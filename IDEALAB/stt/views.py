# stt/views.py
from rest_framework.views import APIView
from rest_framework.response import Response
from rest_framework import status

from django.shortcuts import get_object_or_404
from django.conf import settings

from .serializers import STTChunkSerializer
from .models import TranscriptSegment
from meetings.models import Meeting
from meetings.serializers import MeetingCreateSerializer

# LLM 키워드 추출 (rules 모듈 기준)
from keywords.services.rules import extract_keywords_llm, save_keywords_log

# 실시간 방송(선택)
from asgiref.sync import async_to_sync
from channels.layers import get_channel_layer

import os


def _is_incremental_enabled() -> bool:
    env_flag = os.getenv("MINUTES_INCREMENTAL_ENABLED")
    if env_flag is not None:
        return env_flag.strip() in ("1", "true", "True", "YES", "yes")
    return getattr(settings, "MINUTES_INCREMENTAL_ENABLED", False)


class CreateMeetingView(APIView):
    def post(self, request):
        ser = MeetingCreateSerializer(data=request.data)
        ser.is_valid(raise_exception=True)
        m = Meeting.objects.create(
            title=ser.validated_data["title"],
            project=ser.validated_data.get("project") or "",
            market_area=ser.validated_data.get("market_area") or "",
        )
        return Response({
            "id": m.id,
            "title": m.title,
            "project": m.project,
            "market_area": m.market_area,
        }, status=status.HTTP_201_CREATED)


class STTChunkView(APIView):
    """
    POST /api/meetings/<meeting_id>/stt-chunk
    body: {text, start_ms, end_ms, speaker?}

    - 항상: TranscriptSegment 저장
    - 옵션: 증분 요약(LLM) -> 임시 minutes 스냅샷 저장/방송  (MINUTES_INCREMENTAL_ENABLED=1)
    - 항상: 키워드 추출 -> 로그 저장 -> WS 방송
    - 응답: { ok, segment_id, minutes, summarized, keywords, cards, reason? }
    """
    def post(self, request, meeting_id: int):
        meeting = get_object_or_404(Meeting, pk=meeting_id)

        ser = STTChunkSerializer(data=request.data)
        ser.is_valid(raise_exception=True)

        seg = TranscriptSegment.objects.create(
            meeting=meeting,
            start_ms=ser.validated_data["start_ms"],
            end_ms=ser.validated_data["end_ms"],
            speaker=ser.validated_data.get("speaker") or "",
            text=ser.validated_data["text"],
        )

        minutes_payload = None
        summarized = False
        reason = None

        # --- (옵션) 증분 요약 한 번만 ---
        if _is_incremental_enabled():
            try:
                from minutes.models import MinutesSnapshot
                from minutes.services.summarizer import summarize_incremental
                from minutes.services.storage import save_live_minutes

                latest = (
                    MinutesSnapshot.objects
                    .filter(meeting=meeting, is_final=False)
                    .order_by("-id")
                    .first()
                )
                current = latest.payload if latest else {
                    "meta": {
                        "date": "TBD",
                        "time": "TBD",
                        "location": "TBD",
                        "attendees": [],
                        "project": meeting.project,
                        "market_area": meeting.market_area,
                    },
                    "overall_summary": "",
                    "topics": [],
                    "decisions": [],
                    "action_items": [],
                    "next_topics": [],
                    "risks": [],
                    "dependencies": [],
                }

                updated = summarize_incremental(current, seg.text)
                minutes_payload = save_live_minutes(meeting, updated)
                summarized = True

                # WS: minutes
                try:
                    layer = get_channel_layer()
                    if layer:
                        async_to_sync(layer.group_send)(
                            f"meeting_{meeting.id}",
                            {"type": "minutes_update",
                             "payload": {"provisional": True, "minutes": minutes_payload}}
                        )
                except Exception:
                    pass

            except Exception as e:
                # 요약 실패해도 키워드는 계속
                reason = f"summarize_error: {e}"

        else:
            reason = "incremental_disabled"

        # --- (항상) 키워드 추출 한 번만 ---
        keywords, cards = [], []
        try:
            # rules.extract_keywords_llm(text) 는 {entities, metrics, api_hints} 반환
            kw_res = extract_keywords_llm(seg.text)

            entities  = kw_res.get("entities", []) or []
            metrics   = kw_res.get("metrics", []) or []
            api_hints = kw_res.get("api_hints", []) or []

            # 응답용 매핑
            keywords = list(dict.fromkeys([*entities, *metrics]))  # 중복 제거 + 순서 유지
            cards = [{"slug": s} for s in api_hints]

            # 로그 저장 (현재 rules.save_keywords_log 시그니처: meta 없음)
            try:
                save_keywords_log(
                    meeting=meeting,
                    source="live",
                    raw_text=seg.text,
                    keywords={"entities": entities, "metrics": metrics, "api_hints": api_hints},
                )
            except Exception:
                pass

            # WS: keywords
            try:
                layer = get_channel_layer()
                if layer:
                    async_to_sync(layer.group_send)(
                        f"meeting_{meeting.id}",
                        {"type": "keywords_update",
                         "payload": {"source": "live", "keywords": keywords, "cards": cards}}
                    )
            except Exception:
                pass

        except Exception as e:
            # 키워드 실패는 minutes만 제공
            reason = reason or f"keywords_error: {e}"

        # --- 최종 응답 ---
        return Response({
            "ok": True,
            "segment_id": seg.id,
            "minutes": minutes_payload,
            "summarized": summarized,
            "keywords": keywords,
            "cards": cards,
            "reason": reason,
        }, status=201)
    