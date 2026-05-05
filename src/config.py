import re
import os
from dataclasses import dataclass
from typing import Tuple

def _env_int(name: str, default: int) -> int:
    try:
        return int(os.getenv(name, str(default)))
    except ValueError:
        return default

def _env_float(name: str, default: float) -> float:
    try:
        return float(os.getenv(name, str(default)))
    except ValueError:
        return default

@dataclass
class CFG:
    # ----------------------
    # OpenAI-compatible model API
    # ----------------------
    MODEL_API_BASE_URL: str = os.getenv(
        "MODEL_API_BASE_URL",
        "https://dashscope.aliyuncs.com/compatible-mode/v1",
    )
    MODEL_API_KEY: str = os.getenv("MODEL_API_KEY", "")
    VISION_MODEL: str = os.getenv("VISION_MODEL", "qwen-vl-max")
    PLANNER_MODEL: str = os.getenv("PLANNER_MODEL", "qwen-plus")
    MODEL_API_TIMEOUT: float = _env_float("MODEL_API_TIMEOUT", 60.0)
    PLANNER_MAX_TOKENS: int = _env_int("PLANNER_MAX_TOKENS", 1024)

    # ----------------------
    # Planning LLM
    # ----------------------
    PLANNER_PROVIDER: str = "api"

    # ----------------------
    # Hierarchical Planning Mode
    # ----------------------
    USE_PLANNER: bool = True                  # Enable Plan→Execute→Verify loop

    PLANNER_MAX_REPLAN: int = 2                # Max replan attempts per objective

    # Repeat guard
    STOP_ON_REPEAT: bool = True

    # Tolerance for detecting repeated clicks on the same point
    REPEAT_XY_EPS: float = 0.01     # normalized 0..1

    # Open VM screen as a separate window
    OPEN_VNC_VIEWER: bool = True
    # ----------------------
    # Sandbox Docker config
    # ----------------------
    SANDBOX_IMAGE: str = "docker.io/trycua/cua-xfce:latest"
    SANDBOX_NAME: str = "cua_xfce_agent"

    # (Host side) VNC & API ports. 
    # container 5901: VNC
    # container 6901: noVNC (mapped externally)
    # container 8000: Computer Server API
    VNC_PORT: int = 5901
    NOVNC_PORT: int = 6901
    API_PORT: int = 8001

    # Docker run settings
    DOCKER_SHM_SIZE: str = "512m"
    VNC_RESOLUTION: str = "1920x1080"
    VNC_COL_DEPTH: int = 24

    # If True: launch VNC viewer automatically
    OPEN_VNC_VIEWER: bool = True

    # ----------------------
    # Agent loop timing
    # ----------------------
    WAIT_BEFORE_SCREENSHOT_SEC: float = 2.2
    PAUSE_AFTER_CLICK_SEC: float = 0.25

    SCREENSHOT_PATH: str = "./img/screen.png"
    MAX_DIM: int = 640

    PREVIEW_PATH_TEMPLATE: str = "./img/click_preview_step_{i}.png"

    MIN_MARGIN: float = 0.02
    CONFIDENCE_MIN: float = 0.15

    WAIT_CHANGE_TIMEOUT: float = 3.0
    WAIT_CHANGE_INTERVAL: float = 0.25
    CHANGE_THRESHOLD: float = 0.02

    MAX_STEPS: int = 20
    MODEL_RETRY: int = 2
    API_READY_TIMEOUT: int = 120  # seconds

    # Sandbox screen size cache (seconds)
    SCREEN_CACHE_TTL: float = 0.5

    # Anti-loop
    REPEAT_CLICK_DISTANCE_PX: int = 10

    ALLOWED_PRESS_KEYS: Tuple[str, ...] = (
        "enter", "tab", "esc", "backspace", "delete",
        "up", "down", "left", "right",
        "home", "end", "pageup", "pagedown",
        "space"
    )

    ALLOWED_HOTKEYS: Tuple[Tuple[str, ...], ...] = (
        ("ctrl", "l"),
        ("ctrl", "t"),
        ("ctrl", "w"),
        ("alt", "tab"),
    )


# Instantiate config
cfg = CFG()

# ----------------------
# Regex / MIME tables
# ----------------------

# vision.image_to_data_uri needs this
IMAGE_MIME = {
    ".png": "image/png",
    ".jpg": "image/jpeg",
    ".jpeg": "image/jpeg",
    ".webp": "image/webp",
}

# Used in llm_client to parse JSON from model text
JSON_RE = re.compile(r"\{.*\}", re.S)
