from rest_framework import serializers

class KeywordExtractRequestSerializer(serializers.Serializer):
    # 실시간/최종 모두 재사용: text만 보내면 됨
    text = serializers.CharField()
    source = serializers.ChoiceField(choices=["realtime", "final"], default="realtime")


class KeywordLogResponseSerializer(serializers.Serializer):
    id = serializers.IntegerField()
    source = serializers.CharField()
    raw_text = serializers.CharField()
    keywords = serializers.JSONField()
    created_at = serializers.DateTimeField()
