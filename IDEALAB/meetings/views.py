from django.db import transaction
from rest_framework import viewsets, status
from rest_framework.decorators import action
from rest_framework.response import Response
from .models import Meeting, Block, BlockRevision, Attachment
from .serializers import (
    MeetingSerializer,
    MeetingCreateSerializer,
    BlockSerializer,
    BlockCreateSerializer,
    BlockUpdateSerializer,
    BlockRevisionSerializer,
    AttachmentSerializer,
    AttachmentCreateSerializer,
)

DUMMY_USER_ID = 1  # 서버 미연결이므로 임시

class MeetingViewSet(viewsets.ModelViewSet):
    queryset = Meeting.objects.all().order_by("-updated_at")
    serializer_class = MeetingSerializer

    def create(self, request, *args, **kwargs):
        ser = MeetingCreateSerializer(data=request.data)
        ser.is_valid(raise_exception=True)
        m = Meeting.objects.create(owner_id=DUMMY_USER_ID, **ser.validated_data)
        return Response(MeetingSerializer(m).data, status=201)

class BlockViewSet(viewsets.ModelViewSet):
    queryset = Block.objects.all()
    serializer_class = BlockSerializer

    def create(self, request, *args, **kwargs):
        ser = BlockCreateSerializer(data=request.data)
        ser.is_valid(raise_exception=True)
        b = Block.objects.create(**ser.validated_data, updated_by=DUMMY_USER_ID)
        return Response(BlockSerializer(b).data, status=201)

    def partial_update(self, request, *args, **kwargs):
        block = self.get_object()
        ser = BlockUpdateSerializer(data=request.data)
        ser.is_valid(raise_exception=True)
        # 낙관적 잠금
        if block.version != ser.validated_data["version"]:
            return Response({"detail":"version_conflict",
                             "current":{"id":block.id,"version":block.version}},
                            status=409)
        with transaction.atomic():
            # 변경 전 스냅샷
            BlockRevision.objects.create(
                block=block,
                version=block.version,
                snapshot={
                    "type": block.type,
                    "level": block.level,
                    "text": block.text,
                    "rich_payload": block.rich_payload,
                    "order_no": block.order_no,
                    "parent_block": block.parent_block_id
                },
                edited_by=DUMMY_USER_ID
            )
            # 업데이트
            for f in ("text","level","rich_payload"):
                if f in ser.validated_data:
                    setattr(block, f, ser.validated_data[f])
            block.version += 1
            block.updated_by = DUMMY_USER_ID
            block.save()
        return Response(BlockSerializer(block).data)

    @action(detail=True, methods=["post"])
    def reorder(self, request, pk=None):
        """블록 순서/부모 변경"""
        block = self.get_object()
        new_order = int(request.data.get("new_order_no"))
        new_parent = request.data.get("new_parent_block_id")
        with transaction.atomic():
            if new_parent is not None:
                block.parent_block_id = new_parent
            block.order_no = new_order
            block.save()
        return Response(BlockSerializer(block).data)

    @action(detail=True, methods=["get"])
    def revisions(self, request, pk=None):
        qs = BlockRevision.objects.filter(block_id=pk).order_by("-edited_at")[:100]
        return Response(BlockRevisionSerializer(qs, many=True).data)

    @action(detail=True, methods=["post"])
    def restore(self, request, pk=None):
        """특정 버전으로 되돌리기"""
        version = int(request.data.get("version"))
        block = self.get_object()
        rev = BlockRevision.objects.filter(block_id=block.id, version=version).first()
        if not rev:
            return Response({"detail":"revision_not_found"}, status=404)
        snap = rev.snapshot
        with transaction.atomic():
            # 스냅샷을 현재로 반영
            block.type = snap.get("type", block.type)
            block.level = snap.get("level")
            block.text = snap.get("text")
            block.rich_payload = snap.get("rich_payload")
            block.order_no = snap.get("order_no", block.order_no)
            block.parent_block_id = snap.get("parent_block", block.parent_block_id)
            block.version += 1
            block.updated_by = DUMMY_USER_ID
            block.save()
        return Response(BlockSerializer(block).data)

class AttachmentViewSet(viewsets.ModelViewSet):
    queryset = Attachment.objects.all()
    serializer_class = AttachmentSerializer

    def create(self, request, *args, **kwargs):
        ser = AttachmentCreateSerializer(data=request.data)
        ser.is_valid(raise_exception=True)
        att = Attachment.objects.create(**ser.validated_data)
        return Response(AttachmentSerializer(att).data, status=201)
