# minutes/services/summarizer.py
import os
import json
import inspect
from typing import Dict, Any, Optional

from openai import OpenAI

# ---- 모델/키 설정 ----
OPENAI_API_KEY = os.getenv("OPENAI_API_KEY")
if not OPENAI_API_KEY:
    raise RuntimeError("OPENAI_API_KEY is not set in environment")

DEFAULT_MODEL = os.getenv("OPENAI_MINUTES_MODEL", "gpt-4o")  # 필요시 .env에서 교체
client = OpenAI(api_key=OPENAI_API_KEY)

# ---- 공통 스키마 ----
SCHEMA: Dict[str, Any] = {
    "type": "object",
    "properties": {
        "meta": {
            "type": "object",
            "properties": {
                "date": {"type": "string"},
                "time": {"type": "string"},
                "location": {"type": "string"},
                "attendees": {"type": "array", "items": {"type": "string"}},
                "project": {"type": "string"},
                "market_area": {"type": "string"},
            },
            "required": ["date", "time", "location", "attendees"],
        },
        "overall_summary": {"type": "string"},
        "topics": {
            "type": "array",
            "items": {
                "type": "object",
                "properties": {
                    "topic": {"type": "string"},
                    "summary": {"type": "string"},
                    "owner": {"type": "string"},
                },
                "required": ["topic", "summary"],
            },
        },
        "decisions": {
            "type": "array",
            "items": {
                "type": "object",
                "properties": {
                    "decision": {"type": "string"},
                    "rationale": {"type": "string"},
                },
                "required": ["decision"],
            },
        },
        "action_items": {
            "type": "array",
            "items": {
                "type": "object",
                "properties": {
                    "owner": {"type": "string"},
                    "task": {"type": "string"},
                    "due": {"type": "string"},
                    "status": {"type": "string", "enum": ["Open", "Blocked", "Done"]},
                    "priority": {"type": "string", "enum": ["High", "Medium", "Low"]},
                },
                "required": ["owner", "task", "due", "status"],
            },
        },
        "next_topics": {"type": "array", "items": {"type": "string"}},
        "risks": {
            "type": "array",
            "items": {
                "type": "object",
                "properties": {
                    "risk": {"type": "string"},
                    "mitigation": {"type": "string"},
                },
                "required": ["risk"],
            },
        },
        "dependencies": {"type": "array", "items": {"type": "string"}},
    },
    "required": ["meta", "overall_summary", "topics", "decisions", "action_items", "next_topics"],
    "additionalProperties": False,
}

SYSTEM_LIVE = (
    "You are an incremental meeting-minutes updater. "
    "Given current minutes(state) and a new segment, update only changed parts. "
    "Keep dates/numbers/names verbatim; if missing, use 'TBD'. "
    "Return a full minutes JSON matching the schema."
)

SYSTEM_FINAL = (
    "You are a meeting-minutes extractor for the full transcript. "
    "Output full JSON matching the schema. No hallucination; verbatim dates/numbers/names."
)

def _responses_supports_json_schema() -> bool:
    """런타임에서 responses.create가 response_format 인자를 지원하는지 확인."""
    try:
        sig = inspect.signature(client.responses.create)
        return "response_format" in sig.parameters
    except Exception:
        return False

def _call_responses_json_schema(system_text: str, user_text: str, model: str) -> Dict[str, Any]:
    """Responses API + JSON Schema (지원되는 경우)."""
    resp = client.responses.create(
        model=model,
        input=[
            {"role": "system", "content": [{"type": "input_text", "text": system_text}]},
            {"role": "user", "content": [{"type": "input_text", "text": user_text}]},
        ],
        response_format={"type": "json_schema", "json_schema": {"name": "Minutes", "schema": SCHEMA}},
        temperature=0.1,
        max_output_tokens=4096,
    )

    # 응답 본문 추출
    txt = None
    if hasattr(resp, "output_text") and isinstance(resp.output_text, str):
        txt = resp.output_text
    else:
        # 호환용: 첫 메시지 텍스트
        try:
            txt = resp.output[0].content[0].text
        except Exception:
            txt = None
    if not txt:
        raise RuntimeError("No text in responses output")

    return json.loads(txt)

def _call_chat_json_object(system_text: str, user_text: str, model: str) -> Dict[str, Any]:
    """
    Chat Completions로 폴백. JSON 객체 강제 후 파이썬에서 스키마 검증(간단).
    """
    cc = client.chat.completions.create(
        model=model,
        response_format={"type": "json_object"},
        # temperature=0.1,
        messages=[
            {"role": "system", "content": (
                f"{system_text}\n"
                "Return strictly a single JSON object only. "
                "The object must follow this JSON Schema (do not include this text in output):\n"
                f"{json.dumps(SCHEMA, ensure_ascii=False)}"
            )},
            {"role": "user", "content": user_text},
        ],
    )
    content = cc.choices[0].message.content
    data = json.loads(content)

    # 최소 필드만 소프트 검증(하드 스키마 검증이 필요하면 jsonschema 패키지를 붙이세요)
    required = ["meta", "overall_summary", "topics", "decisions", "action_items", "next_topics"]
    for k in required:
        if k not in data:
            raise RuntimeError(f"Missing required key in fallback output: {k}")
    return data

def summarize_incremental(current_minutes: Dict[str, Any], new_segment: str, *, model: Optional[str] = None) -> Dict[str, Any]:
    """
    증분 요약: 현재 minutes 상태 + 새로운 발화(new_segment) -> 업데이트된 minutes JSON
    """
    model = model or DEFAULT_MODEL
    user_payload = json.dumps({"state": current_minutes, "new_segment": new_segment}, ensure_ascii=False)

    if _responses_supports_json_schema():
        return _call_responses_json_schema(SYSTEM_LIVE, user_payload, model)
    # 폴백
    return _call_chat_json_object(SYSTEM_LIVE, user_payload, model)

def summarize_final(full_transcript: str, project: Optional[str] = None, market_area: Optional[str] = None, *, model: Optional[str] = None) -> Dict[str, Any]:
    """
    최종 요약: 전체 원문 -> minutes JSON
    """
    model = model or DEFAULT_MODEL
    body = full_transcript
    if project or market_area:
        hint = {"project": project, "market_area": market_area}
        body = f"[META_HINT]{json.dumps(hint, ensure_ascii=False)}\n{full_transcript}"

    if _responses_supports_json_schema():
        return _call_responses_json_schema(SYSTEM_FINAL, body, model)
    # 폴백
    return _call_chat_json_object(SYSTEM_FINAL, body, model)
