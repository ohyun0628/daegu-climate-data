# -*- coding: utf-8 -*-
"""
대구 기후·탄소중립 공공데이터 전처리 파이프라인 (표준 라이브러리 기반)

입력 (data/raw/):
1. 3. 2025 지역 온실가스 통계_대구.xlsx / 15. 2025 지역 온실가스 통계_경북.xlsx
2. ta_20261024004648.csv (기상청 대구 일별 기온, 2020.01~2026.09)
3. 시군구별전력사용량(홈페이지게시용)_202512.xlsx / _202608.xlsx
4. 한국전력공사_산업분류별 법정동별 전력사용량_20251231 (1).csv
5. 대구광역시_공공건축물 현황_20260903.csv
6. 구별 노인/독거노인 및 인구 현황 (달서구, 북구, 서구, 중구)

출력 (data/processed/):
1. weather_monthly_2020_2026.csv        : 연·월별 평균/최고기온, 폭염일수(>=33℃), 냉방도일(CDD, 기준 24℃)
2. electricity_district_monthly.csv    : 대구 9개 구·군 × 계약종별 × 연·월(2025.01~2026.08) 전력사용량(kWh)
3. electricity_dong_2025.csv           : 대구 9개 구·군 × 법정동별 2025년 월별 전력사용량 및 여름철(7~8월) 급증률
4. ghg_district_2010_2023.csv          : 대구 광역 및 구·군별 온실가스 배출량 (2010~2023)
5. district_summary_metrics.csv        : 구·군별 폭염-전력 민감도(여름철 전력 급증률), 건물/전력 비중, 공공건축물 연면적 통합표
6. dong_senior_vulnerability.csv       : 달서구·북구·서구·중구 행정동별 고령/독거노인 현황 정제 테이블
"""

import csv
import re
import xml.etree.ElementTree as ET
import zipfile
from collections import defaultdict
from pathlib import Path

ROOT_DIR = Path(__file__).resolve().parents[2]
RAW_DIR = ROOT_DIR / "data" / "raw"
PROCESSED_DIR = ROOT_DIR / "data" / "processed"

DAEGU_DISTRICTS = [
    "중구",
    "동구",
    "서구",
    "남구",
    "북구",
    "수성구",
    "달서구",
    "달성군",
    "군위군",
]


def read_csv_auto(path: Path):
    for enc in ("utf-8-sig", "cp949", "euc-kr", "utf-8"):
        try:
            with open(path, "r", encoding=enc, newline="") as f:
                return list(csv.reader(f))
        except Exception:
            continue
    raise RuntimeError(f"Cannot decode CSV: {path}")


def read_xlsx_sheets(path: Path):
    """Return list of sheet names and a function to load any sheet as 2D list of strings."""
    z = zipfile.ZipFile(path)
    shared = []
    if "xl/sharedStrings.xml" in z.namelist():
        root = ET.fromstring(z.read("xl/sharedStrings.xml"))
        for si in root.findall("{http://schemas.openxmlformats.org/spreadsheetml/2006/main}si"):
            t = "".join(
                x.text or ""
                for x in si.iter("{http://schemas.openxmlformats.org/spreadsheetml/2006/main}t")
            )
            shared.append(t)
    wb = ET.fromstring(z.read("xl/workbook.xml"))
    sheets = [el.attrib.get("name") for el in wb.iter() if el.tag.endswith("sheet")]

    def load_sheet(sheet_idx: int):
        sname = f"xl/worksheets/sheet{sheet_idx + 1}.xml"
        ws = ET.fromstring(z.read(sname))
        rows = []
        for row in ws.iter("{http://schemas.openxmlformats.org/spreadsheetml/2006/main}row"):
            row_dict = {}
            for c in row:
                ref = c.attrib.get("r", "")
                col_letters = re.sub(r"[0-9]", "", ref)
                col_idx = 0
                for ch in col_letters:
                    col_idx = col_idx * 26 + (ord(ch) - ord("A") + 1)
                t = c.attrib.get("t")
                v = c.find("{http://schemas.openxmlformats.org/spreadsheetml/2006/main}v")
                if v is not None and v.text is not None:
                    val = shared[int(v.text)] if t == "s" else v.text
                else:
                    val = ""
                row_dict[col_idx] = val.strip()
            if row_dict:
                max_c = max(row_dict.keys())
                arr = [row_dict.get(i, "") for i in range(1, max_c + 1)]
                if any(arr):
                    rows.append(arr)
        return rows

    return z, sheets, load_sheet


def to_float(val: str) -> float:
    if not val:
        return 0.0
    cleaned = val.replace(",", "").strip()
    try:
        return float(cleaned)
    except ValueError:
        return 0.0


def process_weather() -> dict:
    """Process KMA daily temperature CSV into monthly metrics (2020-01 ~ 2026-09)."""
    candidates = sorted(RAW_DIR.glob("ta_*.csv"))
    if not candidates:
        raise FileNotFoundError("ta_*.csv not found")
    rows = read_csv_auto(candidates[0])
    header_idx = 0
    for i, r in enumerate(rows):
        if r and "날짜" in r[0]:
            header_idx = i
            break

    monthly = defaultdict(lambda: {
        "days": 0,
        "sum_avg": 0.0,
        "sum_max": 0.0,
        "sum_min": 0.0,
        "max_temp": -999.0,
        "heatwave_days_33": 0,
        "severe_heat_days_35": 0,
        "cdd_24": 0.0,
        "hdd_18": 0.0,
    })

    for r in rows[header_idx + 1:]:
        if len(r) < 5:
            continue
        dt = r[0].strip()
        if not re.match(r"^\d{4}-\d{2}-\d{2}$", dt):
            continue
        ym = dt[:7]
        t_avg = to_float(r[2])
        t_min = to_float(r[3])
        t_max = to_float(r[4])
        m = monthly[ym]
        m["days"] += 1
        m["sum_avg"] += t_avg
        m["sum_min"] += t_min
        m["sum_max"] += t_max
        if t_max > m["max_temp"]:
            m["max_temp"] = t_max
        if t_max >= 33.0:
            m["heatwave_days_33"] += 1
        if t_max >= 35.0:
            m["severe_heat_days_35"] += 1
        if t_avg > 24.0:
            m["cdd_24"] += (t_avg - 24.0)
        if t_avg < 18.0:
            m["hdd_18"] += (18.0 - t_avg)

    out_path = PROCESSED_DIR / "weather_monthly_2020_2026.csv"
    with open(out_path, "w", encoding="utf-8-sig", newline="") as f:
        w = csv.writer(f)
        w.writerow([
            "year_month",
            "year",
            "month",
            "days",
            "avg_temp_c",
            "avg_max_temp_c",
            "avg_min_temp_c",
            "peak_max_temp_c",
            "heatwave_days_33c",
            "severe_heat_days_35c",
            "cooling_degree_days_24c",
            "heating_degree_days_18c",
        ])
        for ym in sorted(monthly.keys()):
            m = monthly[ym]
            d = max(1, m["days"])
            yr, mo = ym.split("-")
            w.writerow([
                ym,
                yr,
                int(mo),
                m["days"],
                round(m["sum_avg"] / d, 2),
                round(m["sum_max"] / d, 2),
                round(m["sum_min"] / d, 2),
                round(m["max_temp"], 1),
                m["heatwave_days_33"],
                m["severe_heat_days_35"],
                round(m["cdd_24"], 2),
                round(m["hdd_18"], 2),
            ])
    return monthly


def process_kepco_district(weather_monthly: dict):
    """Process 2025 & 2026 KEPCO district monthly electricity files for Daegu."""
    records = []
    for path in sorted(RAW_DIR.glob("*시군구별전력사용량*.xlsx")):
        z, sheets, load_sheet = read_xlsx_sheets(path)
        rows = load_sheet(0)  # '계약종별'
        z.close()
        header = None
        for r in rows:
            if len(r) >= 6 and r[0] == "연도" and r[1] == "시도":
                header = r
                break
        if not header:
            continue
        month_cols = []
        for idx, col_name in enumerate(header):
            m_match = re.match(r"^(\d+)월$", col_name)
            if m_match:
                month_cols.append((idx, int(m_match.group(1))))

        for r in rows:
            if len(r) < 5:
                continue
            yr = r[0]
            sido = r[1]
            sgg = r[2]
            contract = r[3].replace(" ", "")
            if sido != "대구광역시":
                continue
            for col_idx, mo in month_cols:
                if col_idx < len(r) and r[col_idx] != "":
                    kwh = to_float(r[col_idx])
                    ym = f"{yr}-{mo:02d}"
                    w_info = weather_monthly.get(ym, {})
                    d = max(1, w_info.get("days", 1))
                    records.append({
                        "year_month": ym,
                        "year": int(yr),
                        "month": mo,
                        "district": sgg,
                        "contract_type": contract,
                        "usage_kwh": round(kwh),
                        "usage_mwh": round(kwh / 1000.0, 2),
                        "avg_temp_c": round(w_info.get("sum_avg", 0.0) / d, 2) if w_info else "",
                        "heatwave_days_33c": w_info.get("heatwave_days_33", ""),
                        "cdd_24c": round(w_info.get("cdd_24", 0.0), 2) if w_info else "",
                    })

    out_path = PROCESSED_DIR / "electricity_district_monthly.csv"
    with open(out_path, "w", encoding="utf-8-sig", newline="") as f:
        w = csv.writer(f)
        w.writerow([
            "year_month",
            "year",
            "month",
            "district",
            "contract_type",
            "usage_kwh",
            "usage_mwh",
            "avg_temp_c",
            "heatwave_days_33c",
            "cdd_24c",
        ])
        for rec in sorted(records, key=lambda x: (x["year_month"], x["district"], x["contract_type"])):
            w.writerow([
                rec["year_month"],
                rec["year"],
                rec["month"],
                rec["district"],
                rec["contract_type"],
                rec["usage_kwh"],
                rec["usage_mwh"],
                rec["avg_temp_c"],
                rec["heatwave_days_33c"],
                rec["cdd_24c"],
            ])
    return records


def process_dong_electricity():
    """Aggregate 2025 legal-dong monthly electricity usage for Daegu."""
    candidates = sorted(RAW_DIR.glob("*법정동별*전력사용량*.csv"))
    if not candidates:
        return []
    rows = read_csv_auto(candidates[0])
    agg = defaultdict(lambda: defaultdict(float))

    for r in rows[1:]:
        if len(r) < 7:
            continue
        sido, sgg, dong, yr, mo, hh, kwh = (x.strip() for x in r[:7])
        if sido != "대구광역시":
            continue
        key = (sgg, dong, yr)
        m_int = int(mo)
        agg[key][m_int] += to_float(kwh)

    out_path = PROCESSED_DIR / "electricity_dong_2025.csv"
    dong_summary = []
    with open(out_path, "w", encoding="utf-8-sig", newline="") as f:
        w = csv.writer(f)
        w.writerow([
            "district",
            "dong",
            "year",
            "annual_mwh",
            "spring_fall_avg_mwh",
            "summer_7_8_avg_mwh",
            "summer_surge_ratio",
            "summer_excess_mwh",
        ])
        for (sgg, dong, yr), m_dict in sorted(agg.items()):
            annual_kwh = sum(m_dict.values())
            base_months = [m_dict.get(m, 0.0) for m in (4, 5, 10) if m_dict.get(m, 0.0) > 0]
            summer_months = [m_dict.get(m, 0.0) for m in (7, 8) if m_dict.get(m, 0.0) > 0]
            base_avg = (sum(base_months) / len(base_months)) if base_months else 0.0
            summer_avg = (sum(summer_months) / len(summer_months)) if summer_months else 0.0
            surge_ratio = (summer_avg / base_avg) if base_avg > 0 else 0.0
            excess_mwh = max(0.0, (summer_avg - base_avg) * 2.0 / 1000.0)
            rec = {
                "district": sgg,
                "dong": dong,
                "year": int(yr),
                "annual_mwh": round(annual_kwh / 1000.0, 1),
                "spring_fall_avg_mwh": round(base_avg / 1000.0, 1),
                "summer_7_8_avg_mwh": round(summer_avg / 1000.0, 1),
                "summer_surge_ratio": round(surge_ratio, 3),
                "summer_excess_mwh": round(excess_mwh, 1),
            }
            dong_summary.append(rec)
            w.writerow(list(rec.values()))
    return dong_summary


def process_ghg_inventory():
    """Extract Daegu regional & district GHG inventory (2010-2023) from GIR xlsx."""
    candidates = [p for p in RAW_DIR.glob("*.xlsx") if "3. 2025" in p.name]
    if not candidates:
        return []
    z, sheets, load_sheet = read_xlsx_sheets(candidates[0])
    records = []

    for idx, sname in enumerate(sheets):
        if "(vkt)" not in sname:
            continue
        rows = load_sheet(idx)
        year_row = None
        for r in rows:
            if "2010" in r and "2023" in r:
                year_row = r
                break
        if not year_row:
            continue
        year_cols = {}
        for c_i, val in enumerate(year_row):
            if re.match(r"^20\d{2}$", val):
                year_cols[int(val)] = c_i

        section_mode = "직접"
        for r in rows:
            joined = " ".join(x for x in r[:4] if x)
            if joined == "간접":
                section_mode = "간접"
                continue
            if len(r) < 4:
                continue
            cat = r[0]
            sido = r[1]
            sgg = r[2]
            if sido != "대구":
                continue
            for yr, c_i in year_cols.items():
                if c_i < len(r) and r[c_i] != "":
                    records.append({
                        "scope": section_mode,
                        "district": sgg,
                        "category": cat,
                        "year": yr,
                        "emissions_gg_co2eq": round(to_float(r[c_i]), 3),
                    })
    z.close()

    out_path = PROCESSED_DIR / "ghg_district_2010_2023.csv"
    with open(out_path, "w", encoding="utf-8-sig", newline="") as f:
        w = csv.writer(f)
        w.writerow(["scope", "district", "category", "year", "emissions_gg_co2eq"])
        for rec in records:
            w.writerow([
                rec["scope"],
                rec["district"],
                rec["category"],
                rec["year"],
                rec["emissions_gg_co2eq"],
            ])
    return records


def process_public_buildings():
    """Aggregate public building count and floor area by Daegu district."""
    candidates = [p for p in RAW_DIR.glob("*.csv") if "공공건축물" in p.name]
    if not candidates:
        return {}
    rows = read_csv_auto(candidates[0])
    stats = defaultdict(lambda: {"count": 0, "area_m2": 0.0})
    for r in rows[1:]:
        if len(r) < 4:
            continue
        addr = r[2]
        area = to_float(r[3])
        matched = None
        for d in DAEGU_DISTRICTS:
            if f"대구광역시 {d}" in addr or f"대구 {d}" in addr:
                matched = d
                break
        if matched:
            stats[matched]["count"] += 1
            stats[matched]["area_m2"] += area
    return stats


def process_dong_senior_vulnerability():
    """Standardize dong-level senior/elderly population CSVs & XLSX (달서구, 북구, 서구, 중구)."""
    records = []

    # 1. 달서구 노인인구 현황
    for p in RAW_DIR.glob("*달서구*노인인구*.csv"):
        rows = read_csv_auto(p)
        for r in rows[1:]:
            if len(r) >= 4 and r[0].strip():
                records.append({
                    "district": "달서구",
                    "dong": r[0].strip(),
                    "metric_type": "65세이상_노인인구",
                    "senior_count": int(to_float(r[1])),
                    "total_pop": "",
                    "senior_share_pct": "",
                    "reference_date": r[5].strip() if len(r) > 5 else "2026-07-06",
                })

    # 2. 북구 행정동별 독거노인 현황
    for p in RAW_DIR.glob("*북구*독거노인*.csv"):
        rows = read_csv_auto(p)
        for r in rows[1:]:
            if len(r) >= 4 and r[2].strip() and "전체" not in r[2]:
                records.append({
                    "district": "북구",
                    "dong": r[2].strip(),
                    "metric_type": "65세이상_독거노인(1인가구)",
                    "senior_count": int(to_float(r[3])),
                    "total_pop": "",
                    "senior_share_pct": "",
                    "reference_date": "2023-12-31",
                })

    # 3. 서구 인구현황 (총인구 + 65세 이상)
    for p in RAW_DIR.glob("*서구*인구현황*.csv"):
        rows = read_csv_auto(p)
        for r in rows[1:]:
            if len(r) >= 9 and r[0].strip():
                tot = int(to_float(r[2]))
                sen = int(to_float(r[8]))
                share = round(sen / tot * 100.0, 2) if tot > 0 else 0.0
                records.append({
                    "district": "서구",
                    "dong": r[0].strip(),
                    "metric_type": "65세이상_노인인구(고령화율포함)",
                    "senior_count": sen,
                    "total_pop": tot,
                    "senior_share_pct": share,
                    "reference_date": r[9].strip() if len(r) > 9 else "2026-06-30",
                })

    # 4. 중구 독거노인인구 현황 XLSX (최신 연도 블록 추출)
    for p in RAW_DIR.glob("*중구*독거노인*.xlsx"):
        z, sheets, load_sheet = read_xlsx_sheets(p)
        rows = load_sheet(0)
        z.close()
        cur_year = ""
        for r in rows:
            txt = " ".join(r)
            if "2018년" in txt:
                cur_year = "2018-12-31"
            elif cur_year == "2018-12-31" and len(r) >= 2:
                dong_name = r[0].strip()
                cnt = int(to_float(r[1]))
                if dong_name and dong_name not in ("구군", "중구") and cnt > 0:
                    records.append({
                        "district": "중구",
                        "dong": dong_name,
                        "metric_type": "주민등록_독거노인",
                        "senior_count": cnt,
                        "total_pop": "",
                        "senior_share_pct": "",
                        "reference_date": cur_year,
                    })

    out_path = PROCESSED_DIR / "dong_senior_vulnerability.csv"
    with open(out_path, "w", encoding="utf-8-sig", newline="") as f:
        w = csv.writer(f)
        w.writerow([
            "district",
            "dong",
            "metric_type",
            "senior_count",
            "total_pop",
            "senior_share_pct",
            "reference_date",
        ])
        for rec in records:
            w.writerow(list(rec.values()))
    return records


def build_district_summary(elec_records, ghg_records, pub_buildings):
    """Build integrated district-level table for modeling and visualization."""
    elec_map = defaultdict(lambda: defaultdict(float))
    for rec in elec_records:
        key = (rec["district"], rec["year"], rec["contract_type"])
        elec_map[key][rec["month"]] = rec["usage_mwh"]

    ghg_2023 = defaultdict(dict)
    for rec in ghg_records:
        if rec["year"] == 2023:
            ghg_2023[rec["district"]][(rec["scope"], rec["category"])] = rec["emissions_gg_co2eq"]

    out_path = PROCESSED_DIR / "district_summary_metrics.csv"
    summary_rows = []
    with open(out_path, "w", encoding="utf-8-sig", newline="") as f:
        w = csv.writer(f)
        w.writerow([
            "district",
            "ghg_total_2023_gg",
            "elec_total_2025_gwh",
            "elec_building_share_pct",
            "summer_2025_surge_pct",
            "summer_2026_surge_pct",
            "cooling_excess_2025_gwh",
            "public_building_count",
            "public_building_area_m2",
        ])
        for d in DAEGU_DISTRICTS:
            tot_2025 = elec_map[(d, 2025, "합계")]
            res_2025 = elec_map[(d, 2025, "주택용")]
            gen_2025 = elec_map[(d, 2025, "일반용")]
            edu_2025 = elec_map[(d, 2025, "교육용")]

            annual_2025_mwh = sum(tot_2025.values())
            bldg_2025_mwh = sum(res_2025.values()) + sum(gen_2025.values()) + sum(edu_2025.values())
            bldg_share = (bldg_2025_mwh / annual_2025_mwh * 100.0) if annual_2025_mwh > 0 else 0.0

            bldg_m_2025 = {m: res_2025.get(m, 0.0) + gen_2025.get(m, 0.0) + edu_2025.get(m, 0.0) for m in range(1, 13)}
            base_25 = (bldg_m_2025[4] + bldg_m_2025[5]) / 2.0
            sum_25 = (bldg_m_2025[7] + bldg_m_2025[8]) / 2.0
            surge_25_pct = ((sum_25 - base_25) / base_25 * 100.0) if base_25 > 0 else 0.0
            excess_25_gwh = max(0.0, (sum_25 - base_25) * 2.0 / 1000.0)

            res_2026 = elec_map[(d, 2026, "주택용")]
            gen_2026 = elec_map[(d, 2026, "일반용")]
            edu_2026 = elec_map[(d, 2026, "교육용")]
            bldg_m_2026 = {m: res_2026.get(m, 0.0) + gen_2026.get(m, 0.0) + edu_2026.get(m, 0.0) for m in range(1, 9)}
            base_26 = (bldg_m_2026[4] + bldg_m_2026[5]) / 2.0
            sum_26 = (bldg_m_2026[7] + bldg_m_2026[8]) / 2.0
            surge_26_pct = ((sum_26 - base_26) / base_26 * 100.0) if base_26 > 0 else 0.0

            ghg_tot = ghg_2023[d].get(("직접", "총배출량"), 0.0)
            pb = pub_buildings.get(d, {"count": 0, "area_m2": 0.0})

            row = [
                d,
                round(ghg_tot, 1),
                round(annual_2025_mwh / 1000.0, 1),
                round(bldg_share, 1),
                round(surge_25_pct, 1),
                round(surge_26_pct, 1),
                round(excess_25_gwh, 2),
                pb["count"],
                round(pb["area_m2"], 1),
            ]
            summary_rows.append(row)
            w.writerow(row)
    return summary_rows


if __name__ == "__main__":
    PROCESSED_DIR.mkdir(parents=True, exist_ok=True)
    weather = process_weather()
    elec = process_kepco_district(weather)
    dong = process_dong_electricity()
    ghg = process_ghg_inventory()
    pub = process_public_buildings()
    seniors = process_dong_senior_vulnerability()
    summary = build_district_summary(elec, ghg, pub)

    print("=== [완료] 생성된 전처리 파일 (data/processed/) ===")
    for p in sorted(PROCESSED_DIR.glob("*.csv")):
        print(f" - {p.name} ({p.stat().st_size:,} bytes)")
    print(f" - 동별 고령/독거노인 레코드 수: {len(seniors)}개 행정동")
