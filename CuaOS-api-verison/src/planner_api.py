# planner_api.py — OpenAI-compatible API planner
from __future__ import annotations

import json
from typing import Any, Dict

from src.config import cfg, JSON_RE
from src.model_api import ModelAPIClient, load_model_api_client
from src.planner import (
    Plan,
    Planner,
    PLANNER_SYSTEM_PROMPT,
    build_planner_user_prompt,
    validate_plan_json,
)


class APIPlanner(Planner):
    """Plan generation via the configured OpenAI-compatible chat API."""

    def __init__(self, client: ModelAPIClient | None = None):
        self._client = client or load_model_api_client()
        self._model = cfg.PLANNER_MODEL
        self._max_tokens = cfg.PLANNER_MAX_TOKENS

        if not self._model:
            raise ValueError("PLANNER_MODEL must be set to use the API planner.")

        print(f"[PLANNER] API planner ready (model={self._model})")

    def plan(self, objective: str, context: str = "") -> Plan:
        user_prompt = build_planner_user_prompt(objective, context)

        raw_text = self._client.complete_text(
            model=self._model,
            messages=[
                {"role": "system", "content": PLANNER_SYSTEM_PROMPT},
                {"role": "user", "content": user_prompt},
            ],
            temperature=0.2,
            top_p=0.9,
            max_tokens=self._max_tokens,
        )
        return self._parse_plan(raw_text, objective)

    @staticmethod
    def _parse_plan(raw_text: str, objective: str) -> Plan:
        """Parse JSON plan from raw API output."""
        m = JSON_RE.search(raw_text.strip())
        if not m:
            raise ValueError(f"API planner output is not valid JSON:\n{raw_text[:500]}")

        plan_data: Dict[str, Any] = json.loads(m.group(0))
        plan_data.setdefault("objective", objective)

        validate_plan_json(plan_data)
        return Plan.from_dict(plan_data)
