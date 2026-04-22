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

OLLAMA_BASE = "http://<ollama-host>:13811"
OLLAMA_CHAT = f"{OLLAMA_BASE}/api/chat"
MODEL = "gemma4-31b"
ENABLE_THINKING = True
MAX_SECTIONS = 4

# ── Phase prompts (each call fully independent, no shared history) ─────────────

PHASE2_SYSTEM = "阅读以下章节内容，完成两件事：\n1. 用50字以内概括本章节与关注重点的关系\n2. 只列出本章节中与关注重点直接相关的引用标记（如[1][3]或Smith(2020)），不相关的不要列出\n\n严格按以下格式输出两行：\n摘要：<50字以内>\n引用：[1][3] 或 Smith(2020), Jones et al.(2021)\n（若无相关引用则写：引用：无）"

PHASE3_SYSTEM = "\u6839\u636e\u4ee5\u4e0b\u5404\u7ae0\u8282\u6458\u8981\uff0c\u9488\u5bf9\u5173\u6ce8\u91cd\u70b9\u5199\u51fa\u6df1\u5ea6\u5206\u6790\uff08300\u5b57\u4ee5\u5185\uff09\uff0c\u6db5\u76d6\uff1a\u6838\u5fc3\u65b9\u6cd5\u8bba\u51b3\u7b56\u3001\u64cd\u4f5c\u5316\u8def\u5f84\u3001\u6f5c\u5728\u5c40\u9650\u6027\u3002\u53ea\u8f93\u51fa\u5206\u6790\u6587\u5b57\u3002"

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
<link rel="preconnect" href="https://fonts.googleapis.com">
<link href="https://fonts.googleapis.com/css2?family=Lora:ital,wght@0,400;0,600;1,400&family=DM+Sans:opsz,wght@9..40,300;9..40,400;9..40,500&family=JetBrains+Mono:wght@400;500&display=swap" rel="stylesheet">
<style>
:root{
  --bg:#F5F1E8;--surface:#FEFCF8;--border:#E2DDD4;
  --text:#2A2620;--muted:#8C867C;--faint:#C4BFB8;
  --accent:#4338CA;--accent-bg:#EEF2FF;--accent-border:#C7D2FE;
  --green:#166534;--green-bg:#F0FDF4;--green-border:#86EFAC;
  --amber:#92400E;--amber-bg:#FFFBEB;--amber-border:#FCD34D;
  --red:#991B1B;--red-bg:#FEF2F2;--red-border:#FECACA;
  --think:#6B7280;--think-bg:#F9FAFB;
}
*{box-sizing:border-box;margin:0;padding:0}
html{scroll-behavior:smooth}
body{background:var(--bg);color:var(--text);font-family:'DM Sans',sans-serif;font-size:13.5px;line-height:1.6;min-height:100vh}
/* Header */
#hdr{position:sticky;top:0;z-index:100;background:var(--surface);border-bottom:1px solid var(--border);padding:0 28px;height:54px;display:flex;align-items:center;gap:14px;box-shadow:0 1px 4px rgba(0,0,0,.05)}
#logo{font-family:'Lora',serif;font-size:15px;font-weight:600;letter-spacing:-.2px;color:var(--text)}
#logo em{color:var(--accent);font-style:normal}
#badge{font-size:11px;font-weight:500;color:var(--muted);background:var(--bg);border:1px solid var(--border);padding:2px 10px;border-radius:20px;white-space:nowrap}
#prog-wrap{flex:1;max-width:180px;height:3px;background:var(--border);border-radius:3px;overflow:hidden}
#prog{height:100%;width:0%;background:var(--accent);border-radius:3px;transition:width .5s ease}
#conn{font-size:11px;color:var(--muted)}
/* Layout */
#layout{display:flex;gap:24px;max-width:900px;margin:0 auto;padding:24px 20px;align-items:flex-start}
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
/* Phase collapsible group */
.phase-group{display:flex;flex-direction:column;gap:8px}
.ph-hdr{background:var(--bg);border:1px solid var(--border);border-radius:6px;padding:5px 12px;font-size:11.5px;font-weight:600;color:var(--accent);margin-top:4px;animation:fadeUp .2s ease;cursor:pointer;user-select:none;display:flex;align-items:center;gap:6px}
.ph-hdr:hover{background:var(--accent-bg)}
.ph-toggle{font-size:9px;transition:transform .2s;display:inline-block}
.phase-body{display:flex;flex-direction:column;gap:8px}
/* Info card (neutral, not warning) */
.info-card{border-left:2px solid var(--accent-border);background:var(--accent-bg)}
.info-card .clabel{color:#818CF8}
.info-txt{font-size:12px;color:var(--muted)}
/* LLM */
.llm-card{border-left:3px solid var(--accent);background:#FAFBFF}
.llm-card .clabel{color:var(--accent)}
.think-wrap{border:1px solid #E5E7EB;border-radius:5px;margin-bottom:8px;background:var(--think-bg)}
.think-wrap summary{cursor:pointer;font-size:11px;color:var(--think);padding:5px 10px;list-style:none;user-select:none;display:flex;align-items:center;gap:5px}
.think-wrap summary::-webkit-details-marker{display:none}
.think-wrap summary::before{content:'\25B6';font-size:7px;transition:transform .2s}
details[open].think-wrap summary::before{transform:rotate(90deg)}
.think-cnt{font-family:'JetBrains Mono',monospace;font-size:11px;color:var(--think);font-style:italic;max-height:200px;overflow-y:auto;padding:8px 10px;border-top:1px solid #E5E7EB;white-space:pre-wrap;line-height:1.55}
.llm-out{font-family:'JetBrains Mono',monospace;font-size:12.5px;white-space:pre-wrap;line-height:1.65;color:var(--text)}
.cur{display:inline-block;width:7px;height:14px;background:var(--accent);vertical-align:text-bottom;animation:blink 1s step-end infinite;border-radius:1px}
@keyframes blink{50%{opacity:0}}
/* Prompt */
.prompt-card{background:#F8F9FF;border-left:2px solid var(--accent-border)}
.prompt-card .clabel{color:#818CF8}
.prompt-card details summary{cursor:pointer;font-size:12px;color:#818CF8;padding:1px 0}
.prompt-card details summary::-webkit-details-marker{display:none}
.prompt-card pre{font-family:'JetBrains Mono',monospace;font-size:11px;white-space:pre-wrap;color:var(--muted);margin-top:5px;max-height:110px;overflow-y:auto}
/* Tool */
.tool-card{border-left:3px solid var(--green);background:var(--green-bg)}
.tool-card .clabel{color:var(--green)}
.tool-name{font-family:'JetBrains Mono',monospace;font-size:12px;font-weight:500;color:var(--green)}
.tool-args{font-size:12px;color:var(--muted);margin-top:3px}
/* Result */
.result-card{border-left:2px solid var(--border);background:var(--bg)}
.result-card .clabel{color:var(--muted)}
.result-text{font-size:12px;color:var(--muted);max-height:90px;overflow-y:auto;white-space:pre-wrap}
/* Section */
.sec-card{border-left:3px solid var(--green);background:var(--green-bg)}
.sec-card .clabel{color:var(--green)}
.sec-title{font-family:'Lora',serif;font-size:13px;font-weight:600;color:var(--text);margin-bottom:5px}
.sec-summary{font-size:12.5px;color:var(--muted)}
.markers{display:flex;flex-wrap:wrap;gap:4px;margin-top:7px}
.mkr{background:#fff;border:1px solid var(--green-border);color:var(--green);font-size:11px;padding:1px 8px;border-radius:10px;font-family:'JetBrains Mono',monospace}
/* Analysis */
.analysis-card{border-left:3px solid var(--accent);background:var(--accent-bg)}
.analysis-card .clabel{color:var(--accent)}
.analysis-text{font-family:'Lora',serif;font-size:14px;line-height:1.8;color:var(--text);white-space:pre-wrap}
/* Ref */
.ref-card{border-left:2px solid var(--border);padding:8px 13px;background:var(--surface)}
.ref-card.ref-high{border-left-color:var(--green)}
.ref-idx{font-family:'JetBrains Mono',monospace;font-size:11px;color:var(--muted);margin-bottom:3px}
.ref-ttl{font-size:12.5px;color:var(--text);font-weight:500}
.ref-yr{font-size:11.5px;color:var(--muted);margin-top:2px}
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
  <div id="prog-wrap"><div id="prog"></div></div>
  <span id="conn">\u8fde\u63a5\u4e2d</span>
</div>
<div id="layout">
  <div id="sidebar">
    <div class="sb-title">\u5206\u6790\u9636\u6bb5</div>
    <div class="ph"><div class="ph-dot" id="d1">1</div><div class="ph-lbl" id="l1">\u7ae0\u8282\u9009\u62e9</div></div>
    <div class="ph"><div class="ph-dot" id="d2">2</div><div class="ph-lbl" id="l2">\u9010\u6bb5\u9605\u8bfb</div></div>
    <div class="ph"><div class="ph-dot" id="d3">3</div><div class="ph-lbl" id="l3">\u7efc\u5408\u5206\u6790</div></div>
    <div class="ph"><div class="ph-dot" id="d4">4</div><div class="ph-lbl" id="l4">\u5f15\u7528\u5339\u914d</div></div>
    <div class="ph"><div class="ph-dot" id="d5">5</div><div class="ph-lbl" id="l5">\u5143\u6570\u636e\u8865\u5168</div></div>
  </div>
  <div id="stream"></div>
</div>
<script>
let llmEl=null,llmContent=null,llmThinkEl=null,llmThinkSum=null;
let currentBody=null; // current phase body container
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

function setPhase(n){
  for(let i=1;i<=5;i++){
    const d=document.getElementById('d'+i),l=document.getElementById('l'+i);
    if(i<n){d.className='ph-dot done';d.textContent='\u2713';l.className='ph-lbl';}
    else if(i===n){d.className='ph-dot active';d.textContent=i;l.className='ph-lbl active';}
    else{d.className='ph-dot';d.textContent=i;l.className='ph-lbl';}
  }
  document.getElementById('prog').style.width=(Math.min(n-1,4)/4*100)+'%';
}

function addCard(el){
  (currentBody||document.getElementById('stream')).appendChild(el);
}

function handle(ev){
  const s=document.getElementById('stream');
  if(ev.type==='iter'){
    set('badge',ev.label||(ev.n+'/5'));
    setPhase(ev.n||1);
    llmEl=null;llmContent=null;llmThinkEl=null;llmThinkSum=null;
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
    llmEl=document.createElement('div');llmEl.className='card llm-card';
    llmEl.innerHTML=
      '<div class="clabel">&#129302; LLM \u8f93\u51fa</div>'+
      '<details class="think-wrap" open><summary class="think-sum">\u601d\u8003\u4e2d\u2026</summary>'+
      '<div class="think-cnt"></div></details>'+
      '<div class="llm-out"><span class="cnt"></span><span class="cur"></span></div>';
    addCard(llmEl);
    llmContent=llmEl.querySelector('.cnt');
    llmThinkEl=llmEl.querySelector('.think-cnt');
    llmThinkSum=llmEl.querySelector('.think-sum');
    scroll();
  }
  else if(ev.type==='llm_thinking'){
    if(llmThinkEl){
      llmThinkEl.textContent+=ev.text;
      if(llmThinkSum)llmThinkSum.textContent='\u601d\u8003\u94fe \u00b7 '+llmThinkEl.textContent.length+'\u5b57';
      scroll();
    }
  }
  else if(ev.type==='llm_token'){
    if(llmContent){llmContent.textContent+=ev.text;scroll();}
  }
  else if(ev.type==='llm_done'){
    if(llmEl){
      const c=llmEl.querySelector('.cur');if(c)c.remove();
      const tw=llmEl.querySelector('.think-wrap');
      if(tw){if(llmThinkEl&&!llmThinkEl.textContent)tw.style.display='none';else tw.removeAttribute('open');}
    }
  }
  else if(ev.type==='llm_input'){
    const el=document.createElement('div');el.className='card prompt-card';
    el.innerHTML='<div class="clabel">\u2192 Prompt</div>'+
      '<details><summary>\u2630 System</summary><pre>'+esc(ev.system)+'</pre></details>'+
      '<details><summary>\u2630 User</summary><pre>'+esc(ev.user)+'</pre></details>';
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
    addCard(el);scroll();
  }
  else if(ev.type==='tool_result'){
    const el=document.createElement('div');el.className='card result-card';
    el.innerHTML='<div class="clabel">\u2190 \u7ed3\u679c</div><div class="result-text">'+esc(ev.content)+'</div>';
    addCard(el);scroll();
  }
  else if(ev.type==='section_done'){
    const mkrs=ev.markers&&ev.markers.length
      ?ev.markers.map(m=>'<span class="mkr">'+esc(m)+'</span>').join('')
      :'<span style="color:var(--faint)">\u65e0</span>';
    const el=document.createElement('div');el.className='card sec-card';
    el.innerHTML='<div class="clabel">&#128212; \u7ae0\u8282\u5206\u6790</div>'+
      '<div class="sec-title">'+esc(ev.title)+'</div>'+
      '<div class="sec-summary">'+esc(ev.summary||'\u65e0\u6458\u8981')+'</div>'+
      '<div class="markers">'+mkrs+'</div>';
    addCard(el);scroll();
  }
  else if(ev.type==='analysis'){
    const el=document.createElement('div');el.className='card analysis-card';
    el.innerHTML='<div class="clabel">&#128203; \u7efc\u5408\u5206\u6790</div>'+
      '<div class="analysis-text">'+esc(ev.text)+'</div>';
    addCard(el);scroll();
  }
  else if(ev.type==='ref_result'){
    const high=ev.relevance==='high';
    const badge='<span class="rbadge '+(high?'rh':'rl')+'">'+(high?'HIGH':'LOW')+'</span>';
    const meta=(ev.doi?'<span style="color:var(--green);font-size:11px"> DOI\u2713</span>':'')+
               (ev.has_pdf?'<span style="color:var(--green);font-size:11px"> PDF\u2713</span>':'');
    const el=document.createElement('div');el.className='card ref-card'+(high?' ref-high':'');
    el.innerHTML='<div class="ref-idx">['+ev.index+']'+badge+meta+'</div>'+
      '<div class="ref-ttl">'+esc(ev.title)+'</div>'+
      '<div class="ref-yr">'+esc(ev.year||'')+'</div>';
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
    document.getElementById('prog').style.width='100%';
    for(let i=1;i<=5;i++){const d=document.getElementById('d'+i);d.className='ph-dot done';d.textContent='\u2713';document.getElementById('l'+i).className='ph-lbl';}
    set('badge','\u5b8c\u6210 \u2713');set('conn','\u5df2\u5b8c\u6210');
    const el=document.createElement('div');el.className='done-card';
    el.innerHTML='<div class="done-h">&#9989; \u5206\u6790\u5b8c\u6210</div>'+
      '<div class="done-sub">analysis.md \u00b7 refs.json \u00b7 todo_download.txt \u5df2\u5199\u5165</div>'+
      '<div class="done-log">'+esc(ev.log_path)+'</div>';
    s.appendChild(el);scroll();
  }
}
function esc(s){return String(s||'').replace(/&/g,'&amp;').replace(/</g,'&lt;').replace(/>/g,'&gt;');}
function set(id,v){const e=document.getElementById(id);if(e)e.textContent=v;}
function scroll(){if(!userScrolledUp)window.scrollTo({top:document.body.scrollHeight,behavior:'smooth'});}
</script>
</body>
</html>""".encode('utf-8')


# ── HTTP handler ──────────────────────────────────────────────────────────────

class Handler(BaseHTTPRequestHandler):

    def log_message(self, fmt, *args):
        pass

    def do_GET(self):
        if self.path in ('/', '/index.html'):
            self.send_response(200)
            self.send_header('Content-Type', 'text/html; charset=utf-8')
            self.send_header('Content-Length', str(len(HTML)))
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
                for data in buffered:
                    self.wfile.write(f"data: {data}\n\n".encode())
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
                  "think": ENABLE_THINKING, "options": {"temperature": 0.1, "num_ctx": 8192, "num_predict": 4096}},
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
                if obj.get("done"):
                    break
                    broadcast({"type": "llm_token", "text": content})
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
                # numeric: [1][3] or bare "17"
                bracketed = re.findall(r'\[(\d+)\]', raw)
                markers.extend(f'[{n}]' for n in bracketed)
                if not bracketed:
                    bare = re.findall(r'(?<!\d)(\d{1,3})(?!\d)', raw)
                    markers.extend(f'[{n}]' for n in bare if 1 <= int(n) <= 200)
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
    return summary[:200], list(dict.fromkeys(markers))


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
    md_text = md_path.read_text(encoding="utf-8")
    raw_log: list[dict] = [{"type": "session_start",
                             "timestamp": datetime.now().isoformat(),
                             "model": MODEL, "focus": focus, "md_path": str(md_path)}]

    def log(entry: dict):
        raw_log.append(entry)

    # ── \u9884\u63d0\u53d6\u5f15\u7528 ──────────────────────────────────────────────────────────────
    broadcast({"type": "info", "msg": "\u63d0\u53d6\u5f15\u7528\u6587\u732e..."})
    r = _run_subprocess([sys.executable, "scripts/extract_refs.py", str(md_path)], "extract_refs")
    all_refs: list[dict] = []
    if r:
        try:
            all_refs = json.loads(r.stdout)
        except Exception as e:
            broadcast({"type": "err", "msg": f"extract_refs \u8f93\u51fa\u89e3\u6790\u5931\u8d25: {e}"})
    broadcast({"type": "info", "msg": f"\u627e\u5230 {len(all_refs)} \u6761\u5f15\u7528\u6587\u732e"})
    log({"type": "refs_extracted", "count": len(all_refs)})

    # ── \u9636\u6bb51\uff1a\u7ae0\u8282\u9009\u62e9\uff08\u7eaf\u4ee3\u7801\uff0c\u5173\u952e\u8bcd\u5339\u914d\uff09 ─────────────────────────────────────────
    broadcast({"type": "iter", "n": 1, "max": 5, "label": "\u9636\u6bb51\uff1a\u7ae0\u8282\u9009\u62e9"})
    sections_list = tool_list_sections(md_text)

    focus_words = re.findall(r'[\w]+', focus.lower())
    keyword_map = {
        "\u7814\u7a76": ["research", "study", "method", "data", "approach"],
        "\u65b9\u6cd5": ["method", "methodology", "data", "measur", "model", "sample", "construct"],
        "\u7ed3\u8bba": ["result", "finding", "conclusion", "discussion"],
        "\u7406\u8bba": ["theory", "theoretical", "background", "literature", "concept"],
    }
    expanded = set(focus_words)
    for zh, en_list in keyword_map.items():
        if zh in focus:
            expanded.update(en_list)

    scored = []
    for s in sections_list:
        if s.get("body_chars", 0) < 30:  # skip heading-only sections (no real content)
            continue
        title_lower = s["title"].lower()
        score = sum(1 for w in expanded if w in title_lower)
        if score > 0:
            scored.append((score, s["id"]))
    scored.sort(reverse=True)
    selected_ids = [sid for _, sid in scored[:MAX_SECTIONS]]

    if not selected_ids:
        skip = {"introduction", "abstract", "conclusion", "reference", "bibliograph", "acknowledgement"}
        candidates = [s["id"] for s in sections_list
                      if s.get("body_chars", 0) >= 30
                      and not any(w in s["title"].lower() for w in skip)]
        selected_ids = candidates[:MAX_SECTIONS] or list(range(min(MAX_SECTIONS, len(sections_list))))

    title_map = {s["id"]: s["title"] for s in sections_list}
    matched_titles = [title_map.get(sid, f"Section {sid}") for sid in selected_ids]
    broadcast({"type": "tool_call", "tool": "select_sections",
               "args": {"total": len(sections_list), "selected": selected_ids, "titles": matched_titles}})
    log({"type": "phase1_selected", "ids": selected_ids, "titles": matched_titles})

    # ── \u9636\u6bb52\uff1a\u9010\u6bb5\u9605\u8bfb ──────────────────────────────────────────────────────────
    section_results: list[dict] = []
    all_markers: list[str] = []

    # Pre-compute headings once for section length lookup
    _lines_raw = md_text.splitlines()
    _headings_raw = [i for i, l in enumerate(_lines_raw) if re.match(r'^#{1,3}\s+', l)]

    for i, sid in enumerate(selected_ids):
        broadcast({"type": "iter", "n": 2, "max": 5,
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
        text2 = _llm_call(PHASE2_SYSTEM, user2)
        log({"type": "phase2_response", "section_id": sid, "content": text2})

        summary, markers = parse_phase2_output(text2) if text2 else ("", [])
        all_markers.extend(markers)
        section_results.append({"id": sid, "title": title, "summary": summary, "markers": markers})
        broadcast({"type": "section_done", "id": sid, "title": title,
                   "summary": summary, "markers": markers})

    # ── \u9636\u6bb53\uff1a\u7efc\u5408\u5206\u6790 ──────────────────────────────────────────────────────────
    broadcast({"type": "iter", "n": 3, "max": 5, "label": "\u9636\u6bb53\uff1a\u7efc\u5408\u5206\u6790"})
    summaries = "\n".join(
        f"- Section {s['id']}\uff08{s['title']}\uff09\uff1a{s['summary']}" for s in section_results
    )
    user3 = f"\u5173\u6ce8\u91cd\u70b9\uff1a{focus}\n\n\u5404\u7ae0\u8282\u6458\u8981\uff1a\n{summaries}"
    analysis = _llm_call(PHASE3_SYSTEM, user3) or ""
    if not analysis:
        broadcast({"type": "warn", "msg": "\u9636\u6bb53\uff1aLLM \u4e24\u6b21\u5747\u672a\u8fd4\u56de\uff0c\u5206\u6790\u4e3a\u7a7a"})
    else:
        broadcast({"type": "analysis", "text": analysis})
    log({"type": "phase3_analysis", "content": analysis})

    # ── \u9636\u6bb54\uff1a\u5f15\u7528\u5339\u914d\uff08\u7eaf\u4ee3\u7801\uff09 ──────────────────────────────────────────────────
    broadcast({"type": "iter", "n": 4, "max": 5, "label": "\u9636\u6bb54\uff1a\u5f15\u7528\u5339\u914d"})
    all_markers = list(dict.fromkeys(all_markers))
    matched_refs = match_markers_to_refs(all_markers, all_refs)
    matched_indices = {r["index"] for r in matched_refs}
    broadcast({"type": "tool_result",
               "content": f"\u5339\u914d\u5230 {len(matched_refs)} \u6761\u76f8\u5173\u5f15\u7528\uff1a{all_markers}"})
    log({"type": "phase4_matched", "markers": all_markers, "count": len(matched_refs)})

    # ── \u9636\u6bb55\uff1a\u5143\u6570\u636e\u8865\u5168 ──────────────────────────────────────────────────────────
    broadcast({"type": "iter", "n": 5, "max": 5, "label": "\u9636\u6bb55\uff1a\u8865\u5145\u5143\u6570\u636e"})
    search_cache: dict = {}
    enriched: list[dict] = []

    for ref in all_refs:
        idx = ref.get("index")
        ref["relevance"] = "high" if idx in matched_indices else "low"
        ref["reason"] = ""
        ref_title = ref.get("title", "")
        year = str(ref.get("year", ""))

        if idx in matched_indices and ref_title:
            r2 = _run_subprocess(
                [sys.executable, "scripts/search_refs.py", ref_title, "--year", year],
                f"search_refs[{idx}]"
            )
            if r2:
                try:
                    meta = json.loads(r2.stdout)
                    search_cache[f"{ref_title[:50].lower()}|{year}"] = meta
                    for k in ("doi", "pdf_url", "authors", "year"):
                        if meta.get(k) and not ref.get(k):
                            ref[k] = meta[k]
                except Exception:
                    pass

        broadcast({"type": "ref_result",
                   "index": ref.get("index"),
                   "title": ref.get("title", "")[:60],
                   "year": ref.get("year", ""),
                   "relevance": ref.get("relevance", ""),
                   "doi": ref.get("doi", ""),
                   "has_pdf": bool(ref.get("pdf_url"))})
        enriched.append(ref)

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
    print(f"\u8bba\u6587: {md_path.name}")
    print(f"\u5173\u6ce8\u91cd\u70b9: {args.focus}")
    print("Ctrl+C \u9000\u51fa")

    time.sleep(0.3)
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
