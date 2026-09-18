"""Generate colab/SenioCare_Model_Server.ipynb from readable cell sources.

    python colab/build_notebook.py colab/SenioCare_Model_Server.ipynb
"""
import json
import sys

cells = []


def md(text):
    cells.append({"cell_type": "markdown", "metadata": {}, "source": text.strip("\n").splitlines(keepends=True)})


def code(text):
    cells.append({"cell_type": "code", "metadata": {}, "execution_count": None, "outputs": [],
                  "source": text.strip("\n").splitlines(keepends=True)})


md(r"""
# SenioCare — Model Server on Colab

This notebook runs **only the model**, exposed as an **OpenAI-compatible API** (`/v1/chat/completions`).
The SenioCare backend (FastAPI + ADK + tools + database) runs wherever you run it — your laptop, Render, Replit — and consumes this endpoint exactly like it would consume Google AI Studio or any other provider.

```
Flutter app ──► SenioCare backend (tools, prompts, sessions, Postgres) ──► this Colab (GPU inference only)
```

Nothing about tools lives here. ADK sends the model the tool *schemas*; the model returns tool-call requests; ADK executes the Python back in the backend process.

**Run the cells top to bottom.** Cell 5 prints the three `.env` lines to paste into the backend. Cell 6 is the gate: if the tool-calling smoke test fails, the Feature Agent will not work with this model either, regardless of hosting.

> Runtime → Change runtime type → **GPU** (T4 is enough for a 4B model). Free-tier Colab idles out after ~90 minutes and the tunnel URL changes on every restart; re-run cell 5 and update the backend's `.env` when that happens.
""")

md("## 1. Configuration")
code(r'''
# ---- Backend that serves the model --------------------------------------------
BACKEND = "ollama"          # "ollama" (simplest, GGUF quantised) or "vllm" (faster batching, HF weights)

# Model identifiers for each backend
OLLAMA_MODEL = "gemma4:e4b"                   # `ollama pull` name
VLLM_MODEL   = "google/gemma-3-4b-it"         # Hugging Face repo (needs HF_TOKEN for gated models)
SERVED_NAME  = OLLAMA_MODEL if BACKEND == "ollama" else VLLM_MODEL   # name clients use

# ---- Tunnel -------------------------------------------------------------------
TUNNEL = "cloudflared"      # "cloudflared" (no account, random URL) or "ngrok" (token, stable subdomain on paid plans)

# Secrets: add NGROK_AUTH_TOKEN / HF_TOKEN in Colab's left sidebar (key icon) instead of pasting here.
def _secret(name):
    try:
        from google.colab import userdata
        return userdata.get(name)
    except Exception:
        import os
        return os.environ.get(name, "")

NGROK_AUTH_TOKEN = _secret("NGROK_AUTH_TOKEN")
HF_TOKEN         = _secret("HF_TOKEN")

PORT = 11434 if BACKEND == "ollama" else 8000
LOCAL_BASE = f"http://127.0.0.1:{PORT}/v1"
print(f"backend={BACKEND} model={SERVED_NAME} tunnel={TUNNEL} local={LOCAL_BASE}")
''')

md("## 2. GPU check")
code(r'''
import subprocess
print(subprocess.run(["nvidia-smi", "--query-gpu=name,memory.total,memory.used", "--format=csv,noheader"],
                     capture_output=True, text=True).stdout or "No GPU visible — switch the runtime type to GPU.")
''')

md("## 3. Install and start the model server")
code(r'''
import os, subprocess, time, requests, shlex

SERVER = None

def _wait_for(url, timeout=600, label="server"):
    t0 = time.time()
    while time.time() - t0 < timeout:
        try:
            if requests.get(url, timeout=3).status_code < 500:
                print(f"{label} ready after {time.time()-t0:.0f}s")
                return True
        except Exception:
            pass
        time.sleep(2)
    raise RuntimeError(f"{label} did not come up within {timeout}s")

def _have(cmd):
    return subprocess.run(["which", cmd], capture_output=True).returncode == 0

def _install_ollama():
    """Documented manual install (tarball into /usr, CUDA libs included); the
    install script as a fallback. Errors are printed, never hidden."""
    if _have("ollama"):
        return
    # Ollama >= 0.10 ships zstd-compressed bundles; both install paths need zstd.
    if not _have("zstd"):
        print("Installing zstd …")
        subprocess.run("apt-get update -qq >/dev/null 2>&1; apt-get install -y -qq zstd >/dev/null 2>&1", shell=True)
    print("Installing Ollama (tarball) …")
    r = subprocess.run(
        "curl -fL --retry 3 https://ollama.com/download/ollama-linux-amd64.tar.zst -o /tmp/ollama.tar.zst "
        "&& tar --zstd -C /usr -xf /tmp/ollama.tar.zst",
        shell=True, capture_output=True, text=True)
    if r.returncode != 0 or not _have("ollama"):
        print("tarball install failed:", (r.stderr or r.stdout)[-1500:])
        print("Trying the official install script …")
        r = subprocess.run("curl -fsSL https://ollama.com/install.sh | bash", shell=True, capture_output=True, text=True)
        print((r.stdout + r.stderr)[-2500:])
    if not _have("ollama"):
        raise RuntimeError("Ollama install failed — see the output above")
    print("ollama:", subprocess.run(["ollama", "--version"], capture_output=True, text=True).stdout.strip())

if BACKEND == "ollama":
    _install_ollama()
    # Ollama serves a 4,096-token context by default, whatever the model supports.
    # SenioCare's Orchestrator prompt alone is ~3.8k tokens: with the default the
    # model got ~300 tokens to answer and hit MAX_TOKENS on every turn
    # (docs/FINDINGS.md F-10). 16k leaves room for prompt + reasoning + plan.
    env = dict(os.environ,
               OLLAMA_HOST="0.0.0.0:11434",
               OLLAMA_CONTEXT_LENGTH="16384",
               OLLAMA_KEEP_ALIVE="-1",        # never unload the model between requests
               OLLAMA_NUM_PARALLEL="2",
               OLLAMA_FLASH_ATTENTION="1")
    # A server from an earlier run of this cell would keep the old context length.
    subprocess.run(["pkill", "-f", "ollama serve"], capture_output=True)
    time.sleep(2)
    SERVER = subprocess.Popen(["ollama", "serve"], env=env,
                              stdout=open("/tmp/ollama.log", "w"), stderr=subprocess.STDOUT)
    _wait_for("http://127.0.0.1:11434/api/tags", label="Ollama")
    tags = requests.get("http://127.0.0.1:11434/api/tags").json().get("models", [])
    if not any(m["name"].startswith(OLLAMA_MODEL) for m in tags):
        print(f"Pulling {OLLAMA_MODEL} …")
        subprocess.run(["ollama", "pull", OLLAMA_MODEL], check=True)
    # Load into VRAM now rather than on the first real request
    requests.post("http://127.0.0.1:11434/api/generate", json={"model": OLLAMA_MODEL, "keep_alive": -1}, timeout=600)
    print(subprocess.run(["ollama", "ps"], capture_output=True, text=True).stdout)

elif BACKEND == "vllm":
    subprocess.run("pip install -q vllm", shell=True, check=True)
    env = dict(os.environ, HF_TOKEN=HF_TOKEN or "", HUGGING_FACE_HUB_TOKEN=HF_TOKEN or "")
    cmd = (f"python -m vllm.entrypoints.openai.api_server --model {shlex.quote(VLLM_MODEL)} "
           f"--served-model-name {shlex.quote(SERVED_NAME)} --host 0.0.0.0 --port {PORT} "
           f"--max-model-len 8192 --gpu-memory-utilization 0.90 --dtype auto "
           f"--enable-auto-tool-choice --tool-call-parser hermes")
    SERVER = subprocess.Popen(cmd, shell=True, env=env,
                              stdout=open("/tmp/vllm.log", "w"), stderr=subprocess.STDOUT)
    _wait_for(f"http://127.0.0.1:{PORT}/v1/models", timeout=1500, label="vLLM")
else:
    raise ValueError(BACKEND)

print("models:", [m["id"] for m in requests.get(f"{LOCAL_BASE}/models").json()["data"]])
''')

md("""
## 4. Smoke tests (local, before tunnelling)

Two tests through the OpenAI-compatible endpoint, i.e. exactly what LiteLLM in the backend will send:

1. **Plain chat** in Egyptian Arabic — proves generation works.
2. **Tool calling** — the model is given one function schema and a prompt that requires it. **This is the gate.** SenioCare's Feature Agent depends on the model emitting a well-formed `tool_calls` array with parseable JSON arguments. If this fails here, hosting is not the problem; pick a model with native function calling.
""")
code(r'''
import json, time, requests

def chat(messages, tools=None, max_tokens=256, base=None, timeout=180):
    body = {"model": SERVED_NAME, "messages": messages, "max_tokens": max_tokens, "temperature": 0.1}
    if tools:
        body["tools"] = tools
        body["tool_choice"] = "auto"
    t0 = time.time()
    r = requests.post(f"{base or LOCAL_BASE}/chat/completions", json=body,
                      headers={"Authorization": "Bearer not-needed"}, timeout=timeout)
    r.raise_for_status()
    data = r.json()
    data["_latency_s"] = round(time.time() - t0, 2)
    return data

def report(name, ok, detail):
    print(f"[{'PASS' if ok else 'FAIL'}] {name}: {detail}")
    return ok

# --- Warm-up: the first request after load is slow and is not what we measure
chat([{"role": "user", "content": "hi"}], max_tokens=8)

# --- Test 1: plain chat in Egyptian Arabic.
# Thinking models (gemma4, qwen3, …) spend completion tokens on hidden reasoning
# before answering; give them room, and report empty content explicitly.
resp = chat([{"role": "system", "content": "أنت مساعد صحي لكبار السن. رد باللهجة المصرية في جملتين."},
             {"role": "user", "content": "عايز أكلة خفيفة على الغدا"}], max_tokens=768)
msg1 = resp["choices"][0]["message"]
text = msg1.get("content") or ""
reasoning = msg1.get("reasoning") or msg1.get("reasoning_content") or ""
usage = resp.get("usage", {})
t1 = report("plain chat", len(text.strip()) > 0,
            f"{resp['_latency_s']}s, {usage.get('completion_tokens')} completion tokens"
            + (f" ({len(reasoning)} chars hidden reasoning)" if reasoning else "")
            + f" → {text[:120]!r}"
            + ("" if text.strip() else "  <- empty content: raise max_tokens or disable thinking mode"))

# --- Test 2: tool calling (schema mirrors seniocare/tools/nutrition.py::get_meal_options)
tools = [{
    "type": "function",
    "function": {
        "name": "get_meal_options",
        "description": "Get meal options for the user filtered by their health conditions and allergies.",
        "parameters": {
            "type": "object",
            "properties": {
                "meal_type": {"type": "string", "enum": ["breakfast", "lunch", "dinner", "snack"],
                              "description": "Which meal of the day"}
            },
            "required": ["meal_type"],
        },
    },
}]
resp = chat([{"role": "system", "content": "You are a health assistant. You MUST call get_meal_options to answer meal requests. Never answer from memory."},
             {"role": "user", "content": "I want something good for lunch"}], tools=tools)
msg = resp["choices"][0]["message"]
calls = msg.get("tool_calls") or []
ok = False
detail = f"{resp['_latency_s']}s, finish_reason={resp['choices'][0].get('finish_reason')}, no tool_calls; content={str(msg.get('content'))[:120]!r}"
if calls:
    fn = calls[0].get("function", {})
    try:
        args = json.loads(fn.get("arguments") or "{}")
        ok = fn.get("name") == "get_meal_options" and args.get("meal_type") == "lunch"
        detail = f"{resp['_latency_s']}s → {fn.get('name')}({args})"
    except json.JSONDecodeError as e:
        detail = f"tool call present but arguments are not valid JSON: {fn.get('arguments')!r} ({e})"
t2 = report("tool calling", ok, detail)

# --- Test 3: tool result round trip (model must use the returned data, not call again)
if t2:
    followup = chat([
        {"role": "system", "content": "You are a health assistant. Use tool results to answer."},
        {"role": "user", "content": "I want something good for lunch"},
        {"role": "assistant", "content": None, "tool_calls": calls},
        {"role": "tool", "tool_call_id": calls[0]["id"], "name": "get_meal_options",
         "content": json.dumps({"status": "success", "options": [{"name_ar": "شوربة عدس", "name_en": "Lentil soup"}]})},
    ], tools=tools)
    m3 = followup["choices"][0]["message"]
    t3 = report("tool result round trip", not m3.get("tool_calls") and bool(m3.get("content")),
                f"{followup['_latency_s']}s → {str(m3.get('content'))[:120]!r}")
else:
    t3 = False

print()
print("GATE:", "PASS — this model can drive SenioCare's Feature Agent" if (t1 and t2 and t3)
      else "FAIL — do not point the backend at this model; stage 2 will not call tools reliably")
''')

md("""
## 5. Expose the server and print the backend `.env` lines

`cloudflared` needs no account and gives a random `*.trycloudflare.com` URL. `ngrok` needs `NGROK_AUTH_TOKEN` in Colab secrets and gives a stable subdomain on paid plans.
""")
code(r'''
import re, subprocess, time, requests

PUBLIC_URL = None
TUNNEL_PROC = None

if TUNNEL == "cloudflared":
    if subprocess.run(["which", "cloudflared"], capture_output=True).returncode != 0:
        subprocess.run("curl -fsSL -o /tmp/cf.deb https://github.com/cloudflare/cloudflared/releases/latest/download/cloudflared-linux-amd64.deb "
                       "&& dpkg -i /tmp/cf.deb", shell=True, check=True, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
    TUNNEL_PROC = subprocess.Popen(["cloudflared", "tunnel", "--url", f"http://127.0.0.1:{PORT}", "--no-autoupdate"],
                                   stdout=subprocess.PIPE, stderr=subprocess.STDOUT, text=True)
    t0 = time.time()
    while time.time() - t0 < 60 and PUBLIC_URL is None:
        line = TUNNEL_PROC.stdout.readline()
        m = re.search(r"https://[a-z0-9-]+\.trycloudflare\.com", line)
        if m:
            PUBLIC_URL = m.group(0)
    if PUBLIC_URL is None:
        raise RuntimeError("cloudflared did not print a URL within 60s")

elif TUNNEL == "ngrok":
    if not NGROK_AUTH_TOKEN:
        raise RuntimeError("Add NGROK_AUTH_TOKEN to Colab secrets (key icon in the left sidebar) and re-run.")
    subprocess.run("pip install -q pyngrok", shell=True, check=True)
    from pyngrok import ngrok, conf
    conf.get_default().auth_token = NGROK_AUTH_TOKEN
    ngrok.kill()
    PUBLIC_URL = ngrok.connect(PORT, "http").public_url.replace("http://", "https://")
else:
    raise ValueError(TUNNEL)

# A quick tunnel's hostname takes a little while to propagate in DNS; poll instead of failing.
ok = False
t0 = time.time()
while time.time() - t0 < 120:
    try:
        ok = requests.get(f"{PUBLIC_URL}/v1/models", timeout=15).status_code == 200
        if ok:
            break
    except Exception as e:
        last = f"{type(e).__name__}"
    time.sleep(5)
print("public endpoint:", PUBLIC_URL, f"OK after {time.time()-t0:.0f}s" if ok else "NOT RESPONDING YET — DNS may still be propagating; re-run cell 6 in a minute")

model_name = f"openai/{SERVED_NAME}" if BACKEND == "ollama" else f"hosted_vllm/{SERVED_NAME}"
print(f"""
==================== paste into the backend's .env ====================
MODEL_NAME={model_name}
MODEL_API_BASE={PUBLIC_URL}/v1
MODEL_API_KEY=
=======================================================================
then:  python scripts/check_model.py      (verifies tool calling through LiteLLM)
       python main.py
""")
''')

md("## 6. Smoke test through the public URL (what the backend will actually experience)")
code(r'''
resp = chat([{"role": "user", "content": "قول أهلاً في كلمتين"}], base=f"{PUBLIC_URL}/v1", max_tokens=32)
print(f"via tunnel: {resp['_latency_s']}s →", resp["choices"][0]["message"]["content"])
''')

md("""
## 7. Keep alive

Leave this cell running. It keeps the Colab session active, and logs GPU memory and a request counter every minute so you can see the backend's traffic arriving. Stop it (■) when you are done.
""")
code(r'''
import subprocess, time, requests
count = 0
try:
    while True:
        try:
            requests.get(f"{LOCAL_BASE}/models", timeout=5)
            gpu = subprocess.run(["nvidia-smi", "--query-gpu=memory.used,memory.total,utilization.gpu", "--format=csv,noheader"],
                                 capture_output=True, text=True).stdout.strip()
            status = f"up | GPU {gpu}"
        except Exception as e:
            status = f"DOWN: {e}"
        count += 1
        print(f"[{time.strftime('%H:%M:%S')}] {status} | public={PUBLIC_URL}", flush=True)
        time.sleep(60)
except KeyboardInterrupt:
    print("keep-alive stopped")
''')

md("## 8. Shutdown")
code(r'''
for name in ("TUNNEL_PROC", "SERVER"):
    p = globals().get(name)
    if p is not None:
        p.terminate()
        print(name, "terminated")
try:
    from pyngrok import ngrok; ngrok.kill()
except Exception:
    pass
''')

nb = {
    "cells": cells,
    "metadata": {
        "accelerator": "GPU",
        "colab": {"name": "SenioCare_Model_Server.ipynb", "provenance": [], "gpuType": "T4"},
        "kernelspec": {"display_name": "Python 3", "name": "python3"},
        "language_info": {"name": "python"},
    },
    "nbformat": 4,
    "nbformat_minor": 0,
}
out = sys.argv[1]
with open(out, "w", encoding="utf-8", newline="\n") as f:
    json.dump(nb, f, ensure_ascii=False, indent=1)
print("wrote", out, "cells:", len(cells))
