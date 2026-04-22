"""run_analysis_ui.py — 5-phase paper analysis with live browser UI (SSE streaming).

Usage: python scripts/run_analysis_ui.py <md_path> --focus <focus> [--port 8765]
Opens http://localhost:<port> automatically.
"""
import argparse
import json
import queue
import re
import subprocess
import sys
import threading
import time
import webbrowser
from datetime import datetime
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path

import httpx

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

OLLAMA_BASE = "http://<ollama-host>:13811"
OLLAMA_CHAT = f"{OLLAMA_BASE}/api/chat"
MODEL = "gemma4-31b"
ENABLE_THINKING = True
MAX_SECTIONS = 4

# ── Phase prompts (each call fully independent, no shared history) ─────────────

PHASE2_SYSTEM_TPL = (
    "你正在精读一篇学术论文的特定章节，目标是为读者提取与关注重点直接相关的具体内容。\n"
    "关注重点：{focus}\n\n"
    "阅读以下章节，完成两件事：\n\n"
    "1. 【内容提取】\n"
    "   - 只提取与关注重点**直接相关**的内容，不相关的部分一律跳过\n"
    "   - 要写具体：方法步骤、数据指标、操作流程、公式定义等，让读者读完能真正理解「如何做」\n"
    "   - 忠实原文，不添加、不推断、不总结原文没有的内容\n"
    "   - 若本章节与关注重点无关，直接写：本章节与关注重点无关\n\n"
    "2. 【引用标记】\n"
    "   - 只列出本章节中**实际支撑关注重点内容**的引用，宁缺毋滥\n\n"
    "输出格式（严格两段）：\n"
    "摘要：<详细提取的内容，无字数上限，重要细节不得省略>\n"
    "引用：[1][3] 或 Smith(2020), Jones et al.(2021)（若无相关引用写：引用：无）"
)

PHASE3_SYSTEM_TPL = (
    "你正在基于已提取的章节内容，为读者整理关于【关注重点】的完整理解。\n"
    "关注重点：{focus}\n\n"
    "要求：\n"
    "- 只基于下方提供的章节内容进行分析，不得补充任何原文未提及的信息\n"
    "- 重点写清楚具体的实现方式、步骤、数据、指标等，让读者读完能真正理解\n"
    "- 如果某方面信息不足，直接跳过，不要推测或编造\n"
    "- 不需要套固定框架，内容有什么就写什么\n"
    "- 使用 Markdown 格式，结构自然清晰即可"
)

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
    <div class="ph"><div class="ph-dot" id="d1">1</div><div class="ph-lbl" id="l1">\u7ae0\u8282\u9009\u62e9</div></div>
    <div class="ph"><div class="ph-dot" id="d2">2</div><div class="ph-lbl" id="l2">\u9010\u6bb5\u9605\u8bfb</div></div>
    <div class="ph"><div class="ph-dot" id="d3">3</div><div class="ph-lbl" id="l3">\u7efc\u5408\u5206\u6790</div></div>
    <div class="ph"><div class="ph-dot" id="d4">4</div><div class="ph-lbl" id="l4">\u5f15\u7528\u4e0e\u5143\u6570\u636e</div></div>
  </div>
  <div id="stream"></div>
</div>
<script>
let llmEl=null,llmContent=null,llmThinkEl=null,llmThinkSum=null;
let currentBody=null; // current phase body container
let lastToolCard=null; // 最近一次 tool_call 的卡，用于把 tool_result 追加到同卡
let currentSessionId=null; // 跨会话切换时用它检测新会话
function clearStream(){
  document.getElementById('stream').innerHTML='';
  llmEl=null;llmContent=null;llmThinkEl=null;llmThinkSum=null;
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

const PHASE_MAX=4;
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
    llmEl=null;llmContent=null;llmThinkEl=null;llmThinkSum=null;
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
    llmThinkSum=null;
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
    const el=document.createElement('div');el.className='done-card';
    el.innerHTML='<div class="done-h">&#9989; \u5206\u6790\u5b8c\u6210</div>'+
      '<div class="done-sub">analysis.md \u00b7 refs.json \u00b7 todo_download.txt \u5df2\u5199\u5165</div>'+
      '<div class="done-log">'+esc(ev.log_path)+'</div>';
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
            self.send_header('Access-Control-Allow-Origin', '*')
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


def call_llm_streaming(messages: list[dict]) -> str | None:
    """Stream via native Ollama /api/chat (supports thinking tokens)."""
    full_text = ""
    broadcast({"type": "llm_start"})
    try:
        timeout = httpx.Timeout(connect=30.0, read=TOKEN_TIMEOUT, write=30.0, pool=10.0)
        with httpx.stream(
            "POST", OLLAMA_CHAT,
            json={"model": MODEL, "messages": messages, "stream": True,
                  "think": ENABLE_THINKING, "options": {"temperature": 0.1, "num_ctx": 32768, "num_predict": 16384}},
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


# ── Tool implementations ──────────────────────────────────────────────────────

def tool_list_sections(md_text: str) -> list[dict]:
    lines = md_text.splitlines()
    heading_indices = [i for i, l in enumerate(lines) if re.match(r'^#{1,3}\s+', l)]
    sections = []
    for idx, line_i in enumerate(heading_indices):
        m = re.match(r'^(#{1,3})\s+(.+)', lines[line_i])
        if not m:
            continue
        end = heading_indices[idx + 1] if idx + 1 < len(heading_indices) else len(lines)
        body = "\n".join(l for l in lines[line_i + 1:end] if l.strip())
        sections.append({"id": idx, "level": len(m.group(1)),
                          "title": m.group(2).strip(), "line": line_i + 1,
                          "chars": len("\n".join(lines[line_i:end])),
                          "body_chars": len(body)})
    return sections


def tool_read_section(md_text: str, section_id: int) -> str:
    lines = md_text.splitlines()
    headings = [i for i, l in enumerate(lines) if re.match(r'^#{1,3}\s+', l)]
    if section_id < 0 or section_id >= len(headings):
        return f"[ERROR] section_id {section_id} out of range ({len(headings)} sections)"
    start = headings[section_id]
    end = headings[section_id + 1] if section_id + 1 < len(headings) else len(lines)
    return "\n".join(lines[start:end])


def match_markers_to_refs(markers: list[str], all_refs: list[dict]) -> list[dict]:
    matched_indices: set[int] = set()
    for marker in markers:
        marker = marker.strip()
        m = re.match(r'\[(\d+)\]', marker)
        if m:
            matched_indices.add(int(m.group(1)))
            continue
        m = re.match(r'([A-Z][a-zA-Z\-]+).*?(\d{4})', marker)
        if m:
            lastname = m.group(1).lower()
            year = m.group(2)
            for ref in all_refs:
                if (lastname in ref.get('authors', '').lower() and
                        year in str(ref.get('year', ''))):
                    matched_indices.add(ref['index'])
                    break
    return [r for r in all_refs if r.get('index') in matched_indices]


def parse_phase2_output(text: str) -> tuple[str, list[str]]:
    """Parse LLM output into (summary, relevant_markers)."""
    summary = ""
    markers: list[str] = []
    lines = text.strip().splitlines()
    i = 0
    while i < len(lines):
        line = lines[i].strip()
        if line.startswith("摘要：") or line.startswith("摘要:"):
            parts = [line.split("：", 1)[-1].split(":", 1)[-1].strip()]
            # collect continuation lines until next label or end
            j = i + 1
            while j < len(lines) and not re.match(r'^(摘要|引用)[：:]', lines[j].strip()):
                parts.append(lines[j].strip())
                j += 1
            summary = " ".join(p for p in parts if p)
            i = j
            continue
        if line.startswith("引用：") or line.startswith("引用:"):
            raw = line.split("：", 1)[-1].split(":", 1)[-1].strip()
            if raw and raw != "无":
                # 提取所有 [...] 块，支持 [1] / [1,3] / [1, 3, 5] / [1-3] / 中文逗号
                any_bracketed = False
                for bm in re.finditer(r'\[([0-9,，\s\-\u2013]+)\]', raw):
                    any_bracketed = True
                    block = bm.group(1).strip()
                    # 以负号开头的异常块（如 [-1-3]）直接跳过，避免被拆出 [1][3]
                    if block.startswith(('-', '\u2013')):
                        continue
                    # range: "1-3" 或 "1–3"（lo ≥ 1、hi ≤ 500、跨度 ≤ 20）
                    rm = re.match(r'^\s*(\d+)\s*[\-\u2013]\s*(\d+)\s*$', block)
                    if rm:
                        lo, hi = int(rm.group(1)), int(rm.group(2))
                        if 1 <= lo <= hi <= 500 and hi - lo <= 20:
                            markers.extend(f'[{n}]' for n in range(lo, hi + 1))
                        # 无论是否通过校验，整块 range 处理完都不再落入逗号分支，防止半截命中
                        continue
                    # 逗号/空格分隔的数字列表
                    nums = re.findall(r'\d+', block)
                    markers.extend(f'[{n}]' for n in nums if 1 <= int(n) <= 500)
                if not any_bracketed:
                    # 裸数字兜底上限与 bracketed 分支统一为 500
                    bare = re.findall(r'(?<!\d)(\d{1,3})(?!\d)', raw)
                    markers.extend(f'[{n}]' for n in bare if 1 <= int(n) <= 500)
                # APA with accented chars: "García (2020)", "Smith et al., 2020", "Smith & Jones (2020)"
                _author = (r'[A-Z\u00C0-\u024F][A-Za-z\u00C0-\u024F\-]+'
                           r'(?:\s+et\s+al\.|\s+&\s+[A-Z\u00C0-\u024F][A-Za-z\u00C0-\u024F\-]+'
                           r'(?:\s+et\s+al\.)?)?')
                for m in re.finditer(
                    rf'({_author})(?:\s*[\(\（](\d{{4}})[\)\）]|,\s*(\d{{4}}))',
                    raw
                ):
                    author = m.group(1).strip()
                    year = m.group(2) or m.group(3)
                    markers.append(f'{author} ({year})')
        i += 1
    return summary, list(dict.fromkeys(markers))


def extract_section_markers(section_text: str) -> list[str]:
    """Extract citation markers from full section text using Python regex."""
    markers: list[str] = []
    # Numeric: [1], [1,3], [1-3], [1, 3]
    for m in re.finditer(r'\[(\d[\d,\s\-]*\d|\d)\]', section_text):
        raw = m.group(1)
        if '-' in raw:
            try:
                lo, hi = int(raw.split('-', 1)[0].strip()), int(raw.split('-', 1)[1].strip())
                if 0 < hi - lo <= 20:  # guard against [1-999] explosion
                    markers.extend(f'[{n}]' for n in range(lo, hi + 1))
                else:
                    markers.append(f'[{lo}]')
            except ValueError:
                markers.append(f'[{raw}]')
        elif ',' in raw:
            markers.extend(f'[{n.strip()}]' for n in raw.split(','))
        else:
            markers.append(f'[{raw}]')
    # APA: Smith (2020), Smith & Jones (2020), Smith et al. (2020)
    apa = re.findall(
        r'[A-Z][a-zA-Z\-]+(?:\s+et\s+al\.|\s+&\s+[A-Z][a-zA-Z\-]+(?:\s+et\s+al\.)?)?\s*\(\d{4}\)',
        section_text
    )
    markers.extend(apa)
    return list(dict.fromkeys(markers))[:20]  # dedup, cap at 20


def _run_subprocess(cmd: list[str], label: str) -> subprocess.CompletedProcess | None:
    try:
        r = subprocess.run(cmd, capture_output=True, text=True, encoding="utf-8", timeout=30)
        if r.returncode != 0:
            broadcast({"type": "err", "msg": f"{label} \u5931\u8d25 (code {r.returncode}): {r.stderr[:100]}"})
            return None
        return r
    except subprocess.TimeoutExpired:
        broadcast({"type": "err", "msg": f"{label} \u8d85\u65f6"})
        return None
    except Exception as e:
        broadcast({"type": "err", "msg": f"{label} \u5f02\u5e38: {e}"})
        return None


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


def _llm_call(system: str, user: str) -> str | None:
    broadcast({"type": "llm_input", "system": system, "user": user})
    messages = [{"role": "system", "content": system},
                {"role": "user",   "content": user}]
    text = call_llm_streaming(messages)
    if text is None:
        broadcast({"type": "warn", "msg": "\u7b2c1\u6b21\u8c03\u7528\u5931\u8d25\uff0c\u91cd\u8bd5..."})
        text = call_llm_streaming(messages)
    if text is None:
        broadcast({"type": "warn", "msg": "\u7b2c2\u6b21\u4ecd\u5931\u8d25\uff0c\u8df3\u8fc7\u672c\u6b21\u8c03\u7528"})
    return text


def _run_loop_inner(md_path: Path, focus: str, output_dir: Path):
    # 清空上一次会话的事件缓冲，防止刷新页面回放旧记录；并广播 session_start 让已连接的客户端清屏
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
    # ── 预提取引用 ──────────────────────────────────────────────────────────────
    broadcast({"type": "info", "msg": "\u63d0\u53d6\u5f15\u7528\u6587\u732e..."})
    tprint("开始 extract_refs")
    r = _run_subprocess([sys.executable, "scripts/extract_refs.py", str(md_path)], "extract_refs")
    all_refs: list[dict] = []
    if r:
        try:
            all_refs = json.loads(r.stdout)
        except Exception as e:
            broadcast({"type": "err", "msg": f"extract_refs \u8f93\u51fa\u89e3\u6790\u5931\u8d25: {e}"})
    tprint(f"extract_refs 完成，{len(all_refs)} 条引用")
    broadcast({"type": "info", "msg": f"\u627e\u5230 {len(all_refs)} \u6761\u5f15\u7528\u6587\u732e"})
    log({"type": "refs_extracted", "count": len(all_refs)})

    # ── 阶段1：章节选择（LLM 根据关注重点选择） ─────────────────────────────────────
    broadcast({"type": "iter", "n": 1, "max": 4, "label": "阶段1：章节选择"})
    sections_list = tool_list_sections(md_text)

    candidates = [s for s in sections_list if s.get("body_chars", 0) >= 30]
    section_lines = "\n".join(
        f"{s['id']}. {s['title']}"
        for s in candidates
    )
    sel_system = (
        f"你是学术论文阅读助手。根据用户的关注重点，从章节列表中选出最相关的最多 {MAX_SECTIONS} 个章节。\n"
        f"只输出一行，格式：选中：1, 3\n"
        f"（用章节编号，逗号分隔，不要输出其他内容）"
    )
    sel_user = f"关注重点：{focus}\n\n章节列表：\n{section_lines}\n\n请选出最相关的最多 {MAX_SECTIONS} 个章节编号。"
    tprint("Phase1 LLM 开始（章节选择）")
    sel_text = _llm_call(sel_system, sel_user) or ""
    tprint("Phase1 LLM 完成")

    valid_ids = {s["id"] for s in candidates}
    selected_ids: list[int] = []
    m_sel = re.search(r'^\s*选中[:：]\s*([0-9,，\s]+)\s*$', sel_text, re.M)
    for n in re.findall(r'\d+', m_sel.group(1) if m_sel else ''):
        sid = int(n)
        if sid in valid_ids and sid not in selected_ids:
            selected_ids.append(sid)
        if len(selected_ids) >= MAX_SECTIONS:
            break

    if not selected_ids:
        broadcast({"type": "warn", "msg": "LLM 未按格式输出章节选择，启用关键词 fallback"})
        skip = {"introduction", "abstract", "conclusion", "reference", "bibliograph", "acknowledgement"}
        selected_ids = [s["id"] for s in candidates
                        if not any(w in s["title"].lower() for w in skip)][:MAX_SECTIONS]
        if not selected_ids:
            selected_ids = [s["id"] for s in candidates][:MAX_SECTIONS]

    title_map = {s["id"]: s["title"] for s in sections_list}
    matched_titles = [title_map.get(sid, f"Section {sid}") for sid in selected_ids]
    broadcast({"type": "tool_call", "tool": "select_sections",
               "args": {"total": len(sections_list), "selected": selected_ids, "titles": matched_titles}})
    _sel_lines = "\n".join(f"  [{sid}] {t}" for sid, t in zip(selected_ids, matched_titles))
    broadcast({"type": "tool_result",
               "content": f"从 {len(sections_list)} 个章节中选出 {len(selected_ids)} 个最相关：\n{_sel_lines}"})
    log({"type": "phase1_selected", "ids": selected_ids, "titles": matched_titles})

    # ── \u9636\u6bb52\uff1a\u9010\u6bb5\u9605\u8bfb ──────────────────────────────────────────────────────────
    section_results: list[dict] = []
    all_markers: list[str] = []

    # Pre-compute headings once for section length lookup
    _lines_raw = md_text.splitlines()
    _headings_raw = [i for i, l in enumerate(_lines_raw) if re.match(r'^#{1,3}\s+', l)]

    for i, sid in enumerate(selected_ids):
        tprint(f"Phase2 章节 {i+1}/{len(selected_ids)} 开始 (sid={sid})")
        broadcast({"type": "iter", "n": 2, "max": 4,
                   "label": f"\u9636\u6bb52\uff1a\u9605\u8bfb\u7ae0\u8282 {i+1}/{len(selected_ids)}"})
        title = title_map.get(sid, f"Section {sid}")
        broadcast({"type": "tool_call", "tool": "read_section", "args": {"id": sid, "title": title}})
        if sid < len(_headings_raw):
            st = _headings_raw[sid]
            en = _headings_raw[sid+1] if sid+1 < len(_headings_raw) else len(_lines_raw)
            full_len = len("\n".join(_lines_raw[st:en]))
        else:
            full_len = 0
        # Extract citation markers from FULL section (before truncation)
        full_text_raw = "\n".join(_lines_raw[st:en]) if sid < len(_headings_raw) else ""
        section_text = tool_read_section(md_text, sid)
        broadcast({"type": "tool_result",
                   "content": f"读取章节 [{sid}] {title}（{full_len} 字符）"})

        user2 = f"关注重点：{focus}\n\n章节内容：\n{section_text}"
        tprint(f"Phase2 LLM 开始 (sid={sid})")
        text2 = _llm_call(PHASE2_SYSTEM_TPL.format(focus=focus), user2)
        tprint(f"Phase2 LLM 完成 (sid={sid})")
        log({"type": "phase2_response", "section_id": sid, "content": text2})

        summary, markers = parse_phase2_output(text2) if text2 else ("", [])
        all_markers.extend(markers)
        section_results.append({"id": sid, "title": title, "summary": summary, "markers": markers})
        broadcast({"type": "section_done", "id": sid, "title": title,
                   "summary": summary, "markers": markers})

    # ── \u9636\u6bb53\uff1a\u7efc\u5408\u5206\u6790 ──────────────────────────────────────────────────────────
    tprint("Phase3 开始")
    broadcast({"type": "iter", "n": 3, "max": 4, "label": "\u9636\u6bb53\uff1a\u7efc\u5408\u5206\u6790"})
    MAX_SUMMARY_CHARS = 6000
    trimmed_sums, used = [], 0
    for s in section_results:
        remain = MAX_SUMMARY_CHARS - used
        if remain <= 0:
            break
        part = s["summary"][:remain]
        trimmed_sums.append(f"- Section {s['id']}（{s['title']}）：{part}")
        used += len(part)
    summaries = "\n".join(trimmed_sums)
    user3 = f"\u5173\u6ce8\u91cd\u70b9\uff1a{focus}\n\n\u5404\u7ae0\u8282\u6458\u8981\uff1a\n{summaries}"
    tprint("Phase3 LLM 开始")
    analysis = _llm_call(PHASE3_SYSTEM_TPL.format(focus=focus), user3) or ""
    tprint("Phase3 LLM 完成")
    if not analysis:
        broadcast({"type": "warn", "msg": "\u9636\u6bb53\uff1aLLM \u4e24\u6b21\u5747\u672a\u8fd4\u56de\uff0c\u5206\u6790\u4e3a\u7a7a"})
    else:
        broadcast({"type": "analysis", "text": analysis})
    log({"type": "phase3_analysis", "content": analysis})

    # ── \u9636\u6bb54\uff1a\u5f15\u7528\u5339\u914d + \u5143\u6570\u636e\u8865\u5168\uff08\u5408\u5e76\uff09 ───────────────────────────
    broadcast({"type": "iter", "n": 4, "max": 4, "label": "\u9636\u6bb54\uff1a\u5f15\u7528\u5339\u914d\u4e0e\u5143\u6570\u636e"})
    all_markers = list(dict.fromkeys(all_markers))
    matched_refs = match_markers_to_refs(all_markers, all_refs)
    matched_indices = {r["index"] for r in matched_refs}
    broadcast({"type": "info",
               "msg": f"\u4ece\u5206\u6790\u4e2d\u5339\u914d\u5230 {len(matched_refs)} \u6761\u76f8\u5173\u5f15\u7528\uff08\u6807\u8bb0\uff1a{all_markers}\uff09\uff0c\u7eed\u5145\u5143\u6570\u636e\u2026"})
    log({"type": "phase4_matched", "markers": all_markers, "count": len(matched_refs)})
    enriched: list[dict] = []

    for ref in all_refs:
        ref["relevance"] = "high" if ref.get("index") in matched_indices else "low"
        ref["reason"] = ""
        enriched.append(ref)

    # 并行补全元数据（只处理 high refs），最多 4 个并发
    high_to_enrich = [r for r in enriched if r.get("relevance") == "high" and r.get("title")]

    def _enrich_ref(ref: dict) -> None:
        r2 = _run_subprocess(
            [sys.executable, "scripts/search_refs.py", ref["title"], "--year", str(ref.get("year", ""))],
            f"search_refs[{ref.get('index')}]"
        )
        if r2:
            try:
                meta = json.loads(r2.stdout)
                for k in ("doi", "pdf_url", "authors", "year"):
                    if meta.get(k) and not ref.get(k):
                        ref[k] = meta[k]
            except Exception:
                pass

    import concurrent.futures
    tprint(f"Phase4 并行元数据补全开始，{len(high_to_enrich)} 条")
    with concurrent.futures.ThreadPoolExecutor(max_workers=4) as exc:
        list(exc.map(_enrich_ref, high_to_enrich))
    tprint("Phase4 元数据补全完成")

    # 元数据全部就绪后统一推送，所有卡片同时出现
    for ref in enriched:
        if ref.get("relevance") == "high":
            broadcast({"type": "ref_result",
                       "index": ref.get("index"),
                       "title": ref.get("title", "")[:80],
                       "year": ref.get("year", ""),
                       "relevance": "high",
                       "doi": ref.get("doi", ""),
                       "has_pdf": bool(ref.get("pdf_url"))})

    # 若无匹配结果，给用户一个提示
    if not matched_indices:
        broadcast({"type": "warn", "msg": "\u672c\u6b21\u672a\u5339\u914d\u5230\u4efb\u4f55\u76f8\u5173\u5f15\u7528"})

    # ── \u5199\u8f93\u51fa ────────────────────────────────────────────────────────────────
    output_dir.mkdir(parents=True, exist_ok=True)
    high_refs = [r for r in enriched if r.get("relevance") == "high"]
    overview = "\n".join(
        f"- [{r['index']}] {r.get('authors','')[:30]} ({r.get('year','')}) \u2014 "
        f"{r.get('title','')[:60]} [{r.get('relevance','')}]"
        for r in enriched
    )
    (output_dir / "analysis.md").write_text(
        f"# {md_path.stem}\n\n**\u5173\u6ce8\u91cd\u70b9**\uff1a{focus}\n\n"
        f"## \u6df1\u5ea6\u5206\u6790\n\n{analysis}\n\n"
        f"## \u5f15\u7528\u6587\u732e\u6982\u89c8\n\n{overview}\n",
        encoding="utf-8",
    )
    (output_dir / "refs.json").write_text(
        json.dumps(enriched, ensure_ascii=False, indent=2), encoding="utf-8")
    todo_lines = [
        f"[{r['index']}] {r['title']} | {r.get('doi') or '—'} | {r.get('pdf_url') or 'NOT_FOUND'}"
        for r in high_refs
    ]
    (output_dir / "todo_download.txt").write_text("\n".join(todo_lines), encoding="utf-8")

    ts = datetime.now().strftime('%Y%m%d_%H%M%S')
    log_path = output_dir / f"session_{ts}.jsonl"
    log({"type": "session_complete"})
    log_path.write_text(
        "\n".join(json.dumps(e, ensure_ascii=False) for e in raw_log), encoding="utf-8")

    broadcast({"type": "done", "log_path": str(log_path)})

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
    args = parser.parse_args()

    md_path = Path(args.md_path)
    if not md_path.exists():
        print(f"ERROR: {md_path} not found")
        sys.exit(1)

    output_dir = Path(args.output_dir) / md_path.stem

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
