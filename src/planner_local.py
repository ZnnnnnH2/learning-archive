from __future__ import annotations

from src.planner_api import APIPlanner


class LocalGGUFPlanner(APIPlanner):
    """Compatibility shim for old imports.

    CuaOS no longer supports local GGUF / llama.cpp planners. Existing callers
    that still import LocalGGUFPlanner receive the API planner instead.
    """
