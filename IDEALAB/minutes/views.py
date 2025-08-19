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
    - 모든 TranscriptSegment 취합 → summarize_final → 최종 스냅샷 저장 → WS 방송
    """
    def post(self, request, meeting_id: int):
        meeting = get_object_or_404(Meeting, pk=meeting_id)
        ser = FinalizeSerializer(data=request.data)
        ser.is_valid(raise_exception=True)

        project = ser.validated_data.get("project") or meeting.project
        market_area = ser.validated_data.get("market_area") or meeting.market_area

        segs = TranscriptSegment.objects.filter(meeting=meeting).order_by("start_ms")
        full_text = "\n".join(s.text for s in segs)

        try:
            final_json = summarize_final(full_text, project=project, market_area=market_area)
        except Exception as e:
            return Response({"detail": f"summarize_final error: {e}"}, status=500)

        saved = save_final_minutes(meeting, final_json)

        # WebSocket 방송 (없으면 조용히 패스)
        try:
            layer = get_channel_layer()
            if layer:
                async_to_sync(layer.group_send)(
                    f"meeting_{meeting.id}",
                    {"type": "minutes_update", "payload": {"provisional": False, "minutes": saved}}
                )
        except Exception:
            pass

        return Response(saved, status=status.HTTP_200_OK)
