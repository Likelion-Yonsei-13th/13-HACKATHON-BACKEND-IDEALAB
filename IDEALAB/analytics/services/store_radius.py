# analytics/services/store_radius.py
import os
import time
import math
import requests
from collections import defaultdict

SEOUL_API_KEY = os.getenv("SEOUL_OPENAPI_KEY")  # 환경변수에 넣어두세요
BASE_URL = "http://openapi.seoul.go.kr:8088"
SERVICE = "storeListInRadius"

DEFAULT_NUM_ROWS = 2000  # API가 허용하는 최대치 기준으로 조정

class StoreRadiusClient:
    def __init__(self, api_key: str | None = None):
        self.api_key = api_key or SEOUL_API_KEY
        if not self.api_key:
            raise RuntimeError("환경변수 SEOUL_API_KEY 가 필요합니다.")

    def _endpoint(self, page_no: int, num_rows: int) -> str:
        # /{KEY}/json/storeListInRadius/{pageNo}/{numOfRows}/
        return f"{BASE_URL}/{self.api_key}/json/{SERVICE}/{page_no}/{num_rows}/"

    def fetch_page(self, cx: int, cy: int, radius: int, page_no: int, num_rows: int = DEFAULT_NUM_ROWS):
        url = self._endpoint(page_no, num_rows)
        params = {
            "cx": cx,
            "cy": cy,
            "radius": radius,
        }
        r = requests.get(url, params=params, timeout=20)
        r.raise_for_status()
        j = r.json()
        # 에러 처리 포맷 방어
        block = j.get(SERVICE) or j.get(SERVICE[0].lower() + SERVICE[1:]) or {}
        return {
            "total": block.get("list_total_count"),
            "rows": block.get("row", []) or [],
            "raw": block,
        }

    def fetch_all(self, cx: int, cy: int, radius: int = 2000, sleep_sec: float = 0.15):
        # 1페이지 먼저
        page_no = 1
        first = self.fetch_page(cx, cy, radius, page_no)
        total = int(first["total"] or 0)
        rows = list(first["rows"])
        raw_meta = {"first_result": first.get("raw", {})}

        if total <= len(rows):
            return rows, total, raw_meta

        # 나머지 페이지
        num_rows = DEFAULT_NUM_ROWS
        total_pages = math.ceil(total / num_rows)
        for page_no in range(2, total_pages + 1):
            time.sleep(sleep_sec)  # 과도 호출 방지
            page = self.fetch_page(cx, cy, radius, page_no, num_rows)
            rows.extend(page["rows"])
        return rows, total, raw_meta


def aggregate_counts(rows: list[dict]):
    """
    API row 예시(문서 기준):
      - indsLclsCd / indsLclsNm (대분류)
      - indsMclsCd / indsMclsNm (중분류)
      - indsSclsCd / indsSclsNm (소분류)
    """
    l = defaultdict(int)
    m = defaultdict(int)
    s = defaultdict(int)

    for r in rows:
        # 이름 우선, 없으면 코드로 대체
        ln = r.get("indsLclsNm") or r.get("indsLclsCd")
        mn = r.get("indsMclsNm") or r.get("indsMclsCd")
        sn = r.get("indsSclsNm") or r.get("indsSclsCd")

        if ln: l[ln] += 1
        if mn: m[mn] += 1
        if sn: s[sn] += 1

    return dict(l), dict(m), dict(s)
