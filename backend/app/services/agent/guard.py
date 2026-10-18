"""Post-generation validation for LLM narrative text.

The prompt tells Gemini not to invent numbers. This module *enforces* it:
every figure in the narrative must match a value that a tool returned, no
failure-date / certainty language is allowed, and hypotheses must be hedged.
Anything that fails is rejected and replaced by the deterministic template.
"""
from __future__ import annotations

import re
from typing import Any, Iterable

from app.services.agent.schema import Narrative, Validation

NUM_RE = re.compile(r"(?<![\w.])-?\d+(?:\.\d+)?")
ISO_DATE_RE = re.compile(r"\b\d{4}-\d{2}-\d{2}\b")
# Units that mark a number as a *data claim* (must match a tool value).
DATA_UNIT_RE = re.compile(r"^\s*(?:mm(?:/(?:month|yr|year|day))?|days?|x\b|×|%|km\b|m\b|points?|epochs?)", re.I)
ACTION_UNIT_RE = re.compile(r"^\s*(?:hours?|hrs?|h\b)", re.I)

BANNED = [
    r"\bwill\s+(?:collapse|fail|slide|occur|happen|break|give way)\b",
    r"\bguarantee[sd]?\b",
    r"\bcertain(?:ly)?\s+(?:to\s+)?(?:fail|collapse|slide)\b",
    r"\bimminent\s+(?:collapse|failure)\b",
    r"\binevitabl[ey]\b",
    r"\bpredict(?:s|ed|ion)?\s+(?:the\s+)?(?:exact|failure|collapse)\b",
    r"\bexact\s+(?:date|time|day)\b",
    r"\bfailure\s+date\b",
    r"\bno\s+risk\b",
    r"\bcompletely\s+safe\b",
]
HEDGES = re.compile(r"hypothes|possible|possibly|may\b|might|could|likely|suggest|consistent with|potential", re.I)
DEGRADED_WORDS = re.compile(r"quality|coherence|insufficient|unreliable|verify|low confidence|degraded|not reliable", re.I)


def _leaves(obj: Any) -> Iterable[float]:
    if isinstance(obj, bool):
        return
    if isinstance(obj, (int, float)):
        yield float(obj)
    elif isinstance(obj, dict):
        for v in obj.values():
            yield from _leaves(v)
    elif isinstance(obj, (list, tuple)):
        for v in obj:
            yield from _leaves(v)


def _strings(obj: Any) -> Iterable[str]:
    if isinstance(obj, str):
        yield obj
    elif isinstance(obj, dict):
        for v in obj.values():
            yield from _strings(v)
    elif isinstance(obj, (list, tuple)):
        for v in obj:
            yield from _strings(v)


def allowed_from_tools(tool_results: list[Any]) -> tuple[set[float], set[str]]:
    nums: set[float] = set()
    dates: set[str] = set()
    for r in tool_results:
        for v in _leaves(r):
            nums.add(abs(v))
        for s in _strings(r):
            dates.update(ISO_DATE_RE.findall(s))
            # numbers embedded in tool strings (e.g. state_reasons) are also legitimate
            for n in NUM_RE.findall(ISO_DATE_RE.sub(" ", s)):
                try:
                    nums.add(abs(float(n)))
                except ValueError:
                    pass
    return nums, dates


def _matches(n: float, allowed: set[float]) -> bool:
    n = abs(n)
    for a in allowed:
        if abs(n - a) <= max(0.051, 0.01 * a):
            return True
        if float(n).is_integer() and round(a) == n:  # integer rounding of a tool value
            return True
    return False


def _text_fields(n: Narrative) -> list[tuple[str, str]]:
    out = [("summary", n.summary), ("mechanism_hypothesis", n.mechanism_hypothesis), ("recommended_action", n.recommended_action)]
    out += [(f"site_specific_checks[{i}]", t) for i, t in enumerate(n.site_specific_checks)]
    return out


def validate_narrative(
    narrative: Narrative,
    tool_results: list[Any],
    tier: str,
    site_id: str,
    extra_ignore: Iterable[str] = (),
) -> Validation:
    issues: list[str] = []
    allowed_nums, allowed_dates = allowed_from_tools(tool_results)
    checked = 0

    for field, text in _text_fields(narrative):
        # 1) dates first, so they can never be mistaken for identifiers
        for d in ISO_DATE_RE.findall(text):
            checked += 1
            if d not in allowed_dates:
                issues.append(f"{field}: date {d} not present in tool data")
        cleaned = ISO_DATE_RE.sub(" ", text)

        # 2) strip identifiers that legitimately contain digits (e.g. NH58-DEMO-010).
        #    A token must contain a LETTER to count as an id; otherwise a fabricated
        #    range such as "10-15" or "4.75-5.00" would be hidden from the number check.
        cleaned = cleaned.replace(site_id, " ")
        for ig in extra_ignore:
            cleaned = cleaned.replace(ig, " ")
        cleaned = re.sub(r"(?<![\w.])(?=[A-Z0-9-]*[A-Z])[A-Z0-9]+(?:-[A-Z0-9]+)+(?![\w.])", " ", cleaned)

        for m in NUM_RE.finditer(cleaned):
            raw = m.group(0)
            tail = cleaned[m.end() : m.end() + 14]
            try:
                val = float(raw)
            except ValueError:
                continue
            if ACTION_UNIT_RE.match(tail):  # "within 48 hours" is a recommendation, not a measurement
                continue
            if val in (1.0, 2.0, 3.0) and not DATA_UNIT_RE.match(tail):  # "top 3 checks", "2 steps"
                continue
            checked += 1
            if not _matches(val, allowed_nums):
                issues.append(f"{field}: number {raw} not found in tool data")

        for pat in BANNED:
            if re.search(pat, text, re.I):
                issues.append(f"{field}: forbidden certainty language ({pat})")

    if not HEDGES.search(narrative.mechanism_hypothesis):
        issues.append("mechanism_hypothesis: must be worded as a hypothesis (no hedging term found)")
    if tier == "WEAK" and not DEGRADED_WORDS.search(narrative.summary):
        issues.append("summary: WEAK-tier site must state the data-quality limitation")
    if not narrative.summary.strip() or not narrative.recommended_action.strip():
        issues.append("empty required narrative field")

    return Validation(passed=not issues, issues=issues[:12], numbers_checked=checked)
