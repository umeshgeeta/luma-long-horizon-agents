"""Fold a visible event prefix into retained state with LFM2.5-1.2B-Instruct."""

from __future__ import annotations

import json
import os
import re
from typing import Any

# 4-bit MLX export of LFM2.5-1.2B-Instruct. Same instruct model, sized for a laptop.
MODEL_ID = "LiquidAI/LFM2.5-1.2B-Instruct-MLX-4bit"
SOURCE = "lfm2.5-1.2b-instruct"

_model = None
_tokenizer = None

_SYSTEM = """You compact an agent session into the state that must survive after raw history is hidden.
Reply with one JSON object and no other text.
Use exactly these keys:
{"goal": string, "facts": [string], "open_questions": [string], "decisions": [string]}
Keep the goal unchanged.
facts are short statements that must still be true after the events are hidden.
decisions are choices already made in the events or the prior state.
When an event says who does an action, record that action as a decision. Do not rewrite it into its opposite.
open_questions are unresolved items stated in the events or the prior state. Use an empty array when nothing is unresolved.
Use only the goal, the prior state, and the events. Do not add outside knowledge."""


def compact_state(goal: str, prior: dict[str, Any] | None, events: list[dict[str, Any]]) -> dict[str, Any]:
    prompt_body = _user_prompt(goal, prior or {}, events)
    text = _complete(prompt_body)
    try:
        return _normalize(text, goal)
    except ValueError:
        text = _complete(
            prompt_body
            + "\n\nThe previous reply was not valid JSON. Reply again with only the JSON object."
        )
        return _normalize(text, goal)


def _complete(user: str) -> str:
    model, tokenizer = _load()
    from mlx_lm import generate
    from mlx_lm.sample_utils import make_logits_processors, make_sampler

    messages = [
        {"role": "system", "content": _SYSTEM},
        {"role": "user", "content": user},
    ]
    if getattr(tokenizer, "chat_template", None):
        prompt = tokenizer.apply_chat_template(messages, tokenize=False, add_generation_prompt=True)
    else:
        prompt = _SYSTEM + "\n\n" + user
    return generate(
        model,
        tokenizer,
        prompt=prompt,
        max_tokens=512,
        sampler=make_sampler(temp=0.1, top_k=50, top_p=0.1),
        logits_processors=make_logits_processors(repetition_penalty=1.05),
        verbose=False,
    )


def _load():
    global _model, _tokenizer
    if _model is None:
        os.environ.setdefault("HF_HUB_DISABLE_PROGRESS_BARS", "1")
        os.environ.setdefault("TOKENIZERS_PARALLELISM", "false")
        from mlx_lm import load

        _model, _tokenizer = load(MODEL_ID)
    return _model, _tokenizer


def _user_prompt(goal: str, prior: dict[str, Any], events: list[dict[str, Any]]) -> str:
    prior_view = {
        "goal": prior.get("goal") or goal,
        "facts": list(prior.get("facts") or []),
        "open_questions": list(prior.get("open_questions") or []),
        "decisions": list(prior.get("decisions") or []),
    }
    lines = [f"Goal: {goal}", "", "Prior state:", json.dumps(prior_view), "", "Events:"]
    for event in events:
        kind = event.get("kind") or "observation"
        summary = event.get("summary") or ""
        lines.append(f"- [{kind}] {summary}")
        body = (event.get("body") or "").strip()
        if body:
            lines.append(f"  {body[:400]}")
    return "\n".join(lines)


def _normalize(text: str, goal: str) -> dict[str, Any]:
    match = re.search(r"\{.*\}", text, flags=re.DOTALL)
    if not match:
        raise ValueError("model reply did not contain a JSON object")
    data = json.loads(match.group(0))
    if not isinstance(data, dict):
        raise ValueError("model reply was not a JSON object")
    returned_goal = data.get("goal")
    return {
        "goal": returned_goal.strip() if isinstance(returned_goal, str) and returned_goal.strip() else goal,
        "facts": _strings(data.get("facts")),
        "open_questions": _strings(data.get("open_questions")),
        "decisions": _strings(data.get("decisions")),
        "source": SOURCE,
    }


def _strings(value: Any) -> list[str]:
    if value is None:
        return []
    if isinstance(value, str):
        value = [value]
    if not isinstance(value, list):
        return []
    out = []
    for item in value:
        text = str(item).strip()
        if text:
            out.append(text)
    return out
