#minutes/views.py
from rest_framework.views import APIView
from rest_framework.response import Response
from rest_framework import status

from django.shortcuts import get_object_or_404

from stt.models import TranscriptSegment
from meetings.models import Meeting
from minutes.models import MinutesSnapshot
from .serializers import FinalizeSerializer
from minutes.services.summarizer import summarize_final
from minutes.services.storage import save_final_minutes

from keywords.services.rules import extract_keywords_llm, save_keywords_log

# 실시간 방송(선택)
from asgiref.sync import async_to_sync
from channels.layers import get_channel_layer


class GetLiveMinutesView(APIView):
    """
    GET /api/meetings/<meeting_id>/minutes/live
    """
    def get(self, request, meeting_id: int):
        meeting = get_object_or_404(Meeting, pk=meeting_id)
        latest = MinutesSnapshot.objects.filter(meeting=meeting, is_final=False).order_by("-id").first()
        return Response(latest.payload if latest else {}, status=200)


class GetFinalMinutesView(APIView):
    """
    GET /api/meetings/<meeting_id>/minutes/final
    """
    def get(self, request, meeting_id: int):
        meeting = get_object_or_404(Meeting, pk=meeting_id)
        latest = MinutesSnapshot.objects.filter(meeting=meeting, is_final=True).order_by("-id").first()
        return Response(latest.payload if latest else {}, status=200)


class FinalizeView(APIView):
    """
    POST /api/meetings/<meeting_id>/finalize
    body: {project?, market_area?}

    - 모든 TranscriptSegment 취합 → summarize_final → 최종 스냅샷 저장
    - 전체 텍스트에서 키워드/카드 추출 → 로그 저장
    - (선택) WebSocket으로 최종 상태 브로드캐스트
    """
    def post(self, request, meeting_id: int):
        meeting = get_object_or_404(Meeting, pk=meeting_id)

        # 요청 바디 파싱
        ser = FinalizeSerializer(data=request.data)
        ser.is_valid(raise_exception=True)
        project = ser.validated_data.get("project") or meeting.project
        market_area = ser.validated_data.get("market_area") or meeting.market_area

        # 전체 발화 텍스트 조립
        segs = TranscriptSegment.objects.filter(meeting=meeting).order_by("start_ms")
        full_text = "\n".join(s.text for s in segs)

        # 1) 최종 요약 생성 + 저장
        try:
            final_minutes = summarize_final(full_text, project=project, market_area=market_area)
        except Exception as e:
            return Response({"detail": f"summarize_final error: {e}"}, status=status.HTTP_500_INTERNAL_SERVER_ERROR)

        saved_minutes = save_final_minutes(meeting, final_minutes)

        # 2) 키워드/카드 추출 + 로그 저장
        keywords = []
        cards = []
        try:
            # ✅ 시그니처 맞추기: meeting_id 인자 제거
            kw_res = extract_keywords_llm(full_text)  # returns {entities, metrics, intents, api_hints}

            # ✅ 포맷 매핑: 프론트에서 쓰기 좋은 형태로 변환
            entities = kw_res.get("entities", []) or []
            metrics  = kw_res.get("metrics", []) or []
            api_hints = kw_res.get("api_hints", []) or []

            # 프론트용
            keywords = sorted(set([*entities, *metrics]))
            cards = [{"slug": s} for s in api_hints]

            # ✅ 로그에는 원본 dict(kw_res) 그대로 저장하는 게 제일 깔끔
            try:
                save_keywords_log(
                    meeting=meeting,
                    source="final",
                    raw_text=full_text,
                    keywords=kw_res  # dict 전체 저장
                )
            except Exception:
                pass
        except Exception:
            pass

        # 3) WebSocket 방송 (있으면)
        try:
            layer = get_channel_layer()
            if layer:
                # 최종 회의록 업데이트
                async_to_sync(layer.group_send)(
                    f"meeting_{meeting.id}",
                    {"type": "minutes_update",
                     "payload": {"provisional": False, "minutes": saved_minutes}}
                )
                # 키워드/카드 업데이트
                async_to_sync(layer.group_send)(
                    f"meeting_{meeting.id}",
                    {"type": "keywords_update",
                     "payload": {"source": "final", "keywords": keywords, "cards": cards}}
                )
        except Exception:
            pass

        # 최종 응답
        return Response(
            {
                "ok": True,
                "minutes": saved_minutes,
                "keywords": keywords,
                "cards": cards,
            },
            status=status.HTTP_200_OK,
        )
