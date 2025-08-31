from django.db import transaction
from rest_framework import viewsets
from rest_framework.decorators import action
from rest_framework.response import Response

from .models import Meeting, Block, BlockRevision, Attachment
from .serializers import (
    MeetingSerializer, MeetingCreateSerializer,
    BlockSerializer, BlockCreateSerializer, BlockUpdateSerializer, BlockRevisionSerializer,
    AttachmentSerializer, AttachmentCreateSerializer,
)

DUMMY_USER_ID = 1

# ------------ 유틸 ------------
def _snapshot_block(block: Block) -> dict:
    return {
        "type": block.type,
        "level": block.level,
        "text": block.text,
        "rich_payload": block.rich_payload,
        "order_no": block.order_no,
        "parent_block": block.parent_block_id,
    }

def _next_revision_no(block: Block) -> int:
    last = block.revisions.order_by("-version").first()
    return (last.version if last else 0) + 1

def _record_revision(block: Block, edited_by=DUMMY_USER_ID):
    BlockRevision.objects.create(
        block=block,
        version=_next_revision_no(block),
        snapshot=_snapshot_block(block),
        edited_by=edited_by,
    )

def _ensure_table_payload(block: Block):
    if block.type != "table" or not isinstance(block.rich_payload, dict):
        raise ValueError("not_a_table")
    payload = block.rich_payload
    cols = payload.get("cols")
    rows = payload.get("rows")
    if not isinstance(cols, list) or not isinstance(rows, list):
        raise ValueError("invalid_table_shape")
    if "header" not in payload:
        payload["header"] = True
    if "colWidths" not in payload or not isinstance(payload["colWidths"], list):
        payload["colWidths"] = [None] * len(cols)
    if "merges" not in payload or not isinstance(payload["merges"], list):
        payload["merges"] = []
    target = len(cols)
    fixed_rows = []
    for r in rows:
        if not isinstance(r, list):
            raise ValueError("invalid_table_rows")
        if len(r) < target:
            r = r + [None] * (target - len(r))
        elif len(r) > target:
            r = r[:target]
        fixed_rows.append(r)
    payload["rows"] = fixed_rows
    if len(payload["colWidths"]) < target:
        payload["colWidths"] += [None] * (target - len(payload["colWidths"]))
    elif len(payload["colWidths"]) > target:
        payload["colWidths"] = payload["colWidths"][:target]
    block.rich_payload = payload

# ------------ ViewSets ------------
class MeetingViewSet(viewsets.ModelViewSet):
    queryset = Meeting.objects.all().order_by("-updated_at")
    serializer_class = MeetingSerializer

    def create(self, request, *args, **kwargs):
        ser = MeetingCreateSerializer(data=request.data)
        ser.is_valid(raise_exception=True)
        m = Meeting.objects.create(owner_id=DUMMY_USER_ID, **ser.validated_data)
        return Response(MeetingSerializer(m).data, status=201)

# =============== Blocks (nested) ===============
class BlockViewSet(viewsets.ModelViewSet):
    serializer_class = BlockSerializer

    def get_queryset(self):
        meeting_pk = self.kwargs["meeting_pk"]
        qs = Block.objects.select_related("meeting").filter(meeting_id=meeting_pk)

        parent = self.request.query_params.get("parent")
        if parent is not None:
            if isinstance(parent, str) and parent.lower() == "null":
                qs = qs.filter(parent_block__isnull=True)
            else:
                qs = qs.filter(parent_block_id=parent)

        btype = self.request.query_params.get("type")
        if btype:
            qs = qs.filter(type=btype)
        return qs

    def get_serializer_context(self):
        ctx = super().get_serializer_context()
        ctx["meeting_pk"] = self.kwargs["meeting_pk"]
        return ctx

    def create(self, request, *args, **kwargs):
        ser = BlockCreateSerializer(data=request.data)
        ser.is_valid(raise_exception=True)
        b = Block.objects.create(meeting_id=self.kwargs["meeting_pk"], **ser.validated_data, updated_by=DUMMY_USER_ID)

        if b.type == "table":
            try:
                _ensure_table_payload(b)
                b.save(update_fields=["rich_payload"])
            except ValueError as e:
                b.delete()
                return Response({"detail": str(e)}, status=400)

        return Response(BlockSerializer(b).data, status=201)

    def partial_update(self, request, *args, **kwargs):
        block = self.get_object()
        ser = BlockUpdateSerializer(data=request.data)
        ser.is_valid(raise_exception=True)

        with transaction.atomic():
            _record_revision(block, edited_by=DUMMY_USER_ID)
            for f in ("text", "level", "rich_payload"):
                if f in ser.validated_data:
                    setattr(block, f, ser.validated_data[f])
            if block.type == "table":
                _ensure_table_payload(block)
            block.updated_by = DUMMY_USER_ID
            block.save()
        return Response(BlockSerializer(block).data)

    @action(detail=True, methods=["post"])
    def reorder(self, request, meeting_pk=None, pk=None):
        block = self.get_object()
        try:
            new_order = int(request.data.get("new_order_no"))
        except (TypeError, ValueError):
            return Response({"detail": "new_order_no_required"}, status=400)
        new_parent = request.data.get("new_parent_block_id")

        with transaction.atomic():
            _record_revision(block, edited_by=DUMMY_USER_ID)
            if new_parent is not None:
                if not Block.objects.filter(id=new_parent, meeting_id=self.kwargs["meeting_pk"]).exists():
                    return Response({"detail": "new_parent_not_in_meeting"}, status=400)
                block.parent_block_id = new_parent
            else:
                block.parent_block = None
            block.order_no = new_order
            block.save()
        return Response(BlockSerializer(block).data)

    @action(detail=True, methods=["get"])
    def revisions(self, request, meeting_pk=None, pk=None):
        qs = BlockRevision.objects.filter(block_id=pk).order_by("-edited_at")[:100]
        return Response(BlockRevisionSerializer(qs, many=True).data)

    @action(detail=True, methods=["post"])
    def restore(self, request, meeting_pk=None, pk=None):
        try:
            version = int(request.data.get("version"))
        except (TypeError, ValueError):
            return Response({"detail": "version_required"}, status=400)

        block = self.get_object()
        rev = block.revisions.filter(version=version).first()
        if not rev:
            return Response({"detail": "revision_not_found"}, status=404)
        snap = rev.snapshot
        with transaction.atomic():
            _record_revision(block, edited_by=DUMMY_USER_ID)  # 복원 전 상태도 보관
            block.type = snap.get("type", block.type)
            block.level = snap.get("level")
            block.text = snap.get("text")
            block.rich_payload = snap.get("rich_payload")
            block.order_no = snap.get("order_no", block.order_no)
            block.parent_block_id = snap.get("parent_block", block.parent_block_id)
            if block.type == "table":
                try:
                    _ensure_table_payload(block)
                except ValueError:
                    pass
            block.updated_by = DUMMY_USER_ID
            block.save()
        return Response(BlockSerializer(block).data)

    # ----- 표(Table) 전용 액션들: version 파라미터 없이 동작 -----
    @action(detail=True, methods=["post"])
    def update_cell(self, request, meeting_pk=None, pk=None):
        block = self.get_object()
        try:
            row = int(request.data.get("row"))
            col = int(request.data.get("col"))
        except (TypeError, ValueError):
            return Response({"detail": "row_col_required"}, status=400)

        try:
            _ensure_table_payload(block)
        except ValueError:
            return Response({"detail": "not_a_table"}, status=400)

        rows = block.rich_payload["rows"]
        if row < 0 or row >= len(rows) or len(rows) == 0:
            return Response({"detail": "row_out_of_range"}, status=400)
        if col < 0 or col >= len(rows[0]):
            return Response({"detail": "col_out_of_range"}, status=400)

        with transaction.atomic():
            _record_revision(block, edited_by=DUMMY_USER_ID)
            rows[row][col] = request.data.get("value")
            block.rich_payload["rows"] = rows
            block.updated_by = DUMMY_USER_ID
            block.save()
        return Response(BlockSerializer(block).data)

    @action(detail=True, methods=["post"])
    def insert_row(self, request, meeting_pk=None, pk=None):
        block = self.get_object()
        try:
            idx = int(request.data.get("index"))
        except (TypeError, ValueError):
            return Response({"detail": "index_required"}, status=400)

        try:
            _ensure_table_payload(block)
        except ValueError:
            return Response({"detail": "not_a_table"}, status=400)

        cols_len = len(block.rich_payload["cols"])
        rows = block.rich_payload["rows"]
        if idx < 0 or idx > len(rows):
            return Response({"detail": "index_out_of_range"}, status=400)

        new_row = request.data.get("row")
        if new_row is None:
            new_row = [None] * cols_len
        elif not isinstance(new_row, list):
            return Response({"detail": "row_should_be_list"}, status=400)
        if len(new_row) < cols_len:
            new_row = new_row + [None] * (cols_len - len(new_row))
        elif len(new_row) > cols_len:
            new_row = new_row[:cols_len]

        with transaction.atomic():
            _record_revision(block, edited_by=DUMMY_USER_ID)
            rows.insert(idx, new_row)
            block.rich_payload["rows"] = rows
            block.updated_by = DUMMY_USER_ID
            block.save()
        return Response(BlockSerializer(block).data)

    @action(detail=True, methods=["post"])
    def delete_row(self, request, meeting_pk=None, pk=None):
        block = self.get_object()
        try:
            idx = int(request.data.get("index"))
        except (TypeError, ValueError):
            return Response({"detail": "index_required"}, status=400)

        try:
            _ensure_table_payload(block)
        except ValueError:
            return Response({"detail": "not_a_table"}, status=400)

        rows = block.rich_payload["rows"]
        if idx < 0 or idx >= len(rows):
            return Response({"detail": "index_out_of_range"}, status=400)

        with transaction.atomic():
            _record_revision(block, edited_by=DUMMY_USER_ID)
            rows.pop(idx)
            block.rich_payload["rows"] = rows
            block.updated_by = DUMMY_USER_ID
            block.save()
        return Response(BlockSerializer(block).data)

    @action(detail=True, methods=["post"])
    def insert_col(self, request, meeting_pk=None, pk=None):
        block = self.get_object()
        try:
            idx = int(request.data.get("index"))
        except (TypeError, ValueError):
            return Response({"detail": "index_required"}, status=400)

        try:
            _ensure_table_payload(block)
        except ValueError:
            return Response({"detail": "not_a_table"}, status=400)

        cols = block.rich_payload["cols"]
        rows = block.rich_payload["rows"]
        colWidths = block.rich_payload.get("colWidths", [])

        if idx < 0 or idx > len(cols):
            return Response({"detail": "index_out_of_range"}, status=400)

        name = request.data.get("name", "")
        default = request.data.get("default", None)
        width = request.data.get("width", None)

        with transaction.atomic():
            _record_revision(block, edited_by=DUMMY_USER_ID)
            cols.insert(idx, name)
            for r in rows:
                r.insert(idx, default)
            colWidths.insert(idx, width)
            block.rich_payload["cols"] = cols
            block.rich_payload["rows"] = rows
            block.rich_payload["colWidths"] = colWidths
            block.updated_by = DUMMY_USER_ID
            block.save()
        return Response(BlockSerializer(block).data)

    @action(detail=True, methods=["post"])
    def delete_col(self, request, meeting_pk=None, pk=None):
        block = self.get_object()
        try:
            idx = int(request.data.get("index"))
        except (TypeError, ValueError):
            return Response({"detail": "index_required"}, status=400)

        try:
            _ensure_table_payload(block)
        except ValueError:
            return Response({"detail": "not_a_table"}, status=400)

        cols = block.rich_payload["cols"]
        rows = block.rich_payload["rows"]
        colWidths = block.rich_payload.get("colWidths", [])
        if idx < 0 or idx >= len(cols):
            return Response({"detail": "index_out_of_range"}, status=400)

        with transaction.atomic():
            _record_revision(block, edited_by=DUMMY_USER_ID)
            cols.pop(idx)
            for r in rows:
                if len(r) > idx:
                    r.pop(idx)
            if len(colWidths) > idx:
                colWidths.pop(idx)
            block.rich_payload["cols"] = cols
            block.rich_payload["rows"] = rows
            block.rich_payload["colWidths"] = colWidths
            block.updated_by = DUMMY_USER_ID
            block.save()
        return Response(BlockSerializer(block).data)

    @action(detail=True, methods=["post"])
    def rename_col(self, request, meeting_pk=None, pk=None):
        block = self.get_object()
        try:
            idx = int(request.data.get("index"))
            name = request.data.get("name")
        except (TypeError, ValueError):
            return Response({"detail": "index_name_required"}, status=400)

        if not isinstance(name, str):
            return Response({"detail": "name_should_be_string"}, status=400)

        try:
            _ensure_table_payload(block)
        except ValueError:
            return Response({"detail": "not_a_table"}, status=400)

        cols = block.rich_payload["cols"]
        if idx < 0 or idx >= len(cols):
            return Response({"detail": "index_out_of_range"}, status=400)

        with transaction.atomic():
            _record_revision(block, edited_by=DUMMY_USER_ID)
            cols[idx] = name
            block.rich_payload["cols"] = cols
            block.updated_by = DUMMY_USER_ID
            block.save()
        return Response(BlockSerializer(block).data)

    @action(detail=True, methods=["post"])
    def set_col_width(self, request, meeting_pk=None, pk=None):
        block = self.get_object()
        try:
            idx = int(request.data.get("index"))
        except (TypeError, ValueError):
            return Response({"detail": "index_required"}, status=400)
        width = request.data.get("width", None)
        if width is not None:
            try:
                width = int(width)
            except (TypeError, ValueError):
                return Response({"detail": "width_should_be_int_or_null"}, status=400)

        try:
            _ensure_table_payload(block)
        except ValueError:
            return Response({"detail": "not_a_table"}, status=400)

        colWidths = block.rich_payload.get("colWidths", [])
        cols = block.rich_payload["cols"]
        if idx < 0 or idx >= len(cols):
            return Response({"detail": "index_out_of_range"}, status=400)

        with transaction.atomic():
            _record_revision(block, edited_by=DUMMY_USER_ID)
            if len(colWidths) < len(cols):
                colWidths += [None] * (len(cols) - len(colWidths))
            colWidths[idx] = width
            block.rich_payload["colWidths"] = colWidths
            block.updated_by = DUMMY_USER_ID
            block.save()
        return Response(BlockSerializer(block).data)

# =============== Attachments (nested) ===============
class AttachmentViewSet(viewsets.ModelViewSet):
    serializer_class = AttachmentSerializer

    def get_queryset(self):
        return Attachment.objects.select_related("meeting").filter(meeting_id=self.kwargs["meeting_pk"])

    def get_serializer_context(self):
        ctx = super().get_serializer_context()
        ctx["meeting_pk"] = self.kwargs["meeting_pk"]
        return ctx

    def create(self, request, *args, **kwargs):
        ser = AttachmentCreateSerializer(data=request.data, context=self.get_serializer_context())
        ser.is_valid(raise_exception=True)
        att = Attachment.objects.create(meeting_id=self.kwargs["meeting_pk"], **ser.validated_data)
        return Response(AttachmentSerializer(att).data, status=201)
