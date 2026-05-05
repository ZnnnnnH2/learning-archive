# CuaOS

CuaOS is a desktop computer-use agent that runs actions inside a Docker XFCE
sandbox. The model layer is API-only: executor and verifier use a vision model,
and the planner uses a text model through the same OpenAI-compatible
`/chat/completions` endpoint.

## Model Configuration

Set these environment variables before launching the CLI or GUI:

```powershell
$env:MODEL_API_BASE_URL = "https://dashscope.aliyuncs.com/compatible-mode/v1"
$env:MODEL_API_KEY = "<your-api-key>"
$env:VISION_MODEL = "qwen-vl-max"
$env:PLANNER_MODEL = "qwen-plus"
```

Any OpenAI-compatible service can be used, including Aliyun Model Studio,
OpenRouter, LM Studio, or a self-hosted compatible gateway. The endpoint must
accept `POST {MODEL_API_BASE_URL}/chat/completions`; the vision model must
support `image_url` message content.

Optional:

```powershell
$env:MODEL_API_TIMEOUT = "60"
$env:PLANNER_MAX_TOKENS = "1024"
```

## Install

Use `uv` for Python environment management:

```powershell
$env:UV_CACHE_DIR = (Join-Path (Get-Location) ".uv-cache-local")
New-Item -ItemType Directory -Force -Path $env:UV_CACHE_DIR | Out-Null
uv pip install -r requirements.txt
```

Docker Desktop or Docker Engine must be running for the sandbox. CuaOS keeps the
original sandbox behavior:

- If `cua_xfce_agent` is already running, CuaOS reuses it.
- If a stopped `cua_xfce_agent` container exists, CuaOS removes and recreates it.
- If `docker.io/trycua/cua-xfce:latest` is not present locally, Docker pulls it
  automatically during `docker run`.
- VNC, noVNC, screenshot capture, and mouse/keyboard action execution still use
  the Docker sandbox exactly as before.

The only required new setup is the model API configuration above. No local GGUF
files, GPU setup, `llama-cpp-python`, or HuggingFace model downloads are needed.

## Run

Set the API environment variables in the same PowerShell session before running
one of these entrypoints.

CLI:

```powershell
uv run python main.py
```

GUI:

```powershell
uv run python gui_mission_control.py
```

Hierarchical mission-control GUI:

```powershell
uv run python gui_mission_control_local.py
```

## Test

Tests mock the model API and do not call the network:

```powershell
$env:UV_CACHE_DIR = (Join-Path (Get-Location) ".uv-cache-local")
New-Item -ItemType Directory -Force -Path $env:UV_CACHE_DIR | Out-Null
uv run --with requests --with pytest --with pillow pytest -q
```

Pytest cache and temp output are configured under `.tmp/`.

## Runtime Flow

1. Planner receives the user objective and returns structured plan JSON.
2. Executor receives the current screenshot plus the current step and returns
   one action JSON.
3. The sandbox executes the action.
4. Verifier receives the post-action screenshot and returns structured
   completion JSON.
5. The agent advances, retries, or replans.

Local GGUF, `llama-cpp-python`, HuggingFace model downloads, local GPU layer
configuration, and local MarianMT translation are no longer part of the runtime.
