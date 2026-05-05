import json
import os
import sys

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from src.llm_client import ask_next_action
from src.planner import PlanStep
from src.verifier import verify_step


class FakeClient:
    def __init__(self, content):
        self.content = content
        self.calls = []

    def complete_text(self, **kwargs):
        self.calls.append(kwargs)
        return self.content


def test_executor_sends_vision_payload(monkeypatch):
    monkeypatch.setattr("src.llm_client.image_to_data_uri", lambda path: "data:image/png;base64,abc")
    client = FakeClient(json.dumps({"action": "CLICK", "x": 0.5, "y": 0.4}))

    out = ask_next_action(client, "click button", "screen.png", [])

    assert out["action"] == "CLICK"
    call = client.calls[0]
    assert call["model"]
    user_content = call["messages"][1]["content"]
    assert user_content[0]["type"] == "image_url"
    assert user_content[0]["image_url"]["url"] == "data:image/png;base64,abc"


def test_verifier_uses_vision_payload(monkeypatch):
    monkeypatch.setattr("src.verifier.image_to_data_uri", lambda path: "data:image/png;base64,abc")
    client = FakeClient(json.dumps({
        "step_id": "S1",
        "done": True,
        "evidence": ["dialog is closed"],
        "failure_type": "NONE",
        "suggested_fix": "",
        "confidence": 0.9,
    }))

    result = verify_step(
        client,
        PlanStep(id="S1", title="Close dialog", success_criteria=["dialog is closed"]),
        "screen.png",
    )

    assert result.done is True
    assert client.calls[0]["model"]
