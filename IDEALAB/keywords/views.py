from rest_framework.views import APIView
from rest_framework.response import Response
from rest_framework import status
from django.shortcuts import get_object_or_404

from meetings.models import Meeting
from .models import KeywordLog
from .serializers import KeywordExtractRequestSerializer, KeywordLogResponseSerializer
from .services.rules import extract_keywords_llm, save_keywords_log

# (선택) 실시간 방송
from asgiref.sync import async_to_sync
from channels.layers import get_channel_layer


class ExtractKeywordsView(APIView):
    """
    POST /api/meetings/<int:meeting_id>/keywords/extract
    body: { text: str, source: "realtime"|"final" }
    """
    def post(self, request, meeting_id: int):
        meeting = get_object_or_404(Meeting, pk=meeting_id)
        ser = KeywordExtractRequestSerializer(data=request.data)
        ser.is_valid(raise_exception=True)

        text = ser.validated_data["text"]
        source = ser.validated_data.get("source", "realtime")

        keywords = extract_keywords_llm(text)
        log = save_keywords_log(meeting, source, text, keywords)

        # WebSocket으로도 푸시
        try:
            layer = get_channel_layer()
            if layer:
                async_to_sync(layer.group_send)(
                    f"meeting_{meeting.id}",
                    {
                        "type": "keywords_update",
                        "payload": {
                            "source": source,
                            "keywords": keywords,
                            "log_id": log.id,
                        },
                    },
                )
        except Exception:
            pass

        return Response(
            {
                "ok": True,
                "log_id": log.id,
                "keywords": keywords,
            },
            status=status.HTTP_201_CREATED,
        )


class ListKeywordLogsView(APIView):
    """
    GET /api/meetings/<int:meeting_id>/keywords
    최근 키워드 로그 조회(페이지네이션 생략)
    """
    def get(self, request, meeting_id: int):
        meeting = get_object_or_404(Meeting, pk=meeting_id)
        logs = KeywordLog.objects.filter(meeting=meeting).order_by("-id")[:100]
        data = [
            {
                "id": l.id,
                "source": l.source,
                "raw_text": l.raw_text,
                "keywords": l.keywords,
                "created_at": l.created_at,
            }
            for l in logs
        ]
        return Response(data, status=200)
    