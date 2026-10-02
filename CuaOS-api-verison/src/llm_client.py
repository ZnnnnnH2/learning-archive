# llm_client.py
from __future__ import annotations

import json
from typing import Any, Dict, List

from src.config import cfg, JSON_RE
from src.model_api import ModelAPIClient, load_model_api_client
from src.vision import image_to_data_uri


def load_llm() -> ModelAPIClient:
    client = load_model_api_client()
    print(
        "[LLM] API client ready "
        f"(base_url={client.base_url}, vision_model={cfg.VISION_MODEL})"
    )
    return client



def _parse_json_obj(text: str) -> Dict[str, Any]:
    m = JSON_RE.search(text.strip())
    if not m:
        raise ValueError(f"Model output is not JSON: {text}")
    return json.loads(m.group(0))


def ask_next_action(
    llm: ModelAPIClient,
    objective: str,
    screenshot_path: str,
    history: List[Dict[str, Any]],
) -> Dict[str, Any]:
    """
    Returns one action JSON. When done: {"action":"BITTI", ...}
    """
    uri = image_to_data_uri(screenshot_path)

    system = (
        "You are a reactive GUI agent.\n"
        "Given OBJECTIVE, HISTORY (executed actions), and a SCREENSHOT, decide the NEXT single action.\n\n"
        "Return EXACTLY one JSON object. No extra text.\n"
        "Schema:\n"
        "{\n"
        '  "action": "CLICK|DOUBLE_CLICK|RIGHT_CLICK|TYPE|PRESS|HOTKEY|SCROLL|WAIT|NOOP|BITTI",\n'
        '  "x": 0.5,\n'
        '  "y": 0.5,\n'
        '  "text": "",\n'
        '  "key": "",\n'
        '  "keys": [""],\n'
        '  "scroll": 0,\n'
        '  "seconds": 0.0,\n'
        '  "target": "short description",\n'
        '  "confidence": 0.0,\n'
        '  "why_short": "<=12 words"\n'
        "}\n\n"
        "Rules:\n"
        "- Output ONLY valid JSON.\n"
        "- For CLICK/DOUBLE_CLICK/RIGHT_CLICK: set x,y.\n"
        "- For TYPE: set text.\n"
        "- For PRESS: set key.\n"
        "- For HOTKEY: set keys list.\n"
        "- For SCROLL: set scroll (positive=up, negative=down).\n"
        "- For WAIT: set seconds.\n"
        "- If objective is complete, action MUST be BITTI.\n"
        "- Do NOT propose repeating the last executed action unless it clearly failed.\n"
        f"- Safety: Never output x or y within {cfg.MIN_MARGIN} of edges.\n"
    )

    user = (
        f"OBJECTIVE: {objective}\n"
        f"HISTORY: {json.dumps(history, ensure_ascii=False)}\n"
        "Decide the NEXT action from the CURRENT screenshot."
    )

    raw_text = llm.complete_text(
        model=cfg.VISION_MODEL,
        messages=[
            {"role": "system", "content": system},
            {"role": "user", "content": [
                {"type": "image_url", "image_url": {"url": uri}},
                {"type": "text", "text": user},
            ]},
        ],
        temperature=0.1,
        top_p=0.9,
        max_tokens=220,
        stop=["\n\n", "<|im_end|>"],
    )
    return _parse_json_obj(raw_text)
