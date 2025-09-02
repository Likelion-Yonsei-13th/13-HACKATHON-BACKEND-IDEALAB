# analytics/management/commands/import_trading_areas_csv.py
from django.core.management.base import BaseCommand
from analytics.models import TradingArea
from analytics.services.csv_loader import read_csv_rows

def _to_float(x):
    if x is None:
        return None
    s = str(x).strip().replace(",", "")
    if s == "":
        return None
    try:
        return float(s)
    except Exception:
        return None

class Command(BaseCommand):
    help = "CSV로 상권(소권역) 마스터 적재 (한글/영문 헤더 및 인코딩 지원)"

    def add_arguments(self, parser):
        parser.add_argument("csv_path", type=str, help="CSV 파일 경로")
        parser.add_argument(
            "--encoding",
            type=str,
            default="utf-8",
            help="CSV 인코딩 (예: utf-8, utf-8-sig, cp949, euc-kr 등)",
        )

    def handle(self, *args, **opts):
        path = opts["csv_path"]
        encoding = opts["encoding"]

        # 컬럼 별로 가능한 헤더 별칭(한글/영문/스네이크)을 모두 허용
        aliases = {
            "TRDAR_CD":       ["TRDAR_CD", "trdar_cd", "상권_코드"],
            "TRDAR_CD_NM":    ["TRDAR_CD_NM", "trdar_cd_nm", "상권_코드_명"],
            "TRDAR_SE_CD":    ["TRDAR_SE_CD", "trdar_se_cd", "상권_구분_코드"],
            "TRDAR_SE_CD_NM": ["TRDAR_SE_CD_NM", "trdar_se_cd_nm", "상권_구분_코드_명"],
            "XCNTS_VALUE":    ["XCNTS_VALUE", "x", "X좌표", "X좌표_TM", "TM_X", "엑스좌표_값"],
            "YDNTS_VALUE":    ["YDNTS_VALUE", "y", "Y좌표", "Y좌표_TM", "TM_Y", "와이좌표_값"],
            "SIGNGU_CD":      ["SIGNGU_CD", "signgu_cd", "자치구_코드"],
            "SIGNGU_CD_NM":   ["SIGNGU_CD_NM", "signgu_cd_nm", "자치구_코드_명", "자치구명"],
            "ADSTRD_CD":      ["ADSTRD_CD", "adstrd_cd", "행정동_코드", "법정동_코드"],
            "ADSTRD_CD_NM":   ["ADSTRD_CD_NM", "adstrd_cd_nm", "행정동_코드_명", "법정동명"],
            "RELM_AR":        ["RELM_AR", "area_m2", "면적(m2)", "면적_제곱미터", "영역_면적"],
        }

        def get_val(row, key):
            """별칭 목록을 순회하며 첫 번째로 존재하는 값을 반환"""
            for k in aliases[key]:
                if k in row and row[k] not in (None, ""):
                    return row[k]
            return None

        created = updated = skipped = 0

        for r in read_csv_rows(path, encoding=encoding):
            trdar_cd = (get_val(r, "TRDAR_CD") or "").strip()
            if not trdar_cd:
                skipped += 1
                continue

            defaults = {
                "trdar_cd_nm":    get_val(r, "TRDAR_CD_NM"),
                "trdar_se_cd":    get_val(r, "TRDAR_SE_CD"),
                "trdar_se_cd_nm": get_val(r, "TRDAR_SE_CD_NM"),
                "x":              _to_float(get_val(r, "XCNTS_VALUE")),
                "y":              _to_float(get_val(r, "YDNTS_VALUE")),
                "signgu_cd":      get_val(r, "SIGNGU_CD"),
                "signgu_cd_nm":   get_val(r, "SIGNGU_CD_NM"),
                "adstrd_cd":      get_val(r, "ADSTRD_CD"),
                "adstrd_cd_nm":   get_val(r, "ADSTRD_CD_NM"),
                "area_m2":        _to_float(get_val(r, "RELM_AR")),
            }

            obj, is_created = TradingArea.objects.update_or_create(
                trdar_cd=trdar_cd, defaults=defaults
            )
            created += int(is_created)
            updated += int(not is_created)

        self.stdout.write(self.style.SUCCESS(
            f"TradingArea upserted: created={created}, updated={updated}, skipped={skipped}"
        ))
