# analytics/management/commands/fetch_store_counts.py

import os
import math
import requests
from collections import Counter
from django.core.management.base import BaseCommand
from analytics.models import TradingArea, StoreCount

SEOUL_STORE_API_BASE = os.getenv("SEOUL_STORE_API_BASE", "http://apis.data.go.kr/B553077/api/open/sdsc2")
API_KEY = os.getenv("SEOUL_STORE_API_KEY")

from pyproj import Transformer
# TM중부(보정) → WGS84 (EPSG:2097 또는 5186 케이스에 맞춰 사용)
_transformer = Transformer.from_crs("EPSG:2097", "EPSG:4326", always_xy=True)

def tm_to_wgs84(x, y):
    lon, lat = _transformer.transform(x, y)
    return lon, lat

class Command(BaseCommand):
    help = "반경 내 상가업소(서울) 집계 저장"

    def add_arguments(self, parser):
        parser.add_argument("--radius", type=int, default=2000)
        parser.add_argument("--trdar", type=str, default=None, help="특정 상권코드만")
        parser.add_argument("--api-key", type=str, default=None)
        parser.add_argument("--insecure", action="store_true", help="http 사용 강제")
        parser.add_argument("--verbose_fail", action="store_true")

    def handle(self, *args, **opts):
        radius = opts["radius"]
        trdar_only = opts.get("trdar")
        api_key = opts.get("api-key") or API_KEY
        if not api_key:
            self.stdout.write("SEOUL_STORE_API_KEY 미설정. export SEOUL_STORE_API_KEY=... 후 재시도")
            return

        base = SEOUL_STORE_API_BASE
        if opts["insecure"] and base.startswith("https://"):
            base = base.replace("https://", "http://")

        # 상권 목록
        if trdar_only:
            ta_qs = TradingArea.objects.filter(trdar_cd=trdar_only)
        else:
            ta_qs = TradingArea.objects.all()

        created = updated = failed = 0

        for ta in ta_qs.iterator():
            cx = float(ta.x) if getattr(ta, "x", None) is not None else None
            cy = float(ta.y) if getattr(ta, "y", None) is not None else None
            if cx is None or cy is None:
                self.stdout.write(f"[SKIP] {ta.trdar_cd} {ta.trdar_cd_nm} -> 좌표(x,y) 없음")
                continue

            try:
                # 첫 페이지 호출(샘플 + totalCount 파악)
                params = {
                    "ServiceKey": api_key,
                    "type": "json",
                    "radius": radius,
                    "cx": cx,
                    "cy": cy,
                    "pageNo": 1,
                    "numOfRows": 1000,  # 가능한 큰 값
                }
                url = f"{base}/storeListInRadius"
                r = requests.get(url, params=params, timeout=30)
                r.raise_for_status()
                data = r.json()

                body = (data or {}).get("body") or {}
                items = body.get("items") or []
                total = int(body.get("totalCount") or 0)
                num = int(body.get("numOfRows") or 0)

                # 카운터 준비
                c_l = Counter()
                c_m = Counter()
                c_s = Counter()

                # 첫 페이지 반영
                for it in items:
                    c_l[it.get("indsLclsNm")] += 1
                    c_m[it.get("indsMclsNm")] += 1
                    c_s[it.get("indsSclsNm")] += 1

                # 다음 페이지들
                if total > num > 0:
                    pages = math.ceil(total / num)
                    for page in range(2, pages + 1):
                        params["pageNo"] = page
                        rr = requests.get(url, params=params, timeout=30)
                        rr.raise_for_status()
                        dd = rr.json()
                        bb = (dd or {}).get("body") or {}
                        its = bb.get("items") or []
                        for it in its:
                            c_l[it.get("indsLclsNm")] += 1
                            c_m[it.get("indsMclsNm")] += 1
                            c_s[it.get("indsSclsNm")] += 1

                # DB upsert
                obj, is_created = StoreCount.objects.update_or_create(
                    trdar_cd=ta.trdar_cd, radius=radius,
                    defaults={
                        "cx": cx, "cy": cy,
                        "total": total,
                        # raw는 첫 페이지만 샘플로 저장
                        "raw_data": data,
                        "counts_lcls": dict(c_l),
                        "counts_mcls": dict(c_m),
                        "counts_scls": dict(c_s),
                    }
                )
                created += 1 if is_created else 0
                updated += 0 if is_created else 1

            except requests.RequestException as e:
                failed += 1
                if opts["verbose_fail"]:
                    self.stdout.write(f"[FAIL] {ta.trdar_cd} {ta.trdar_cd_nm} -> {e}")
            except ValueError as e:
                failed += 1
                if opts["verbose_fail"]:
                    self.stdout.write(f"[FAIL] {ta.trdar_cd} {ta.trdar_cd_nm} -> {e}")

        self.stdout.write(f"Done. created={created}, updated={updated}, failed={failed}")
