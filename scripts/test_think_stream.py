"""Test whether Ollama /api/chat streams thinking tokens in real-time."""
import httpx, json, time

print("Connecting to Ollama /api/chat with think=True...")
t0 = time.time()
think_arrivals = []
content_arrivals = []

with httpx.stream("POST", "http://<ollama-host>:13811/api/chat",
    json={"model": "gemma4-31b",
          "messages": [{"role": "user", "content": "what is 2+2? think step by step"}],
          "stream": True, "think": True,
          "options": {"temperature": 0.1}},
    timeout=httpx.Timeout(connect=10, read=120, write=30, pool=10)) as r:
    print(f"HTTP {r.status_code}")
    for i, line in enumerate(r.iter_lines()):
        if not line:
            continue
        try:
            obj = json.loads(line)
        except:
            continue
        msg = obj.get("message", {})
        think = msg.get("thinking", "")
        content = msg.get("content", "")
        elapsed = time.time() - t0
        if think:
            think_arrivals.append(elapsed)
            print(f"  t={elapsed:.2f}s  THINK chunk #{len(think_arrivals)}: {repr(think[:80])}")
        if content:
            content_arrivals.append(elapsed)
            print(f"  t={elapsed:.2f}s  CONTENT chunk #{len(content_arrivals)}: {repr(content[:80])}")
        if obj.get("done"):
            print(f"  t={elapsed:.2f}s  DONE")
            break
        if i > 200:
            print("200 lines reached, stopping")
            break

print()
print(f"Think chunks: {len(think_arrivals)}, first at t={think_arrivals[0]:.2f}s" if think_arrivals else "Think chunks: 0 (NONE RECEIVED)")
print(f"Content chunks: {len(content_arrivals)}, first at t={content_arrivals[0]:.2f}s" if content_arrivals else "Content chunks: 0")
if len(think_arrivals) > 1:
    gaps = [think_arrivals[i]-think_arrivals[i-1] for i in range(1, min(5, len(think_arrivals)))]
    print(f"Think inter-chunk gaps (first 4): {[f'{g:.3f}s' for g in gaps]}")
    print("=> Streaming: YES" if max(gaps) < 2 else "=> Streaming: BUFFERED (large gaps)")
