from rest_framework import serializers
from .models import Meeting, Block, BlockRevision, Attachment

class MeetingCreateSerializer(serializers.ModelSerializer):
    class Meta:
        model = Meeting
        fields = ("id","title","project","market_area","scheduled_time","description")

class MeetingSerializer(MeetingCreateSerializer):
    class Meta(MeetingCreateSerializer.Meta):
        fields = MeetingCreateSerializer.Meta.fields + ("owner_id","created_at","updated_at","ended_at")

# ---------- Blocks ----------
class BlockCreateSerializer(serializers.ModelSerializer):
    class Meta:
        model = Block
        # meeting은 URL로만 주입
        fields = ("id","parent_block","order_no","type","level","text","rich_payload")

    def validate(self, attrs):
        if attrs.get("type") == "table":
            payload = attrs.get("rich_payload") or {}
            if not isinstance(payload.get("cols"), list):
                raise serializers.ValidationError({"rich_payload": "cols(list) is required"})
            if not isinstance(payload.get("rows"), list):
                raise serializers.ValidationError({"rich_payload": "rows(list) is required"})
            payload.setdefault("header", True)
            payload.setdefault("colWidths", [None]*len(payload["cols"]))
            payload.setdefault("merges", [])
            attrs["rich_payload"] = payload
        return attrs

class BlockUpdateSerializer(serializers.ModelSerializer):
    # version 제거
    class Meta:
        model = Block
        fields = ("text","level","rich_payload")

class BlockSerializer(serializers.ModelSerializer):
    meeting = serializers.PrimaryKeyRelatedField(read_only=True)
    class Meta:
        model = Block
        fields = ("id","meeting","parent_block","order_no","type","level","text",
                  "rich_payload","updated_by","updated_at")  # version 제거

class BlockRevisionSerializer(serializers.ModelSerializer):
    class Meta:
        model = BlockRevision
        fields = ("id","block","version","snapshot","edited_by","edited_at")

# ---------- Attachments ----------
class AttachmentCreateSerializer(serializers.ModelSerializer):
    class Meta:
        model = Attachment
        fields = ("id","block","file_url","mime_type","size")

    def validate(self, attrs):
        meeting_pk = self.context.get("meeting_pk")
        blk = attrs.get("block")
        if blk and meeting_pk and blk.meeting_id != int(meeting_pk):
            raise serializers.ValidationError({"block": "block은 URL의 meeting에 속해야 합니다."})
        return attrs

class AttachmentSerializer(AttachmentCreateSerializer):
    meeting = serializers.PrimaryKeyRelatedField(read_only=True)
    class Meta(AttachmentCreateSerializer.Meta):
        fields = ("id","meeting","block","file_url","mime_type","size","created_at")
