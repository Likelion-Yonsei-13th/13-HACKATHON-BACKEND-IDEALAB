# IDEALAB/meetings/views.py
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

DUMMY_USER_ID = 1  # 서버 연동 전 임시 사용자

# ------------ 유틸 ------------
def _snapshot_block(block: Block) -> dict:
    """리비전에 저장할 스냅샷 만들기"""
    return {
        "type": block.type,
        "level": block.level,
        "text": block.text,
        "rich_payload": block.rich_payload,
        "order_no": block.order_no,
        "parent_block": block.parent_block_id,
    }

def _record_revision(block: Block, edited_by=DUMMY_USER_ID):
    """수정 전 리비전 기록"""
    BlockRevision.objects.create(
        block=block,
        version=block.version,
        snapshot=_snapshot_block(block),
        edited_by=edited_by,
    )

def _ensure_table_payload(block: Block):
    """표 블록의 payload 기본 형태 보정 + 최소 검증"""
    if block.type != "table" or not isinstance(block.rich_payload, dict):
        raise ValueError("not_a_table")

    payload = block.rich_payload
    cols = payload.get("cols")
    rows = payload.get("rows")
    if not isinstance(cols, list) or not isinstance(rows, list):
        raise ValueError("invalid_table_shape")

    # 선택 필드 기본값
    if "header" not in payload:
        payload["header"] = True
    if "colWidths" not in payload or not isinstance(payload["colWidths"], list):
        payload["colWidths"] = [None] * len(cols)
    if "merges" not in payload or not isinstance(payload["merges"], list):
        payload["merges"] = []

    # 모든 row 길이 cols 길이와 맞추기(짧으면 None로 채움, 길면 자름)
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

    # colWidths 길이 보정
    if len(payload["colWidths"]) < target:
        payload["colWidths"] += [None] * (target - len(payload["colWidths"]))
    elif len(payload["colWidths"]) > target:
        payload["colWidths"] = payload["colWidths"][:target]

    block.rich_payload = payload  # 보정 반영


# ------------ ViewSets ------------
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

    # 목록 필터: ?meeting=1&parent=null|<id>&type=table|paragraph...
    def get_queryset(self):
        qs = super().get_queryset()
        meeting_id = self.request.query_params.get("meeting")
        if meeting_id:
            qs = qs.filter(meeting_id=meeting_id)

        parent = self.request.query_params.get("parent")
        if parent is not None:
            if parent.lower() == "null":
                qs = qs.filter(parent_block__isnull=True)
            else:
                qs = qs.filter(parent_block_id=parent)

        btype = self.request.query_params.get("type")
        if btype:
            qs = qs.filter(type=btype)
        return qs

    def create(self, request, *args, **kwargs):
        ser = BlockCreateSerializer(data=request.data)
        ser.is_valid(raise_exception=True)
        b = Block.objects.create(**ser.validated_data, updated_by=DUMMY_USER_ID)

        # 표 블록이면 기본 형태 보정
        if b.type == "table":
            try:
                _ensure_table_payload(b)
                b.save(update_fields=["rich_payload"])
            except ValueError as e:
                b.delete()  # 생성 롤백
                return Response({"detail": str(e)}, status=400)

        return Response(BlockSerializer(b).data, status=201)

    def partial_update(self, request, *args, **kwargs):
        block = self.get_object()
        ser = BlockUpdateSerializer(data=request.data)
        ser.is_valid(raise_exception=True)

        # 낙관적 잠금
        if block.version != ser.validated_data["version"]:
            return Response(
                {"detail": "version_conflict", "current": {"id": block.id, "version": block.version}},
                status=409,
            )

        with transaction.atomic():
            _record_revision(block, edited_by=DUMMY_USER_ID)
            # 업데이트
            for f in ("text", "level", "rich_payload"):
                if f in ser.validated_data:
                    setattr(block, f, ser.validated_data[f])

            # 표라면 payload 보정/검증
            if block.type == "table":
                try:
                    _ensure_table_payload(block)
                except ValueError as e:
                    raise  # 500이 아니라 400으로 내리고 싶으면 아래로 바꿔도 됨

            block.version += 1
            block.updated_by = DUMMY_USER_ID
            block.save()
        return Response(BlockSerializer(block).data)

    @action(detail=True, methods=["post"])
    def reorder(self, request, pk=None):
        """블록 순서/부모 변경"""
        block = self.get_object()
        try:
            new_order = int(request.data.get("new_order_no"))
        except (TypeError, ValueError):
            return Response({"detail": "new_order_no_required"}, status=400)
        new_parent = request.data.get("new_parent_block_id")

        with transaction.atomic():
            block.parent_block_id = new_parent if new_parent is not None else block.parent_block_id
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
        try:
            version = int(request.data.get("version"))
        except (TypeError, ValueError):
            return Response({"detail": "version_required"}, status=400)

        block = self.get_object()
        rev = BlockRevision.objects.filter(block_id=block.id, version=version).first()
        if not rev:
            return Response({"detail": "revision_not_found"}, status=404)
        snap = rev.snapshot
        with transaction.atomic():
            block.type = snap.get("type", block.type)
            block.level = snap.get("level")
            block.text = snap.get("text")
            block.rich_payload = snap.get("rich_payload")
            block.order_no = snap.get("order_no", block.order_no)
            block.parent_block_id = snap.get("parent_block", block.parent_block_id)
            block.version += 1
            block.updated_by = DUMMY_USER_ID
            # 표 보정
            if block.type == "table":
                try:
                    _ensure_table_payload(block)
                except ValueError:
                    pass
            block.save()
        return Response(BlockSerializer(block).data)

    # ------------- 표(Table) 전용 액션들 -------------
    @action(detail=True, methods=["post"])
    def update_cell(self, request, pk=None):
        """
        body: { "row": <int>, "col": <int>, "value": <any>, "version": <int> }
        """
        block = self.get_object()
        try:
            row = int(request.data.get("row"))
            col = int(request.data.get("col"))
            version = int(request.data.get("version"))
        except (TypeError, ValueError):
            return Response({"detail": "row_col_version_required"}, status=400)

        if block.version != version:
            return Response({"detail": "version_conflict", "current": {"version": block.version}}, status=409)

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
            block.version += 1
            block.updated_by = DUMMY_USER_ID
            block.save()
        return Response(BlockSerializer(block).data)

    @action(detail=True, methods=["post"])
    def insert_row(self, request, pk=None):
        """
        body: { "index": <int>, "version": <int>, "row": [optional list values] }
        """
        block = self.get_object()
        try:
            idx = int(request.data.get("index"))
            version = int(request.data.get("version"))
        except (TypeError, ValueError):
            return Response({"detail": "index_version_required"}, status=400)
        if block.version != version:
            return Response({"detail": "version_conflict", "current": {"version": block.version}}, status=409)

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
        # 길이 보정
        if len(new_row) < cols_len:
            new_row = new_row + [None] * (cols_len - len(new_row))
        elif len(new_row) > cols_len:
            new_row = new_row[:cols_len]

        with transaction.atomic():
            _record_revision(block, edited_by=DUMMY_USER_ID)
            rows.insert(idx, new_row)
            block.rich_payload["rows"] = rows
            block.version += 1
            block.updated_by = DUMMY_USER_ID
            block.save()
        return Response(BlockSerializer(block).data)

    @action(detail=True, methods=["post"])
    def delete_row(self, request, pk=None):
        """
        body: { "index": <int>, "version": <int> }
        """
        block = self.get_object()
        try:
            idx = int(request.data.get("index"))
            version = int(request.data.get("version"))
        except (TypeError, ValueError):
            return Response({"detail": "index_version_required"}, status=400)
        if block.version != version:
            return Response({"detail": "version_conflict", "current": {"version": block.version}}, status=409)

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
            block.version += 1
            block.updated_by = DUMMY_USER_ID
            block.save()
        return Response(BlockSerializer(block).data)

    @action(detail=True, methods=["post"])
    def insert_col(self, request, pk=None):
        """
        body: { "index": <int>, "version": <int>, "name": <optional str>, "default": <optional any>, "width": <optional int> }
        """
        block = self.get_object()
        try:
            idx = int(request.data.get("index"))
            version = int(request.data.get("version"))
        except (TypeError, ValueError):
            return Response({"detail": "index_version_required"}, status=400)
        if block.version != version:
            return Response({"detail": "version_conflict", "current": {"version": block.version}}, status=409)

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
            block.version += 1
            block.updated_by = DUMMY_USER_ID
            block.save()
        return Response(BlockSerializer(block).data)

    @action(detail=True, methods=["post"])
    def delete_col(self, request, pk=None):
        """
        body: { "index": <int>, "version": <int> }
        """
        block = self.get_object()
        try:
            idx = int(request.data.get("index"))
            version = int(request.data.get("version"))
        except (TypeError, ValueError):
            return Response({"detail": "index_version_required"}, status=400)
        if block.version != version:
            return Response({"detail": "version_conflict", "current": {"version": block.version}}, status=409)

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
            block.version += 1
            block.updated_by = DUMMY_USER_ID
            block.save()
        return Response(BlockSerializer(block).data)

    @action(detail=True, methods=["post"])
    def rename_col(self, request, pk=None):
        """
        body: { "index": <int>, "name": <str>, "version": <int> }
        """
        block = self.get_object()
        try:
            idx = int(request.data.get("index"))
            name = request.data.get("name")
            version = int(request.data.get("version"))
        except (TypeError, ValueError):
            return Response({"detail": "index_name_version_required"}, status=400)

        if not isinstance(name, str):
            return Response({"detail": "name_should_be_string"}, status=400)
        if block.version != version:
            return Response({"detail": "version_conflict", "current": {"version": block.version}}, status=409)

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
            block.version += 1
            block.updated_by = DUMMY_USER_ID
            block.save()
        return Response(BlockSerializer(block).data)

    @action(detail=True, methods=["post"])
    def set_col_width(self, request, pk=None):
        """
        body: { "index": <int>, "width": <int|null>, "version": <int> }
        """
        block = self.get_object()
        try:
            idx = int(request.data.get("index"))
            version = int(request.data.get("version"))
        except (TypeError, ValueError):
            return Response({"detail": "index_version_required"}, status=400)
        width = request.data.get("width", None)
        if width is not None:
            try:
                width = int(width)
            except (TypeError, ValueError):
                return Response({"detail": "width_should_be_int_or_null"}, status=400)

        if block.version != version:
            return Response({"detail": "version_conflict", "current": {"version": block.version}}, status=409)

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
