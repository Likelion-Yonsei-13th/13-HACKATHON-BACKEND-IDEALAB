from rest_framework import serializers

class STTChunkSerializer(serializers.Serializer):
    text = serializers.CharField()
    start_ms = serializers.IntegerField()
    end_ms = serializers.IntegerField()
    speaker = serializers.CharField(required=False, allow_blank=True, allow_null=True)
