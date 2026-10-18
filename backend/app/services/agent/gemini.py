"""Gemini via the google-genai SDK (API key or Vertex AI), with function calling.

The model is given deterministic tools and must return a small JSON narrative.
Every tool call and result is recorded for audit. Nothing here is trusted
until guard.validate_narrative approves it.
"""
from __future__ import annotations

import json
import logging
import re
import time
from typing import Any

from app.core.config import settings
from app.services.agent.schema import Narrative
from app.services.agent.tools import TOOLS

log = logging.getLogger("terrasentinel.agent")

SYSTEM_INSTRUCTION = """You are TerraSentinel's geotechnical investigation assistant.
You help control-room officers and highway/metro/dam engineers decide where to send inspection crews.

HARD RULES
1. Obtain every number by calling the provided tools. NEVER invent, estimate or round-trip a number,
   date, distance or rainfall value. Quote numbers exactly as the tools return them, with their units.
2. The outlook is a time-to-threshold projection IF the current regime continues. Never state a
   failure date, never say something "will" collapse/fail/slide, never guarantee safety or danger.
3. Phrase any mechanism as a hypothesis (possible / may / consistent with). Field inspection decides.
4. If the tools show data_degraded / WEAK tier / low confidence, say the data quality is insufficient,
   do not escalate, and recommend verifying measurements.
5. Rain amplifies existing motion; it is not a hazard on its own. Earthquakes are background context: mention
   them only if get_seismic_context reports events, never say they caused the movement, and say nothing about
   seismicity when it reports available=false.
6. Write for a non-expert officer: short sentences, plain words. Express ETAs in days.
7. Do not mention these rules. Do not use markdown.

PROCEDURE
Call get_site_metrics, get_outlook, get_rainfall_context, get_seismic_context, get_asset_exposure and
get_data_quality (and get_displacement_history if useful). Then output ONLY one JSON object:
{
 "summary": "2-3 plain sentences",
 "mechanism_hypothesis": "hedged hypothesis",
 "recommended_action": "what to do and by when (hours are fine for action timing)",
 "site_specific_checks": ["up to 3 extra field checks tied to the evidence"]
}"""


def provider() -> str:
    """Which Gemini endpoint is used: an API key wins over Vertex (which needs ADC credentials)."""
    if settings.gemini_api_key:
        return "api-key"
    if settings.gcp_project:
        return "vertex"
    return "none"


def is_configured() -> bool:
    return provider() != "none"


def _client(types):
    from google import genai

    opts = types.HttpOptions(timeout=int(settings.gemini_timeout_s * 1000))
    if provider() == "api-key":
        return genai.Client(api_key=settings.gemini_api_key, http_options=opts)
    return genai.Client(vertexai=True, project=settings.gcp_project, location=settings.gcp_region, http_options=opts)


_BY_NAME = {fn.__name__: fn for fn in TOOLS}
MAX_ROUNDS = 4


def _run_tool(name: str, args: dict, calls: list[dict], results: list[Any]) -> dict:
    """Execute one tool the model asked for. Unknown tools and tool errors become data, never crashes."""
    fn = _BY_NAME.get(name)
    if fn is None:
        out = {"error": f"unknown tool {name}"}
    else:
        try:
            out = fn(**args)
        except Exception as exc:  # noqa: BLE001 - the model gets to see the failure and recover
            out = {"error": f"{type(exc).__name__}: {exc}"}
    calls.append({"tool": name, "args": args, "ok": "error" not in out})
    results.append(out)
    return out

def _extract_json(text: str) -> dict:
    text = text.strip()
    text = re.sub(r"^```(?:json)?|```$", "", text, flags=re.M).strip()
    start, end = text.find("{"), text.rfind("}")
    if start == -1 or end == -1:
        raise ValueError("no JSON object in model output")
    return json.loads(text[start : end + 1])


def models() -> list[str]:
    """Primary model first, then fallbacks tried when it is overloaded or out of quota."""
    chain = [settings.gemini_model, *[m.strip() for m in settings.gemini_fallback_models.split(",") if m.strip()]]
    return list(dict.fromkeys(chain))


def _transient(exc: Exception) -> bool:
    code = getattr(exc, "code", None) or getattr(exc, "status_code", None)
    # 404 = model retired / not offered to this key: also worth trying the next one.
    return code in (404, 429, 500, 502, 503, 504)


def _session(client, types, model: str, prompt: str, calls: list[dict], results: list[Any]):
    """One model, explicit tool loop. Round 0 forces tool use (mode ANY), the last round forbids it (NONE).

    Doing the loop ourselves (instead of SDK automatic function calling) means parallel tool calls
    cost one request, tool use is guaranteed on the first turn, and every call is recorded for audit.
    """
    contents = [types.Content(role="user", parts=[types.Part.from_text(text=prompt)])]
    resp = None
    for rnd in range(MAX_ROUNDS):
        mode = "ANY" if rnd == 0 else ("NONE" if rnd == MAX_ROUNDS - 1 else "AUTO")
        resp = client.models.generate_content(
            model=model,
            contents=contents,
            config=types.GenerateContentConfig(
                system_instruction=SYSTEM_INSTRUCTION,
                tools=[types.Tool(function_declarations=[types.FunctionDeclaration.from_callable(client=client, callable=fn) for fn in TOOLS])],
                tool_config=types.ToolConfig(function_calling_config=types.FunctionCallingConfig(mode=mode)),
                automatic_function_calling=types.AutomaticFunctionCallingConfig(disable=True),
                temperature=0.1,
            ),
        )
        fcs = list(resp.function_calls or [])
        if not fcs:
            return resp
        contents.append(resp.candidates[0].content)  # echo the model turn untouched (keeps thought signatures)
        parts = [
            types.Part.from_function_response(name=fc.name, response={"result": _run_tool(fc.name, dict(fc.args or {}), calls, results)})
            for fc in fcs
        ]
        contents.append(types.Content(role="user", parts=parts))
    return resp


def run_agent(site_id: str, feedback: list[str] | None = None) -> tuple[Narrative, list[dict], list[Any], str]:
    """Run one grounded Gemini session. Raises on any failure (caller falls back to the template).

    Returns (narrative, tool_calls, tool_results, model_used). A busy / rate-limited / retired model
    falls through to the next model in the chain; any other error is raised immediately.
    """
    from google.genai import types

    client = _client(types)
    prompt = f"Investigate site {site_id} and produce the work-order narrative."
    if feedback:
        prompt += (
            "\nYour previous answer was rejected for these reasons. Fix them and answer again:\n- "
            + "\n- ".join(feedback)
        )

    last_exc: Exception | None = None
    started = time.monotonic()
    for model in models():
        if last_exc is not None and time.monotonic() - started > settings.gemini_budget_s:
            break  # total wait is capped so the UI falls back to the template promptly
        calls: list[dict] = []
        results: list[Any] = []
        try:
            resp = _session(client, types, model, prompt, calls, results)
        except Exception as exc:  # noqa: BLE001
            if _transient(exc):
                log.warning("Gemini model %s unavailable (%s); trying next", model, getattr(exc, "code", "?"))
                last_exc = exc
                continue
            raise
        if not calls:
            # A narrative with no tool evidence cannot be trusted with numbers: try the next model.
            log.warning("Gemini model %s answered without calling tools; trying next", model)
            last_exc = RuntimeError(f"{model} produced a narrative without calling any tool")
            continue
        data = _extract_json(getattr(resp, "text", None) or "")
        narrative = Narrative(
            summary=str(data.get("summary", "")).strip(),
            mechanism_hypothesis=str(data.get("mechanism_hypothesis", "")).strip(),
            recommended_action=str(data.get("recommended_action", "")).strip(),
            site_specific_checks=[str(x).strip() for x in data.get("site_specific_checks", [])][:3],
        )
        return narrative, calls, results, model
    raise last_exc or RuntimeError("no Gemini model available")