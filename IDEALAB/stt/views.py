from rest_framework.views import APIView
from rest_framework.response import Response
from rest_framework import status

from django.shortcuts import get_object_or_404
from django.conf import settings

from .serializers import STTChunkSerializer
from .models import TranscriptSegment
from meetings.models import Meeting
from meetings.serializers import MeetingCreateSerializer

# 실시간 방송(선택)
from asgiref.sync import async_to_sync
from channels.layers import get_channel_layer

import os


def _is_incremental_enabled() -> bool:
    """
    증분 요약(LLM)을 켜고/끄는 스위치.
    - 환경변수 MINUTES_INCREMENTAL_ENABLED=1 이면 켬
    - settings.MINUTES_INCREMENTAL_ENABLED=True 이면 켬
    (환경변수가 우선)
    """
    env_flag = os.getenv("MINUTES_INCREMENTAL_ENABLED")
    if env_flag is not None:
        return env_flag.strip() in ("1", "true", "True", "YES", "yes")
    return getattr(settings, "MINUTES_INCREMENTAL_ENABLED", False)


class CreateMeetingView(APIView):
    """
    POST /api/meetings
    body: {title, project?, market_area?}
    resp: {id, title, project, market_area}
    """
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

    역할 분리:
    - 기본: TranscriptSegment 저장만 (STT 결과 누적 저장)
    - 옵션: 증분 요약(LLM) 실행 -> 임시 minutes 스냅샷 저장/방송
      * MINUTES_INCREMENTAL_ENABLED=1 인 경우에만 수행
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

        # --- 기본 동작: 세그먼트 저장 결과만 반환 ---
        response_payload = {
            "ok": True,
            "segment_id": seg.id,
            "minutes": None,      # 기본은 None (요약 안 함)
            "summarized": False,  # 요약 실행 여부 플래그
        }

        # --- 옵션: 증분 요약 ---
        if _is_incremental_enabled():
            try:
                # minutes 관련 의존성은 "옵션"일 때만 import (순환/마이그레 에러 회피)
                from minutes.models import MinutesSnapshot
                from minutes.services.summarizer import summarize_incremental
                from minutes.services.storage import save_live_minutes

                # 현재 임시 minutes 상태 불러오기
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

                # 증분 요약 실행
                updated = summarize_incremental(current, seg.text)

                # 임시 스냅샷 저장
                merged = save_live_minutes(meeting, updated)

                # WebSocket 방송 (있으면 전송, 에러는 무시)
                try:
                    layer = get_channel_layer()
                    if layer:
                        async_to_sync(layer.group_send)(
                            f"meeting_{meeting.id}",
                            {"type": "minutes_update",
                             "payload": {"provisional": True, "minutes": merged}}
                        )
                except Exception:
                    pass

                response_payload["minutes"] = merged
                response_payload["summarized"] = True

            except Exception as e:
                # 요약 실패는 전체 500으로 만들지 말고, STT 저장 성공만 응답
                response_payload["summarized"] = False
                response_payload["minutes"] = None
                response_payload["summarize_error"] = str(e)

        return Response(response_payload, status=201)
