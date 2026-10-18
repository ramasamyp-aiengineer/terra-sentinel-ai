"""Gemini agent: model-fallback chain and explicit tool loop, exercised with a fake client (no network, no quota)."""
from __future__ import annotations

import json
from types import SimpleNamespace

import pytest
from google.genai import types

from app.core.config import settings
from app.services.agent import gemini
from app.services.detection import pipeline

SITE = "METRO4-DEMO-004"
GOOD = json.dumps({"summary": "ok", "mechanism_hypothesis": "m", "recommended_action": "a", "site_specific_checks": ["c1"]})


class _Err(Exception):
    def __init__(self, code):
        super().__init__(f"HTTP {code}")
        self.code = code


def _resp(text=None, calls=()):
    fcs = [SimpleNamespace(name=n, args=a) for n, a in calls]
    parts = [types.Part(function_call=types.FunctionCall(name=n, args=a)) for n, a in calls] or [types.Part.from_text(text=text or "")]
    return SimpleNamespace(
        function_calls=fcs or None,
        text=None if fcs else text,
        candidates=[SimpleNamespace(content=types.Content(role="model", parts=parts))],
    )


class _FakeModels:
    """behaviour[model] is an HTTP code to raise, 'no-tools', 'ok', or a list of per-round responses."""

    def __init__(self, behaviour):
        self.behaviour = behaviour
        self.requests: list[dict] = []

    @property
    def tried(self):
        out: list[str] = []
        for r in self.requests:
            if r["model"] not in out:
                out.append(r["model"])
        return out

    def generate_content(self, model, contents, config):
        mode = config.tool_config.function_calling_config.mode
        self.requests.append({"prompt": contents[0].parts[0].text, "model": model, "mode": str(mode).split(".")[-1], "n_contents": len(contents), "afc_off": config.automatic_function_calling.disable})
        b = self.behaviour[model]
        if isinstance(b, int):
            raise _Err(b)
        rounds = sum(1 for r in self.requests if r["model"] == model)
        if b == "no-tools":
            return _resp(text=GOOD)
        if b == "ok":
            if rounds == 1:  # a well-behaved model asks for several tools in parallel, then answers
                return _resp(calls=[("get_site_metrics", {"site_id": SITE}), ("get_outlook", {"site_id": SITE})])
            return _resp(text="```json\n" + GOOD + "\n```")
        return b[min(rounds, len(b)) - 1]


@pytest.fixture()
def fake(monkeypatch):
    monkeypatch.setattr(settings, "gemini_api_key", "test-key")
    monkeypatch.setattr(settings, "gemini_model", "m1")
    monkeypatch.setattr(settings, "gemini_fallback_models", "m2,m3")
    monkeypatch.setattr(settings, "gemini_budget_s", 30.0)

    def install(behaviour):
        models = _FakeModels(behaviour)
        monkeypatch.setattr(gemini, "_client", lambda t: SimpleNamespace(models=models, vertexai=False))
        return models

    return install


@pytest.fixture(scope="module", autouse=True)
def _demo_pipeline():
    pipeline.run_pipeline()  # warm so tool calls inside tests are fast


def test_chain_order_and_provider(monkeypatch):
    monkeypatch.setattr(settings, "gemini_api_key", "k")
    monkeypatch.setattr(settings, "gemini_model", "a")
    monkeypatch.setattr(settings, "gemini_fallback_models", "b, a ,c")
    assert gemini.models() == ["a", "b", "c"]
    assert gemini.provider() == "api-key" and gemini.is_configured()
    monkeypatch.setattr(settings, "gemini_api_key", "")
    monkeypatch.setattr(settings, "gcp_project", "")
    assert gemini.provider() == "none" and not gemini.is_configured()
    monkeypatch.setattr(settings, "gcp_project", "p")
    assert gemini.provider() == "vertex"


def test_happy_path_forces_tools_first_and_records_every_call(fake):
    models = fake({"m1": "ok", "m2": "ok", "m3": "ok"})
    narrative, calls, results, used = gemini.run_agent(SITE)
    assert used == "m1" and narrative.summary == "ok" and narrative.site_specific_checks == ["c1"]
    assert [c["tool"] for c in calls] == ["get_site_metrics", "get_outlook"] and all(c["ok"] for c in calls)
    assert len(results) == 2 and "error" not in results[0]
    # one parallel tool round + one answer = exactly 2 requests; tool use forced on turn 1; SDK auto-calling off
    # MAX_ROUNDS=2: force tools on turn 0 (ANY), forbid on turn 1 (NONE) so the narrative returns fast.
    assert [r["mode"] for r in models.requests] == ["ANY", "NONE"]
    assert all(r["afc_off"] for r in models.requests)
    assert models.requests[1]["n_contents"] == 3  # prompt + model tool-call turn + tool results


def test_overloaded_primary_falls_through_to_next_model(fake):
    models = fake({"m1": 503, "m2": 429, "m3": "ok"})
    narrative, calls, _, used = gemini.run_agent(SITE)
    assert used == "m3" and narrative.summary == "ok" and calls
    assert models.tried == ["m1", "m2", "m3"]


def test_retired_model_404_is_skipped(fake):
    models = fake({"m1": 404, "m2": "ok", "m3": "ok"})
    assert gemini.run_agent(SITE)[3] == "m2" and models.tried == ["m1", "m2"]


def test_model_that_skips_tools_is_not_trusted(fake):
    models = fake({"m1": "no-tools", "m2": "ok", "m3": "ok"})
    _, calls, _, used = gemini.run_agent(SITE)
    assert used == "m2" and calls and models.tried == ["m1", "m2"]


def test_unknown_tool_and_tool_errors_become_data_not_crashes(fake):
    models = fake(
        {
            "m1": [
                _resp(calls=[("get_site_metrics", {"site_id": SITE}), ("made_up_tool", {}), ("get_outlook", {"site_id": "NOPE"})]),
                _resp(text=GOOD),
            ],
            "m2": "ok",
            "m3": "ok",
        }
    )
    _, calls, results, used = gemini.run_agent(SITE)
    assert used == "m1" and models.tried == ["m1"]
    assert [c["ok"] for c in calls] == [True, False, False]
    assert "unknown tool" in results[1]["error"]


def test_tool_loop_is_bounded_and_last_round_forbids_tools(fake):
    # Round 0 forces tools (ANY); round 1 is the last and forbids tools (NONE).
    models = fake(
        {
            "m1": [
                _resp(calls=[("get_site_metrics", {"site_id": SITE})]),
                _resp(text=GOOD),
            ],
            "m2": "ok",
            "m3": "ok",
        }
    )
    _, calls, _, used = gemini.run_agent(SITE)
    assert used == "m1" and len(calls) == 1
    assert [r["mode"] for r in models.requests] == ["ANY", "NONE"]
    assert len(models.requests) == gemini.MAX_ROUNDS


def test_non_transient_error_is_raised_not_swallowed(fake):
    models = fake({"m1": 400, "m2": "ok", "m3": "ok"})
    with pytest.raises(_Err):
        gemini.run_agent(SITE)
    assert models.tried == ["m1"]


def test_all_models_down_raises_so_service_uses_template(fake):
    fake({"m1": 503, "m2": 503, "m3": 504})
    with pytest.raises(_Err):
        gemini.run_agent(SITE)


def test_budget_stops_the_chain(fake, monkeypatch):
    models = fake({"m1": 503, "m2": "ok", "m3": "ok"})
    monkeypatch.setattr(settings, "gemini_budget_s", -1.0)
    with pytest.raises(_Err):
        gemini.run_agent(SITE)
    assert models.tried == ["m1"]


def test_feedback_is_added_to_the_prompt(fake):
    models = fake({"m1": "ok", "m2": "ok", "m3": "ok"})
    gemini.run_agent(SITE, feedback=["number 99 not found in tool data"])
    assert "rejected" in models.requests[0]["prompt"] and "number 99 not found in tool data" in models.requests[0]["prompt"]
    models.requests.clear()
    gemini.run_agent(SITE)
    assert "rejected" not in models.requests[0]["prompt"]