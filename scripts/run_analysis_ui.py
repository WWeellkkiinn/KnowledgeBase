"""run_analysis_ui.py — 5-phase paper analysis with live browser UI (SSE streaming).

Usage: python scripts/run_analysis_ui.py <md_path> --focus <focus> [--port 8765]
Opens http://localhost:<port> automatically.
"""
import argparse
import json
import queue
import re
import sys
import threading
import time
import webbrowser
from datetime import datetime
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path

import httpx

sys.path.insert(0, str(Path(__file__).parent))
from search_refs import search as search_ref  # noqa: E402
from download_pdf import download as download_pdf_fn  # noqa: E402

# 从同目录读取本地 JS 库（避免 CDN 依赖）
_SCRIPT_DIR = Path(__file__).parent
try:
    _MARKED_JS = (_SCRIPT_DIR / "_marked.min.js").read_text(encoding="utf-8").replace("</script>", "<\\/script>")
    _PURIFY_JS  = (_SCRIPT_DIR / "_dompurify.min.js").read_text(encoding="utf-8").replace("</script>", "<\\/script>")
except FileNotFoundError as _e:
    print(f"ERROR: 缺少 JS 库文件 {_e.filename}，请先运行：\n"
          f"  python -c \"import urllib.request; "
          f"[open('scripts/'+n,'wb').write(urllib.request.urlopen(u).read()) "
          f"for n,u in [('_marked.min.js','https://cdn.jsdelivr.net/npm/marked@12.0.0/marked.min.js'),"
          f"('_dompurify.min.js','https://cdn.jsdelivr.net/npm/dompurify@3.0.9/dist/purify.min.js')]]\"")
    sys.exit(1)

OLLAMA_BASE = "http://<ollama-host>:13812"
OLLAMA_CHAT = f"{OLLAMA_BASE}/api/chat"
MODEL = "qwen3.6-27b"

SYSTEM_TPL = (
    "/no_think\n"
    "你是学术文献分析助手。用户会提供一篇完整论文（Markdown 格式），你将分两轮完成分析任务，每轮均严格遵守指定格式。"
)

INSIGHT_USER_TPL = (
    "{md_text}\n\n"
    "---\n\n"
    "针对关注重点「{focus}」，提取并说明该论文的相关内容，使读者无需阅读原文即可了解论文在此方面的完整做法与发现。\n\n"
    "输出格式（严格遵守，使用自然段落，不要分点列表）：\n\n"
    "## 总览\n"
    "（2-3句话，说明论文在「{focus}」方面做了什么、得出了什么结论）\n\n"
    "## 详细内容\n"
    "（自然段落展开：使用了哪些方法/数据/框架，如何操作，发现了什么）\n\n"
    "## 小结\n"
    "（1句话，核心贡献或主要局限性）"
)

REFS_USER_TPL = (
    "现在列出上述论文中与关注重点「{focus}」高度相关的引用文献，逐条说明：\n"
    "1. 该文献在论文中的具体作用\n"
    "2. 与「{focus}」的直接联系\n\n"
    "只输出高相关引用，不相关的直接忽略。\n\n"
    "输出格式（严格遵守）：\n\n"
    "### [编号] 第一作者 et al. (年份) — 完整标题  ·  DOI: 10.xxxx/xxxx\n"
    "**在论文中的作用**：xxx\n"
    "**与「{focus}」的联系**：xxx\n\n"
    "---\n\n"
    "规则：\n"
    "- 每条引用之间用 --- 分隔\n"
    "- 若只有一位作者则不加 et al.\n"
    "- DOI：若论文参考文献列表中明确给出，原样抄录在标题后；若未给出则省略整个 `  ·  DOI: ...` 部分，**绝不编造或猜测 DOI**"
)

# ── Ref parsing ───────────────────────────────────────────────────────────────

# 匹配 LLM Phase 2 输出：`### 1. Giczy...` 或 `### [1] Giczy...`
# 序号接受 `N.` / `[N]` / `[N].`；分隔符接受 em dash (—) 或 ASCII hyphen (-)
_REF_HEADING = re.compile(
    r'^###\s*\[?(\d+)\]?\.?\s*(.+?)\s+\((\d{4})\)\s*[—–-]\s*'
    r'(.+?)(?:\s*·\s*DOI:\s*(\S+))?\s*$',
    re.MULTILINE,
)


def _parse_refs(text: str) -> list[dict]:
    """解析 analysis_refs.md 中的引用标题行为结构化条目。"""
    out = []
    for m in _REF_HEADING.finditer(text):
        idx, authors, year, title, doi = m.groups()
        first = re.match(r'[A-Za-z]+', authors)
        out.append({
            "index": int(idx),
            "authors": authors.strip(),
            "year": year,
            "title": title.strip(),
            "doi": (doi or "").strip(),
            "first_author": (first.group(0).lower() if first else "unknown"),
        })
    return out


# ── SSE broadcast ─────────────────────────────────────────────────────────────

_clients: list[queue.Queue] = []
_clients_lock = threading.Lock()
_event_buffer: list[str] = []   # replay buffer for late-joining clients


def broadcast(event: dict):
    data = json.dumps(event, ensure_ascii=False)
    with _clients_lock:
        _event_buffer.append(data)
        for q in _clients:
            q.put(data)


# ── HTML UI ───────────────────────────────────────────────────────────────────

HTML = """\
<!DOCTYPE html>
<html lang="zh">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width,initial-scale=1">
<title>KnowledgeBase \u5206\u6790</title>
<script>__MARKED_JS__</script>
<script>__PURIFY_JS__</script>
<style>
:root{
  --bg:#F5F1E8;--surface:#FEFCF8;--border:#E2DDD4;
  --text:#2A2620;--muted:#8C867C;--faint:#C4BFB8;
  /* 语义色：每种角色一种颜色，全局统一 */
  --llm:#4338CA;--llm-bg:#EEF2FF;--llm-border:#C7D2FE;          /* LLM 输出（紫） */
  --prompt:#64748B;--prompt-bg:#F1F5F9;--prompt-border:#CBD5E1; /* Prompt（蓝灰） */
  --tool:#166534;--tool-bg:#F0FDF4;--tool-border:#86EFAC;       /* 工具调用（绿） */
  --result:#92400E;--result-bg:#FFFBEB;--result-border:#FCD34D; /* 结构化结果/章节/分析（琥珀） */
  --amber:#92400E;--amber-bg:#FFFBEB;--amber-border:#FCD34D;
  --red:#991B1B;--red-bg:#FEF2F2;--red-border:#FECACA;
  --think:#6B7280;--think-bg:#F9FAFB;
  /* 兼容旧别名（过渡期，避免大面积替换） */
  --accent:var(--llm);--accent-bg:var(--llm-bg);--accent-border:var(--llm-border);
  --green:var(--tool);--green-bg:var(--tool-bg);--green-border:var(--tool-border);
}
*{box-sizing:border-box;margin:0;padding:0}
html{scroll-behavior:smooth}
body{background:var(--bg);color:var(--text);font-family:'DM Sans',sans-serif;font-size:13.5px;line-height:1.6;min-height:100vh}
/* Header */
#hdr{position:sticky;top:0;z-index:100;background:var(--surface);border-bottom:1px solid var(--border);padding:0 16px;height:54px;display:flex;align-items:center;gap:14px;box-shadow:0 1px 4px rgba(0,0,0,.05)}
#logo{font-family:'Lora',serif;font-size:15px;font-weight:600;letter-spacing:-.2px;color:var(--text)}
#logo em{color:var(--accent);font-style:normal}
#badge{font-size:11px;font-weight:500;color:var(--muted);background:var(--bg);border:1px solid var(--border);padding:2px 10px;border-radius:20px;white-space:nowrap}
#conn{font-size:11px;color:var(--muted)}
/* Layout */
#layout{display:flex;gap:24px;max-width:980px;margin:0 auto;padding:24px 10px;align-items:flex-start}
/* Sidebar */
#sidebar{width:188px;flex-shrink:0;position:sticky;top:70px}
.sb-title{font-size:10.5px;font-weight:600;letter-spacing:.08em;text-transform:uppercase;color:var(--faint);margin-bottom:14px}
.ph{display:flex;gap:10px;align-items:flex-start;position:relative;padding:5px 0}
.ph:not(:last-child)::after{content:'';position:absolute;left:10px;top:27px;bottom:-5px;width:1px;background:var(--border)}
.ph-dot{width:21px;height:21px;border-radius:50%;border:2px solid var(--border);background:var(--surface);display:flex;align-items:center;justify-content:center;font-size:9px;font-weight:700;color:var(--faint);flex-shrink:0;transition:all .3s;z-index:1}
.ph-dot.active{border-color:var(--accent);background:var(--accent);color:#fff;box-shadow:0 0 0 3px var(--accent-bg)}
.ph-dot.done{border-color:var(--green);background:var(--green);color:#fff}
.ph-lbl{font-size:12px;color:var(--muted);padding-top:2px;line-height:1.4;transition:color .3s}
.ph-lbl.active{color:var(--text);font-weight:500}
/* Stream */
#stream{flex:1;min-width:0;display:flex;flex-direction:column;gap:8px}
.card{background:var(--surface);border:1px solid var(--border);border-radius:8px;padding:12px 15px;animation:fadeUp .2s ease;word-break:break-word}
@keyframes fadeUp{from{opacity:0;transform:translateY(5px)}to{opacity:1;transform:translateY(0)}}
.clabel{font-size:10px;font-weight:700;letter-spacing:.07em;text-transform:uppercase;margin-bottom:7px}
/* Phase collapsible group — 一级：阶段头（柔和） */
.phase-group{display:flex;flex-direction:column;gap:0;margin-top:16px}
.phase-group:first-child{margin-top:0}
.ph-hdr{background:var(--surface);color:var(--text);
  border:1px solid var(--border);border-left:3px solid var(--accent);
  border-radius:6px;padding:9px 14px;
  font-family:'Lora',serif;font-size:14px;font-weight:600;
  margin:0;animation:fadeUp .2s ease;cursor:pointer;user-select:none;
  display:flex;align-items:center;gap:10px}
.ph-hdr:hover{background:var(--accent-bg)}
.ph-toggle{font-size:9px;transition:transform .2s;display:inline-block;opacity:.55;color:var(--accent)}
/* 二级：阶段内容缩进 + 虚线左边框体现从属 */
.phase-body{display:flex;flex-direction:column;gap:8px;margin-left:18px;
  padding:10px 0 6px 14px;border-left:2px dashed var(--border)}
/* 二级头：子阶段（如"阅读章节 2/4"） */
.subphase-hdr{font-family:'DM Sans',sans-serif;font-size:12px;font-weight:600;
  color:var(--muted);letter-spacing:.04em;text-transform:uppercase;
  margin:6px 0 2px 0;padding-left:4px;border-left:3px solid var(--faint);
  padding-top:2px;padding-bottom:2px}
/* Info card (neutral 蓝灰) */
.info-card{border-left:2px solid var(--prompt-border);background:var(--prompt-bg)}
.info-card .clabel{color:var(--prompt)}
.info-txt{font-size:12px;color:var(--prompt)}
/* 气泡共用：用内部小节 + 分隔线组织 System/User 或 思考/输出 */
.bubble-section{padding:2px 0}
.bubble-label{font-size:10px;font-weight:700;letter-spacing:.06em;text-transform:uppercase;color:var(--muted);margin-bottom:4px;opacity:.8}
.bubble-divider{height:1px;background:var(--border);margin:8px 0;opacity:1}
.bubble-text{font-family:'JetBrains Mono',monospace;font-size:13px;white-space:pre-wrap;line-height:1.65;color:var(--text);max-height:360px;overflow-y:auto}
.bubble-text.think{color:var(--think);font-style:italic;max-height:220px}
/* LLM 气泡（紫，左对齐，宽度固定避免流式时收缩） */
.llm-card{border-left:3px solid var(--llm);background:var(--llm-bg);align-self:flex-start;width:92%}
.llm-card .clabel .sec-title{font-family:'Lora',serif;font-size:12px;font-weight:600;color:var(--text);text-transform:none;letter-spacing:0;opacity:.85;margin-left:2px}
.rendered-md{font-family:'Lora',serif!important;font-size:14px!important;line-height:1.8!important;color:var(--text)!important;font-style:normal!important}
.rendered-md p{margin:0 0 8px 0}.rendered-md p:last-child{margin-bottom:0}
.rendered-md ul,.rendered-md ol{padding-left:22px;margin:4px 0 8px 0}
.rendered-md strong{font-weight:600}
.rendered-md code{font-family:'JetBrains Mono',monospace!important;font-size:12.5px!important;background:#fff;padding:1px 4px;border-radius:3px;font-style:normal!important}
.rendered-md pre{font-family:'JetBrains Mono',monospace!important;font-size:12px!important;background:#fff;padding:8px 10px;border-radius:4px;overflow-x:auto;font-style:normal!important}
.llm-card .clabel{color:var(--llm);display:flex;align-items:center;gap:6px}
.cur{display:inline-block;width:7px;height:14px;background:var(--llm);vertical-align:text-bottom;animation:blink 1s step-end infinite;border-radius:1px;margin-left:2px}
@keyframes blink{50%{opacity:0}}
/* Prompt 气泡（蓝灰，右对齐——"用户"一侧） */
.prompt-card{background:var(--prompt-bg);border:1px solid var(--prompt-border);border-right:3px solid var(--prompt);align-self:flex-end;width:92%}
.prompt-card .clabel{color:var(--prompt);text-align:right}
/* Tool（绿）—— 调用与结果合并在同一张卡，见 Block 4 */
.tool-card{border-left:3px solid var(--tool);background:var(--tool-bg)}
.tool-card .clabel{color:var(--tool)}
.tool-name{font-family:'JetBrains Mono',monospace;font-size:12px;font-weight:500;color:var(--tool)}
.tool-args{font-size:12px;color:#374151;margin-top:3px}
.tool-result{margin-top:8px;padding-top:6px;border-top:1px dashed var(--tool-border);font-size:12px;color:#374151;max-height:120px;overflow-y:auto;white-space:pre-wrap}
.tool-result-label{font-size:10px;font-weight:700;letter-spacing:.07em;text-transform:uppercase;color:var(--tool);margin-bottom:3px;opacity:.75}
/* Result card（fallback：没有匹配上的 tool_result） */
.result-card{border-left:2px solid var(--border);background:var(--bg)}
.result-card .clabel{color:var(--muted)}
.result-text{font-size:12px;color:var(--muted);max-height:90px;overflow-y:auto;white-space:pre-wrap}
/* Section（琥珀——结构化结果） */
.sec-card{border-left:3px solid var(--result);background:var(--result-bg)}
.sec-card .clabel{color:var(--result)}
.sec-title{font-family:'Lora',serif;font-size:13px;font-weight:600;color:var(--text);margin-bottom:5px}
.sec-summary{font-size:12.5px;color:var(--muted)}
/* Analysis（琥珀——结构化结果） */
.analysis-card{border-left:3px solid var(--result);background:var(--result-bg)}
.analysis-card .clabel{color:var(--result)}
.analysis-text{font-family:'Lora',serif;font-size:14px;line-height:1.8;color:var(--text)}
.analysis-text p{margin:0 0 10px 0}
.analysis-text p:last-child{margin-bottom:0}
.analysis-text ul,.analysis-text ol{padding-left:22px;margin:4px 0 10px 0}
.analysis-text code{font-family:'JetBrains Mono',monospace;font-size:12.5px;background:#fff;padding:1px 4px;border-radius:3px}
.analysis-text strong{color:var(--text);font-weight:600}
/* Ref */
.ref-card{border-left:2px solid var(--border);padding:8px 13px;background:var(--surface)}
.ref-card.ref-high{border-left-color:var(--green)}
.ref-idx{font-family:'JetBrains Mono',monospace;font-size:11px;color:var(--muted);margin-bottom:3px}
.ref-ttl{font-size:12.5px;color:var(--text);font-weight:500}
.rbadge{display:inline-block;font-size:9.5px;font-weight:700;padding:1px 7px;border-radius:10px;letter-spacing:.05em;margin-left:6px;vertical-align:middle}
.rh{background:var(--green-bg);color:var(--green);border:1px solid var(--green-border)}
.rl{background:var(--bg);color:var(--muted);border:1px solid var(--border)}
/* Warn/Err */
.warn-card{border-left:3px solid var(--amber-border);background:var(--amber-bg)}
.warn-card .clabel{color:var(--amber)}
.warn-txt{font-size:12px;color:var(--amber)}
.err-card{border-left:3px solid var(--red-border);background:var(--red-bg)}
.err-card .clabel{color:var(--red)}
.err-txt{font-size:12px;color:var(--red)}
/* Done */
.done-card{background:var(--green-bg);border:1px solid var(--green-border);border-radius:10px;padding:24px;text-align:center;animation:fadeUp .3s ease}
.done-h{font-family:'Lora',serif;font-size:18px;font-weight:600;color:var(--green);margin-bottom:6px}
.done-sub{font-size:12.5px;color:var(--muted)}
.done-log{font-family:'JetBrains Mono',monospace;font-size:10.5px;color:var(--faint);margin-top:8px}
</style>
</head>
<body>
<div id="hdr">
  <div id="logo">Knowledge<em>Base</em></div>
  <span id="badge">\u7b49\u5f85\u542f\u52a8\u2026</span>
  <span id="conn">\u8fde\u63a5\u4e2d</span>
</div>
<div id="layout">
  <div id="sidebar">
    <div class="sb-title">\u5206\u6790\u9636\u6bb5</div>
    <div class="ph"><div class="ph-dot" id="d1">1</div><div class="ph-lbl" id="l1">\u8bba\u6587\u5185\u5bb9\u5206\u6790</div></div>
    <div class="ph"><div class="ph-dot" id="d2">2</div><div class="ph-lbl" id="l2">\u9ad8\u76f8\u5173\u5f15\u7528\u5206\u6790</div></div>
    <div class="ph"><div class="ph-dot" id="d3">3</div><div class="ph-lbl" id="l3">\u4e0b\u8f7d\u5f15\u7528 PDF</div></div>
  </div>
  <div id="stream"></div>
</div>
<script>
let llmEl=null,llmContent=null,llmThinkEl=null;
let currentBody=null; // current phase body container
let lastToolCard=null; // 最近一次 tool_call 的卡，用于把 tool_result 追加到同卡
let currentSessionId=null; // 跨会话切换时用它检测新会话
function clearStream(){
  document.getElementById('stream').innerHTML='';
  llmEl=null;llmContent=null;llmThinkEl=null;
  currentBody=null;lastToolCard=null;
  setPhase(1);
}
// Smart scroll: only auto-scroll when user is near bottom
let userScrolledUp=false;
window.addEventListener('scroll',()=>{
  const nearBottom=window.innerHeight+window.scrollY>=document.body.scrollHeight-120;
  userScrolledUp=!nearBottom;
},{ passive:true });
const es=new EventSource('/events');
es.onopen=()=>set('conn','\u5df2\u8fde\u63a5');
es.onerror=()=>set('conn','\u8fde\u63a5\u65ad\u5f00');
es.onmessage=e=>{try{handle(JSON.parse(e.data));}catch(x){console.error(x,e.data);}};

const PHASE_MAX=3;
function setPhase(n){
  // 夹紧到 [1, PHASE_MAX]，防御异常输入导致负宽/越界
  n=Math.max(1,Math.min(PHASE_MAX,n|0));
  for(let i=1;i<=PHASE_MAX;i++){
    const d=document.getElementById('d'+i),l=document.getElementById('l'+i);
    if(!d||!l)continue;
    if(i<n){d.className='ph-dot done';d.textContent='\u2713';l.className='ph-lbl';}
    else if(i===n){d.className='ph-dot active';d.textContent=i;l.className='ph-lbl active';}
    else{d.className='ph-dot';d.textContent=i;l.className='ph-lbl';}
  }
  // 进入第 n 阶段时，进度 = (n-1)/PHASE_MAX；done 事件才会把进度条填满到 100%
}

function addCard(el){
  (currentBody||document.getElementById('stream')).appendChild(el);
}

function handle(ev){
  const s=document.getElementById('stream');
  if(ev.type==='session_start'){
    // 新会话：若前端曾显示过上一次会话的内容，清屏后重新接收
    if(currentSessionId&&currentSessionId!==ev.session_id){clearStream();}
    currentSessionId=ev.session_id;
    set('badge',ev.md_name||'\u4f1a\u8bdd\u5f00\u59cb');
    return;
  }
  if(ev.type==='iter'){
    set('badge',ev.label||(ev.n+'/'+PHASE_MAX));
    setPhase(ev.n||1);
    // 不再强制折叠旧阶段，尊重用户正在阅读的上下文；只在用户主动点阶段头时折叠
    llmEl=null;llmContent=null;llmThinkEl=null;
    lastToolCard=null;
    // Create collapsible phase group
    const group=document.createElement('div');group.className='phase-group';
    const hdr=document.createElement('div');hdr.className='ph-hdr';
    const tog=document.createElement('span');tog.className='ph-toggle';tog.textContent='\u25bc';
    hdr.appendChild(tog);
    hdr.appendChild(document.createTextNode(' '+esc(ev.label||('Phase '+ev.n))));
    const body=document.createElement('div');body.className='phase-body';
    hdr.addEventListener('click',()=>{
      const open=body.style.display!=='none';
      body.style.display=open?'none':'';
      tog.style.transform=open?'rotate(-90deg)':'';
    });
    group.appendChild(hdr);group.appendChild(body);
    s.appendChild(group);
    currentBody=body;
    scroll();
  }
  else if(ev.type==='llm_start'){
    lastToolCard=null; // LLM 启动后不再向之前的 tool-card 追加结果
    llmEl=document.createElement('div');llmEl.className='card llm-card';
    llmEl.innerHTML=
      '<div class="clabel">&#129302; LLM</div>'+
      '<div class="bubble-section think-sec">'+
        '<div class="bubble-label">\u601d\u8003</div>'+
        '<div class="bubble-text think cnt-think"></div>'+
      '</div>'+
      '<div class="bubble-divider think-div"></div>'+
      '<div class="bubble-section">'+
        '<div class="bubble-label">\u8f93\u51fa</div>'+
        '<div class="bubble-text"><span class="cnt"></span><span class="cur"></span></div>'+
      '</div>';
    addCard(llmEl);
    llmContent=llmEl.querySelector('.cnt');
    llmThinkEl=llmEl.querySelector('.cnt-think');
    scroll();
  }
  else if(ev.type==='llm_thinking'){
    if(llmThinkEl){llmThinkEl.textContent+=ev.text;scroll();}
  }
  else if(ev.type==='llm_token'){
    if(llmContent){llmContent.textContent+=ev.text;scroll();}
  }
  else if(ev.type==='llm_done'){
    if(llmEl){
      const c=llmEl.querySelector('.cur');if(c)c.remove();
      if(llmThinkEl&&!llmThinkEl.textContent.trim()){
        const ts=llmEl.querySelector('.think-sec');if(ts)ts.style.display='none';
        const td=llmEl.querySelector('.think-div');if(td)td.style.display='none';
      }
      // 流式结束后：清理空白 → Markdown 渲染 → KaTeX 公式渲染
      const outBox=llmEl.querySelector('.bubble-section:not(.think-sec) .bubble-text');
      if(outBox&&llmContent){
        const raw=(llmContent.textContent||'')
          .replace(/\\t/g,'  ')
          .replace(/[ ]{4,}/g,'   ')
          .replace(/\\n{3,}/g,'\\n\\n')
          .trim();
        if(raw){
          outBox.innerHTML=md(raw);
          outBox.classList.add('rendered-md');
        }
      }
      llmContent=null;
    }
  }
  else if(ev.type==='llm_input'){
    lastToolCard=null;
    const el=document.createElement('div');el.className='card prompt-card';
    el.innerHTML='<div class="clabel">\u2192 Prompt</div>'+
      '<div class="bubble-section">'+
        '<div class="bubble-label">System</div>'+
        '<div class="bubble-text">'+esc(ev.system)+'</div>'+
      '</div>'+
      '<div class="bubble-divider"></div>'+
      '<div class="bubble-section">'+
        '<div class="bubble-label">User</div>'+
        '<div class="bubble-text">'+esc(ev.user)+'</div>'+
      '</div>';
    addCard(el);scroll();
  }
  else if(ev.type==='tool_call'){
    const el=document.createElement('div');el.className='card tool-card';
    // Truncate args for display: shorten long arrays
    const displayArgs=Object.fromEntries(Object.entries(ev.args||{}).map(([k,v])=>{
      if(Array.isArray(v)&&v.length>3)return[k,v.slice(0,3).concat('...('+v.length+')')];
      if(typeof v==='string'&&v.length>80)return[k,v.slice(0,80)+'...'];
      return[k,v];
    }));
    el.innerHTML='<div class="clabel">&#9881; \u5de5\u5177\u8c03\u7528</div>'+
      '<div class="tool-name">'+esc(ev.tool)+'</div>'+
      '<div class="tool-args">'+esc(JSON.stringify(displayArgs))+'</div>';
    addCard(el);
    lastToolCard=el;
    scroll();
  }
  else if(ev.type==='tool_result'){
    // 优先把结果追加到最近一张未收到结果的 tool-card；否则兜底创建独立 result-card
    if(lastToolCard&&!lastToolCard.querySelector('.tool-result')){
      const r=document.createElement('div');r.className='tool-result';
      r.innerHTML='<div class="tool-result-label">\u2190 \u7ed3\u679c</div>'+esc(ev.content);
      lastToolCard.appendChild(r);
      scroll();
    }else{
      const el=document.createElement('div');el.className='card result-card';
      el.innerHTML='<div class="clabel">\u2190 \u7ed3\u679c</div><div class="result-text">'+esc(ev.content)+'</div>';
      addCard(el);scroll();
    }
    lastToolCard=null; // 已消费：防止再追加
  }
  else if(ev.type==='section_done'){
    // 不再新开独立卡；将章节标题+解析后的 summary/markers 融合到最近一张 LLM 卡
    const last=Array.from(document.querySelectorAll('#stream .llm-card')).pop();
    if(last){
      const cl=last.querySelector('.clabel');
      if(cl && !cl.querySelector('.sec-title')){
        const t=document.createElement('span');t.className='sec-title';
        t.textContent=' \u00b7 '+(ev.title||'');
        cl.appendChild(t);
      }
      scroll();
    }else{
      // Fallback（极端异常路径）
      const el=document.createElement('div');el.className='card sec-card';
      el.innerHTML='<div class="clabel">&#128212; \u7ae0\u8282\u5206\u6790</div>'+
        '<div class="sec-title">'+esc(ev.title)+'</div>'+
        '<div class="sec-summary">'+md(ev.summary||'')+'</div>';
      addCard(el);scroll();
    }
  }
  else if(ev.type==='analysis'){
    // 融合到最近一张 LLM 卡（Phase 3 的 LLM 输出）
    const last=Array.from(document.querySelectorAll('#stream .llm-card')).pop();
    if(last){
      const cl=last.querySelector('.clabel');
      if(cl && !cl.querySelector('.sec-title')){
        const t=document.createElement('span');t.className='sec-title';
        t.textContent=' \u00b7 \u7efc\u5408\u5206\u6790';
        cl.appendChild(t);
      }
      const outBox=last.querySelector('.bubble-section:not(.think-sec) .bubble-text');
      if(outBox && ev.text){
        outBox.innerHTML=md(ev.text);
        outBox.classList.add('rendered-md');
      }
      scroll();
    }else{
      const el=document.createElement('div');el.className='card analysis-card';
      el.innerHTML='<div class="clabel">&#128203; \u7efc\u5408\u5206\u6790</div>'+
        '<div class="analysis-text">'+md(ev.text)+'</div>';
      addCard(el);scroll();
    }
  }
  else if(ev.type==='ref_result'){
    const high=ev.relevance==='high';
    const yearBadge=ev.year?'<span class="rbadge rh">'+esc(String(ev.year))+'</span>':'';
    const doiBadge=ev.doi?'<span class="rbadge rh">DOI</span>':'';
    const pdfBadge=ev.has_pdf?'<span class="rbadge rh">PDF</span>':'';
    const el=document.createElement('div');el.className='card ref-card'+(high?' ref-high':'');
    el.innerHTML='<div class="ref-idx">['+ev.index+']'+yearBadge+doiBadge+pdfBadge+'</div>'+
      '<div class="ref-ttl">'+esc(ev.title)+'</div>';
    addCard(el);scroll();
  }
  else if(ev.type==='info'){
    const el=document.createElement('div');el.className='card info-card';
    el.innerHTML='<div class="info-txt">'+esc(ev.msg)+'</div>';
    addCard(el);scroll();
  }
  else if(ev.type==='warn'){
    const el=document.createElement('div');el.className='card warn-card';
    el.innerHTML='<div class="clabel">&#9888; \u8b66\u544a</div><div class="warn-txt">'+esc(ev.msg)+'</div>';
    addCard(el);scroll();
  }
  else if(ev.type==='err'){
    const el=document.createElement('div');el.className='card err-card';
    el.innerHTML='<div class="clabel">&#10007; \u9519\u8bef</div><div class="err-txt">'+esc(ev.msg)+'</div>';
    addCard(el);scroll();
  }
  else if(ev.type==='done'){
    try{es.close();}catch(_){} // 防止 EventSource 自动重连回放整场
    for(let i=1;i<=PHASE_MAX;i++){const d=document.getElementById('d'+i);if(!d)continue;d.className='ph-dot done';d.textContent='\u2713';document.getElementById('l'+i).className='ph-lbl';}
    set('badge','\u5b8c\u6210 \u2713');set('conn','\u5df2\u5b8c\u6210');
    const el=document.createElement('div');
    if(ev.error){
      el.className='card err-card';
      el.innerHTML='<div class="clabel">&#10007; \u9519\u8bef</div><div class="err-txt">\u5206\u6790\u5f02\u5e38\u9000\u51fa</div>';
    }else{
      el.className='done-card';
      el.innerHTML='<div class="done-h">&#9989; \u5206\u6790\u5b8c\u6210</div>'+
        '<div class="done-sub">analysis_insight.md \u00b7 analysis_refs.md \u5df2\u5199\u5165</div>'+
        '<div class="done-log">'+esc(ev.log_path)+'</div>';
    }
    s.appendChild(el);scroll();
  }
}
function esc(s){return String(s||'').replace(/&/g,'&amp;').replace(/</g,'&lt;').replace(/>/g,'&gt;');}
// 安装一次性 DOMPurify 钩子：给所有 <a> 强制加 target=_blank + rel，防反向 tabnabbing
if(window.DOMPurify){
  DOMPurify.addHook('afterSanitizeAttributes',function(node){
    if(node.tagName==='A'){
      node.setAttribute('target','_blank');
      node.setAttribute('rel','noopener noreferrer');
    }
  });
}
function md(s){
  if(!s)return'';
  try{
    if(window.marked&&window.DOMPurify){
      // 局部传参，不污染全局 marked options
      const html=marked.parse(String(s),{breaks:false,gfm:true});
      // 白名单：只放 Markdown 渲染实际需要的标签/属性
      return DOMPurify.sanitize(html,{
        ALLOWED_TAGS:['p','br','strong','em','code','pre','ul','ol','li',
                      'h1','h2','h3','h4','h5','h6','a','blockquote','hr'],
        ALLOWED_ATTR:['href','target','rel']
      });
    }
  }catch(e){console.error('md render failed',e);}
  return esc(s);
}
function set(id,v){const e=document.getElementById(id);if(e)e.textContent=v;}
let _scrollRaf=0;
function scroll(){
  if(userScrolledUp)return;
  if(_scrollRaf)return;
  _scrollRaf=requestAnimationFrame(()=>{
    _scrollRaf=0;
    // 流式高频调用下用 auto（非平滑）滚动，避免与 token 追加形成抖动竞态
    window.scrollTo({top:document.body.scrollHeight,behavior:'auto'});
  });
}
</script>
</body>
</html>""".replace("__MARKED_JS__", _MARKED_JS).replace("__PURIFY_JS__", _PURIFY_JS).encode('utf-8')


# ── HTTP handler ──────────────────────────────────────────────────────────────

class Handler(BaseHTTPRequestHandler):

    def log_message(self, fmt, *args):
        pass

    def do_GET(self):
        if self.path in ('/', '/index.html'):
            self.send_response(200)
            self.send_header('Content-Type', 'text/html; charset=utf-8')
            self.send_header('Content-Length', str(len(HTML)))
            self.send_header('Cache-Control', 'no-store')
            self.end_headers()
            self.wfile.write(HTML)

        elif self.path == '/events':
            self.send_response(200)
            self.send_header('Content-Type', 'text/event-stream')
            self.send_header('Cache-Control', 'no-cache')
            self.send_header('Access-Control-Allow-Origin', 'http://localhost:8765')
            self.end_headers()

            q: queue.Queue = queue.Queue()
            with _clients_lock:
                buffered = list(_event_buffer)
                _clients.append(q)
            try:
                for i, data in enumerate(buffered):
                    self.wfile.write(f"data: {data}\n\n".encode())
                    if (i + 1) % 50 == 0:
                        self.wfile.flush()
                self.wfile.flush()
            except (BrokenPipeError, ConnectionResetError, OSError):
                with _clients_lock:
                    if q in _clients:
                        _clients.remove(q)
                return
            try:
                while True:
                    try:
                        data = q.get(timeout=25)
                        if data is None:
                            break
                        self.wfile.write(f"data: {data}\n\n".encode())
                        self.wfile.flush()
                    except queue.Empty:
                        self.wfile.write(b": heartbeat\n\n")
                        self.wfile.flush()
            except (BrokenPipeError, ConnectionResetError, OSError):
                pass
            finally:
                with _clients_lock:
                    if q in _clients:
                        _clients.remove(q)
        else:
            self.send_response(404)
            self.end_headers()


# ── LLM streaming ─────────────────────────────────────────────────────────────

TOKEN_TIMEOUT = 300  # seconds; 31B thinking can be slow


def call_llm_streaming(messages: list[dict], num_ctx: int = 32768, num_predict: int = 16384) -> str | None:
    """Stream via native Ollama /api/chat (supports thinking tokens)."""
    full_text = ""
    broadcast({"type": "llm_start"})
    try:
        timeout = httpx.Timeout(connect=30.0, read=TOKEN_TIMEOUT, write=30.0, pool=10.0)
        with httpx.stream(
            "POST", OLLAMA_CHAT,
            json={"model": MODEL, "messages": messages, "stream": True,
                  "options": {"temperature": 0.1, "num_ctx": num_ctx, "num_predict": num_predict}},
            timeout=timeout,
        ) as resp:
            resp.raise_for_status()
            for line in resp.iter_lines():
                if not line:
                    continue
                try:
                    obj = json.loads(line)
                except json.JSONDecodeError:
                    continue
                msg = obj.get("message", {})
                thinking = msg.get("thinking", "")
                content = msg.get("content", "")
                if thinking:
                    broadcast({"type": "llm_thinking", "text": thinking})
                if content:
                    content = re.sub(r'(<channel\|>|<\|[^>]*\|?>)', '', content)
                    full_text += content
                    broadcast({"type": "llm_token", "text": content})
                if obj.get("done"):
                    break
    except httpx.ReadTimeout:
        broadcast({"type": "warn", "msg": f"LLM 读取超过 {TOKEN_TIMEOUT}s，已中断"})
        broadcast({"type": "llm_done"})
        return None
    except httpx.TimeoutException as e:
        broadcast({"type": "warn", "msg": f"LLM 请求超时: {type(e).__name__}"})
        broadcast({"type": "llm_done"})
        return None
    except httpx.ConnectError as e:
        broadcast({"type": "err", "msg": f"Ollama 连接失败: {e}"})
        broadcast({"type": "llm_done"})
        raise
    except httpx.HTTPStatusError as e:
        broadcast({"type": "err", "msg": f"Ollama HTTP {e.response.status_code}: {e.response.text[:80]}"})
        broadcast({"type": "llm_done"})
        return None
    broadcast({"type": "llm_done"})
    if not full_text:
        return None
    full_text = full_text.replace('\ufffd', '')
    full_text = re.sub(r'(.)\1{20,}', r'\1\1\1', full_text)
    return full_text.strip()


# ── Agentic loop ──────────────────────────────────────────────────────────────

def run_loop(md_path: Path, focus: str, output_dir: Path):
    try:
        _run_loop_inner(md_path, focus, output_dir)
    except Exception as e:
        broadcast({"type": "err", "msg": f"loop \u5f02\u5e38\u9000\u51fa: {type(e).__name__}: {e}"})
        # 补一个带 error 的终态事件，防止 UI 卡在 active 无终态
        broadcast({"type": "done", "error": True, "log_path": ""})
    finally:
        # 确保任何退出路径都关闭 SSE 客户端
        time.sleep(1)
        with _clients_lock:
            for q in _clients:
                q.put(None)


def _run_loop_inner(md_path: Path, focus: str, output_dir: Path):
    session_id = datetime.now().strftime("%Y%m%d_%H%M%S_%f")
    with _clients_lock:
        _event_buffer.clear()
    broadcast({"type": "session_start", "session_id": session_id,
               "md_name": md_path.name, "focus": focus})
    md_text = md_path.read_text(encoding="utf-8")
    raw_log: list[dict] = [{"type": "session_start",
                             "timestamp": datetime.now().isoformat(),
                             "model": MODEL, "focus": focus, "md_path": str(md_path)}]

    def log(entry: dict):
        entry.setdefault("timestamp", datetime.now().isoformat())
        raw_log.append(entry)

    def tprint(msg: str):
        print(f"[{datetime.now().strftime('%H:%M:%S')}] {msg}", flush=True)

    tprint("启动分析流程")

    output_dir.mkdir(parents=True, exist_ok=True)
    ts_str = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    header = f"# {md_path.stem}\n\n**关注重点**：{focus}  \n**模型**：{MODEL}  \n**时间**：{ts_str}\n\n---\n\n"

    sys_content = SYSTEM_TPL

    # ── Phase 1：论文内容分析（总分总） ────────────────────────────────────────
    broadcast({"type": "iter", "n": 1, "max": 2, "label": "论文内容分析"})
    tprint("Phase1 LLM 开始（内容分析）")

    user1 = INSIGHT_USER_TPL.format(md_text=md_text, focus=focus)
    messages = [{"role": "system", "content": sys_content},
                {"role": "user",   "content": user1}]
    insight = call_llm_streaming(messages, num_ctx=65536, num_predict=8192) or ""
    tprint("Phase1 LLM 完成")

    if not insight:
        broadcast({"type": "err", "msg": "Phase1 返回空内容，分析中止"})
        return

    log({"type": "phase1_insight", "content": insight})

    (output_dir / "analysis_insight.md").write_text(header + insight + "\n", encoding="utf-8")

    # ── Phase 2：高相关引用分析（multi-turn，复用 KV cache） ──────────────────
    broadcast({"type": "iter", "n": 2, "max": 2, "label": "高相关引用分析"})
    tprint("Phase2 LLM 开始（引用分析）")

    user2 = REFS_USER_TPL.format(focus=focus)
    messages.append({"role": "assistant", "content": insight})
    messages.append({"role": "user",      "content": user2})
    refs = call_llm_streaming(messages, num_ctx=65536, num_predict=8192) or ""
    tprint("Phase2 LLM 完成")
    log({"type": "phase2_refs", "content": refs})

    if not refs:
        broadcast({"type": "warn", "msg": "Phase2 LLM 未返回内容"})

    (output_dir / "analysis_refs.md").write_text(header + refs + "\n", encoding="utf-8")

    # ── Phase 3：逐条搜索元数据并下载 PDF ─────────────────────────────────────
    broadcast({"type": "iter", "n": 3, "max": 3, "label": "下载引用 PDF"})
    tprint("Phase3 开始（搜索 + 下载）")

    parsed = _parse_refs(refs)
    if not parsed:
        broadcast({"type": "info", "msg": "未解析到引用条目，跳过下载"})
    else:
        refs_dir = output_dir / "refs"
        refs_dir.mkdir(parents=True, exist_ok=True)
        failed: list[dict] = []
        for r in parsed:
            idx, title, year = r["index"], r["title"], r["year"]
            src_doi = r.get("doi", "")
            broadcast({"type": "tool_call", "tool": "search_refs",
                       "args": {"title": title, "year": year, "doi": src_doi or "-"}})
            try:
                meta = search_ref(title, year=year, doi=src_doi)
            except Exception as e:
                meta = {"source": f"error:{type(e).__name__}", "pdf_url": "", "doi": ""}
            src = meta.get("source", "?")
            pdf_url = meta.get("pdf_url") or ""
            doi = meta.get("doi") or src_doi
            broadcast({"type": "tool_result",
                       "content": f"source={src}  doi={doi or '-'}  pdf={'yes' if pdf_url else 'no'}"})
            log({"type": "ref_search", "index": idx, "title": title,
                 "source": src, "doi": doi, "pdf_url": pdf_url})

            if not pdf_url:
                failed.append({**r, "doi": doi, "pdf_url": "",
                               "reason": f"未找到 PDF (source={src})"})
                continue

            fname = f"{idx:02d}_{r['first_author']}_{year}.pdf"
            fpath = refs_dir / fname
            broadcast({"type": "tool_call", "tool": "download_pdf",
                       "args": {"url": pdf_url, "out": fname}})
            try:
                ok, msg = download_pdf_fn(pdf_url, str(fpath))
            except Exception as e:
                ok, msg = False, f"{type(e).__name__}: {e}"
            broadcast({"type": "tool_result", "content": msg})
            log({"type": "ref_download", "index": idx, "ok": ok,
                 "path": str(fpath) if ok else "", "reason": "" if ok else msg})

            if not ok:
                failed.append({**r, "doi": doi, "pdf_url": pdf_url, "reason": msg})

        if failed:
            lines = [f"# 下载失败清单\n\n共 {len(failed)} 条需人工介入：\n"]
            for f in failed:
                lines.append(f"## [{f['index']}] {f['authors']} ({f['year']}) — {f['title']}")
                lines.append(f"- doi: {f.get('doi') or '-'}")
                lines.append(f"- pdf_url: {f.get('pdf_url') or '-'}")
                lines.append(f"- reason: {f['reason']}\n")
            failed_path = output_dir / "refs_failed.md"
            # 保留上次人工批注：若已存在，重命名加时间戳后再写新文件
            if failed_path.exists():
                stamp = datetime.now().strftime("%Y%m%d_%H%M%S")
                failed_path.rename(output_dir / f"refs_failed.{stamp}.md")
            failed_path.write_text("\n".join(lines), encoding="utf-8")
            broadcast({"type": "warn",
                       "msg": f"下载失败 {len(failed)}/{len(parsed)} 条 → refs_failed.md"})
        else:
            broadcast({"type": "info", "msg": f"全部 {len(parsed)} 条下载成功"})
    tprint("Phase3 完成")

    ts = datetime.now().strftime('%Y%m%d_%H%M%S')
    log_path = output_dir / f"session_{ts}.jsonl"
    log({"type": "session_complete"})
    log_path.write_text(
        "\n".join(json.dumps(e, ensure_ascii=False) for e in raw_log), encoding="utf-8")

    broadcast({"type": "done", "log_path": str(log_path)})

    # 仅在有 SSE 客户端时才等它们收完再关：headless 下跳过以免浪费 2s
    if _clients:
        time.sleep(2)
        with _clients_lock:
            for q in _clients:
                q.put(None)


# ── Main ──────────────────────────────────────────────────────────────────────

def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("md_path")
    parser.add_argument("--focus", required=True)
    parser.add_argument("--output-dir", default="papers")
    parser.add_argument("--port", type=int, default=8765)
    parser.add_argument("--headless", action="store_true",
                        help="不启 HTTP/浏览器，主线程跑完 3 阶段即退出（供 expand.py 递归用）")
    args = parser.parse_args()

    md_path = Path(args.md_path)
    if not md_path.exists():
        print(f"ERROR: {md_path} not found")
        sys.exit(1)

    output_dir = Path(args.output_dir) / md_path.stem

    if args.headless:
        print(f"[headless] {md_path.name}  focus={args.focus}")
        _run_loop_inner(md_path, args.focus, output_dir)
        return

    ThreadingHTTPServer.allow_reuse_address = True
    ThreadingHTTPServer.daemon_threads = True
    server = ThreadingHTTPServer(("127.0.0.1", args.port), Handler)
    server_thread = threading.Thread(target=server.serve_forever, daemon=True)
    server_thread.start()

    url = f"http://localhost:{args.port}"
    print(f"UI: {url}")
    print(f"论文: {md_path.name}")
    print(f"关注重点: {args.focus}")
    print("Ctrl+C 退出")

    webbrowser.open(url)

    loop_thread = threading.Thread(
        target=run_loop, args=(md_path, args.focus, output_dir), daemon=True
    )
    loop_thread.start()

    try:
        loop_thread.join()
        print("\u5206\u6790\u5b8c\u6210\uff0c\u6d4f\u89c8\u5668\u53ef\u7ee7\u7eed\u67e5\u770b\u3002Ctrl+C \u9000\u51fa\u670d\u52a1\u5668\u3002")
        while True:
            time.sleep(1)
    except KeyboardInterrupt:
        print("\n\u5df2\u9000\u51fa")
    finally:
        server.shutdown()
        server.server_close()


if __name__ == "__main__":
    main()
