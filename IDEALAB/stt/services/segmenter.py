import re
from typing import Optional, Dict, Any

_SENT_END = re.compile(r'([\.!?]+)\s+')

class SegmentBuffer:
    """
    2초 청크 누적 → 간단 규칙으로 세그먼트 확정.
    정책: 30초 이상 또는 300자 이상 모이면 flush.
    """
    def __init__(self):
        self.buf = []
        self.total_ms = 0
        self.last_end = 0

    def push_chunk(self, text: str, start_ms: int, end_ms: int, speaker: str | None = None) -> Optional[Dict[str, Any]]:
        self.buf.append(text)
        self.total_ms += (end_ms - start_ms)
        self.last_end = end_ms
        current = " ".join(self.buf).strip()

        if self.total_ms < 30_000 and len(current) < 300:
            return None

        seg_text = current
        self.buf.clear()
        self.total_ms = 0
        return {"text": seg_text, "start_ms": end_ms - len(seg_text), "end_ms": end_ms, "speaker": speaker}
    