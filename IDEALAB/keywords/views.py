# keywords/views.py
from rest_framework.views import APIView
from rest_framework.response import Response
from rest_framework import status
from django.shortcuts import get_object_or_404

from meetings.models import Meeting
from .models import KeywordLog
from .serializers import KeywordExtractRequestSerializer  # KeywordLogResponseSerializer는 미사용
from .services.rules import extract_keywords_llm, save_keywords_log
from .services.linker import build_api_suggestions

# (선택) 실시간 방송
from asgiref.sync import async_to_sync
from channels.layers import get_channel_layer


class ExtractKeywordsView(APIView):
    """
    POST /api/meetings/<int:meeting_id>/keywords/extract
    body: { text: str, source: "realtime"|"final" }

    - LLM으로 키워드 추출
    - 화이트리스트 규칙 기반 api_hints 생성 (rules.py)
    - api_suggestions(analytics API 호출 후보) 구성
    - 로그 저장 및 WebSocket 브로드캐스트
    """
    def post(self, request, meeting_id: int):
        meeting = get_object_or_404(Meeting, pk=meeting_id)
        ser = KeywordExtractRequestSerializer(data=request.data)
        ser.is_valid(raise_exception=True)

        text = ser.validated_data["text"]
        source = ser.validated_data.get("source", "realtime")

        # 1) 키워드 추출 (rules.py)
        keywords = extract_keywords_llm(text)

        # 2) analytics API 제안 생성 (프론트에서 바로 호출 가능)
        api_suggestions = build_api_suggestions(
            entities=keywords.get("entities", []),
            api_hints=keywords.get("api_hints", []),
        )

        # 3) 로그 저장
        log = save_keywords_log(meeting, source, text, keywords)

        # 4) (선택) WebSocket 알림
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
                            "api_suggestions": api_suggestions,
                            "log_id": log.id,
                        },
                    },
                )
        except Exception:
            # 소켓 실패는 API 실패로 취급하지 않음
            pass

        return Response(
            {
                "ok": True,
                "log_id": log.id,
                "keywords": keywords,
                "api_suggestions": api_suggestions,
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
    