# analytics/management/commands/import_closures_csv.py
from django.core.management.base import BaseCommand
from analytics.models import ClosureStat
from analytics.services.csv_loader import read_csv_rows
try:
    from analytics.services.region import normalize_signgu_name_to_code as name_to_signgu_cd
except Exception:
    def name_to_signgu_cd(x): return None

def _int_or_none(x):
    try:
        return int(str(x).replace(",", "").strip())
    except Exception:
        return None

def _clean(s):
    return str(s).strip().replace('"', '').replace("'", '')

class Command(BaseCommand):
    help = "자치구/행정동 폐업 CSV 업로드"

    def add_arguments(self, parser):
        parser.add_argument("csv_path")
        parser.add_argument("--encoding", default="utf-8")
        # 세로형: 'year'가 각 행에 있거나, 혹은 wide형처럼 한 해 전체일 수 있음
        parser.add_argument("--year", type=int)            # 세로형일 때 연도 고정
        parser.add_argument("--year_col")                  # 세로형일 때 연도 칼럼명
        # 가로형(현재 파일 형태): 한 해 열들만 있고 행은 자치구, melt로 카테고리 펼침
        parser.add_argument("--wide_year", type=int)       # 가로형일 때 연도 고정
        parser.add_argument("--melt_cols", help="가로형에서 펼칠 카테고리 목록(쉼표구분)")
        parser.add_argument("--skip_total_row", action="store_true", help="'서울시' 총계행 스킵")

        parser.add_argument("--signgu_cd_col")
        parser.add_argument("--signgu_nm_col", required=True)
        parser.add_argument("--count_col")                 # 세로형일 때 값 칼럼
        parser.add_argument("--category_col")              # 세로형일 때 카테고리 칼럼

    def handle(self, *args, **opts):
        path       = opts["csv_path"]
        encoding   = opts["encoding"]
        year       = opts.get("year")
        year_col   = opts.get("year_col")
        wide_year  = opts.get("wide_year")
        signgu_cd_col = opts.get("signgu_cd_col")
        signgu_nm_col = opts["signgu_nm_col"]
        count_col  = opts.get("count_col")
        category_col = opts.get("category_col")
        melt_cols  = [c.strip() for c in (opts.get("melt_cols") or "").split(",") if c.strip()]
        skip_total = opts.get("skip_total_row")

        created = updated = skipped = 0

        if wide_year:
            # 가로형: 예) 자치구 | 전체 | 외식업 | 서비스업 | 소매업
            for r in read_csv_rows(path, encoding=encoding):
                name = _clean(r.get(signgu_nm_col, ""))
                if not name:
                    skipped += 1
                    continue
                if skip_total and name == "서울시":
                    skipped += 1
                    continue

                for cat in melt_cols:
                    if cat not in r:
                        continue
                    closures = _int_or_none(r.get(cat))
                    # 조회 키에 category 포함! (중복 방지 핵심)
                    lookup = dict(
                        year=wide_year,
                        signgu_cd_nm=name,
                        category=cat,
                    )
                    defaults = dict(
                        signgu_cd=name_to_signgu_cd(name),
                        closures=closures,
                        raw_data=r,
                    )
                    obj, is_created = ClosureStat.objects.update_or_create(
                        **lookup, defaults=defaults
                    )
                    created += int(is_created)
                    updated += int(not is_created)

        else:
            # 세로형 일반 포맷
            for r in read_csv_rows(path, encoding=encoding):
                y = year or _int_or_none(r.get(year_col))
                if not y:
                    skipped += 1
                    continue
                name = _clean(r.get(signgu_nm_col, ""))
                if not name:
                    skipped += 1
                    continue
                if skip_total and name == "서울시":
                    skipped += 1
                    continue

                cat = _clean(r.get(category_col) or "전체")
                val = _int_or_none(r.get(count_col))
                lookup = dict(
                    year=y,
                    signgu_cd_nm=name,
                    category=cat,   # ← 여기 포함
                )
                defaults = dict(
                    signgu_cd=name_to_signgu_cd(name),
                    closures=val,
                    raw_data=r,
                )
                obj, is_created = ClosureStat.objects.update_or_create(
                    **lookup, defaults=defaults
                )
                created += int(is_created)
                updated += int(not is_created)

        self.stdout.write(self.style.SUCCESS(
            f"[ClosureStat] upserted: created={created}, updated={updated}, skipped={skipped}"
        ))
        