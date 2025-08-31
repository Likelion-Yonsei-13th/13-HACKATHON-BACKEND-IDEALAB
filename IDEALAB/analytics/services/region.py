# analytics/services/region.py
from functools import lru_cache
import logging
from .seoul_openapi import iter_TbgisTrdarRelm
from ..models import TradingArea  # ✅ DB 존재 시 먼저 시도

logger = logging.getLogger(__name__)

def _pick_float(d: dict, keys):
    for k in keys:
        v = d.get(k)
        if v not in (None, "", "NULL", "NaN"):
            try:
                return float(str(v).strip())
            except Exception:
                continue
    return None

@lru_cache(maxsize=1024)
def get_trdar_center(trdar_cd: str):
    """우선 DB TradingArea(x,y) → 실패시 서울 오픈API 폴백."""
    target = (trdar_cd or "").strip()
    if not target:
        return None, None

    # 1) DB 먼저 시도 (모델 필드명: x, y)
    try:
        rec = TradingArea.objects.filter(trdar_cd=target).values("x", "y").first()
        if rec and rec.get("x") is not None and rec.get("y") is not None:
            return float(rec["x"]), float(rec["y"])
    except Exception as e:
        logger.warning("TradingArea lookup failed: %s", e)

    # 2) 오픈API 폴백
    try:
        for row in iter_TbgisTrdarRelm():
            if str(row.get("TRDAR_CD", "")).strip() != target:
                continue
            cx = _pick_float(row, ["X_CRDNT", "TRDAR_X_CRDNT", "LON", "LNG", "X"])
            cy = _pick_float(row, ["Y_CRDNT", "TRDAR_Y_CRDNT", "LAT", "Y"])
            return cx, cy
        logger.warning("TRDAR not found in TbgisTrdarRelm: %s", target)
        return None, None
    except Exception as e:
        logger.exception("get_trdar_center failed: %s", e)
        return None, None