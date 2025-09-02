# analytics/services/region.py
# 자치구 이름 <-> 코드 보조 유틸

# 행안부 표준 5자리 자치구 코드 (서울시)
# 필요하면 계속 보강 가능
from functools import lru_cache
import logging
from .seoul_openapi import iter_TbgisTrdarRelm
from ..models import TradingArea

SIGNGU_NAME_TO_CODE = {
    "종로구": "11110",
    "중구": "11140",
    "용산구": "11170",
    "성동구": "11200",
    "광진구": "11215",
    "동대문구": "11230",
    "중랑구": "11260",
    "성북구": "11290",
    "강북구": "11305",
    "도봉구": "11320",
    "노원구": "11350",
    "은평구": "11380",
    "서대문구": "11410",
    "마포구": "11440",
    "양천구": "11470",
    "강서구": "11500",
    "구로구": "11530",
    "금천구": "11545",
    "영등포구": "11560",
    "동작구": "11590",
    "관악구": "11620",
    "서초구": "11650",
    "강남구": "11680",
    "송파구": "11710",
    "강동구": "11740",
}

def normalize_signgu_name_to_code(name: str) -> str:
    """
    자치구 이름을 코드(문자열)로 변환. 못 찾으면 빈 문자열 반환.
    예) '강남구' -> '11680'
    """
    if not name:
        return ""
    return SIGNGU_NAME_TO_CODE.get(name.strip(), "")

def name_to_signgu_cd(name: str) -> str:
    return normalize_signgu_name_to_code(name)

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
