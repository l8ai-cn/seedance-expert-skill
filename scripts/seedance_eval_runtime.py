from __future__ import annotations

import json
import re
import urllib.request


API_URL = "https://api.anthropic.com/v1/messages"
ANTHROPIC_VERSION = "2023-06-01"


def call_api(
    system: str,
    user: str,
    model: str,
    api_key: str,
    max_tokens: int = 1500,
) -> str:
    payload = json.dumps(
        {
            "model": model,
            "max_tokens": max_tokens,
            "system": system,
            "messages": [{"role": "user", "content": user}],
        }
    ).encode("utf-8")
    request = urllib.request.Request(API_URL, data=payload, method="POST")
    request.add_header("x-api-key", api_key)
    request.add_header("anthropic-version", ANTHROPIC_VERSION)
    request.add_header("content-type", "application/json")
    with urllib.request.urlopen(request, timeout=120) as response:
        body = json.loads(response.read().decode("utf-8"))
    return "".join(
        block.get("text", "")
        for block in body.get("content", [])
        if block.get("type") == "text"
    )


def judge(
    case: dict,
    response: str,
    model: str,
    api_key: str,
    rubric: str,
    *,
    sequence: bool,
) -> dict:
    scale = "0-4" if sequence else "0-3"
    extra = ""
    if case.get("forbidden_behaviors"):
        extra += "\nForbidden behaviors (any present => fail):\n- " + "\n- ".join(
            case["forbidden_behaviors"]
        )
    if case.get("required_output_sections"):
        extra += "\nRequired output sections:\n- " + "\n- ".join(
            case["required_output_sections"]
        )
    system = (
        "You are a strict eval judge for an AI video-prompting skill. Apply the rubric "
        "exactly and return ONLY a JSON object, no prose. Be skeptical: reward only "
        "behavior that is actually present."
    )
    user = (
        f"RUBRIC:\n{rubric}\n\nUse the {scale} scale for this case.\n"
        f"CASE PROMPT:\n{case['prompt']}\n\n"
        f"ASSERTIONS (each must be satisfied):\n- "
        + "\n- ".join(case["assertions"])
        + extra
        + "\n\n"
        f"CANDIDATE RESPONSE TO GRADE:\n{response}\n\n"
        'Return JSON: {"assertion_scores":[{"assertion":str,"met":bool}],'
        '"overall_score":int,"pass":bool,"notes":str}. '
        f"overall_score is on the {scale} scale."
    )
    raw = call_api(system, user, model, api_key, max_tokens=900)
    match = re.search(r"\{.*\}", raw, re.S)
    if not match:
        return _failed_judgment("judge returned no JSON")
    try:
        return json.loads(match.group(0))
    except json.JSONDecodeError:
        return _failed_judgment("unparseable judge JSON")


def _failed_judgment(notes: str) -> dict:
    return {
        "overall_score": 0,
        "pass": False,
        "notes": notes,
        "assertion_scores": [],
    }
