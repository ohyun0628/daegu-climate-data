# -*- coding: utf-8 -*-
"""
심층 AI·시계열 분석 모듈 (Upgrade Step 1)

1. 2010~2023년(14년) 대구 광역 및 9개 구·군 온실가스 좌(직접배출 col 0~16)·우(간접배출 col 18~34) 정밀 분리 추출
   - 군위군의 2010~2022년 배출량은 '15. 2025 지역 온실가스 통계_경북.xlsx'에서 추출하여 14년 시계열 완결성 확보
   - 구·군별 '건물 직접배출(도시가스·열)' + '건물 간접배출(상업·가정·공공 전력)' 합산 건물 총배출량 산출
2. 기온 비선형 임계점 탐지 (Piecewise Threshold Regression Optimization)
   - 검침시차 보정 유효 평균기온(Effective Temp) 기준으로 각 구·군에서 냉방전력이 급격히 꺾여 올라가는
     임계온도(Threshold Temperature, T*)와 냉방 민감도 기울기(MWh/℃) 탐색
3. 주택용(가정 에어컨) vs 일반용(상업·업무 빌딩) vs 교육용 폭염 냉방전력 기여도 분해
"""

import csv
import math
import re
import xml.etree.ElementTree as ET
import zipfile
from collections import defaultdict
from pathlib import Path

ROOT_DIR = Path(__file__).resolve().parents[2]
RAW_DIR = ROOT_DIR / "data" / "raw"
PROCESSED_DIR = ROOT_DIR / "data" / "processed"


def read_csv_dict(path: Path):
    with open(path, "r", encoding="utf-8-sig", newline="") as f:
        return list(csv.DictReader(f))


def to_float(val: str) -> float:
    if not val:
        return 0.0
    cleaned = val.replace(",", "").strip()
    try:
        return float(cleaned)
    except ValueError:
        return 0.0


def load_all_rows_from_xlsx(path: Path):
    z = zipfile.ZipFile(path)
    shared = []
    if "xl/sharedStrings.xml" in z.namelist():
        root = ET.fromstring(z.read("xl/sharedStrings.xml"))
        for si in root.findall("{http://schemas.openxmlformats.org/spreadsheetml/2006/main}si"):
            shared.append(
                "".join(
                    x.text or ""
                    for x in si.iter("{http://schemas.openxmlformats.org/spreadsheetml/2006/main}t")
                )
            )
    wb = ET.fromstring(z.read("xl/workbook.xml"))
    sheets = [el.attrib.get("name") for el in wb.iter() if el.tag.endswith("sheet")]

    def get_sheet_rows(sheet_idx: int):
        ws = ET.fromstring(z.read(f"xl/worksheets/sheet{sheet_idx + 1}.xml"))
        rows = []
        for row in ws.iter("{http://schemas.openxmlformats.org/spreadsheetml/2006/main}row"):
            row_dict = {}
            for c in row:
                col_letters = re.sub(r"[0-9]", "", c.attrib.get("r", ""))
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

    return z, sheets, get_sheet_rows


def extract_full_14yr_ghg():
    """
    GIR 엑셀 시트 내 좌측 표(col 0~16: 직접배출)와 우측 표(col 18~34: 간접배출)를 분리 추출.
    """
    daegu_xlsx = [p for p in RAW_DIR.glob("*.xlsx") if "3. 2025" in p.name][0]
    gb_xlsx = [p for p in RAW_DIR.glob("*.xlsx") if "15. 2025" in p.name][0]

    records = []

    def parse_workbook(xlsx_path: Path, filter_gunwi_only: bool = False):
        z, sheets, get_sheet_rows = load_all_rows_from_xlsx(xlsx_path)
        for idx, sname in enumerate(sheets):
            if "(vkt)" not in sname:
                continue
            if filter_gunwi_only and "군위" not in sname:
                continue
            rows = get_sheet_rows(idx)
            direct_year_cols = {}
            indirect_year_cols = {}

            for r in rows:
                if len(r) >= 17 and r[0] == "구분" and r[3] == "2010":
                    for c_i in range(3, min(17, len(r))):
                        if re.match(r"^20\d{2}$", r[c_i]):
                            direct_year_cols[int(r[c_i])] = c_i
                    for c_i in range(21, min(35, len(r))):
                        if re.match(r"^20\d{2}$", r[c_i]):
                            indirect_year_cols[int(r[c_i])] = c_i
                    break

            if not direct_year_cols:
                continue

            indirect_parent = ""
            for r in rows:
                # 1) Left table: 직접배출 (col 0, 1, 2)
                if len(r) >= 4 and r[1] in ("대구", "경북"):
                    cat_d = r[0].strip()
                    sgg_d = r[2].strip()
                    for yr, c_i in direct_year_cols.items():
                        if filter_gunwi_only and yr >= 2023:
                            continue
                        if c_i < len(r) and r[c_i] != "":
                            records.append({
                                "scope": "직접",
                                "district": sgg_d,
                                "category": cat_d,
                                "year": yr,
                                "emissions_gg": round(to_float(r[c_i]), 3),
                            })

                # 2) Right table: 간접배출 (col 18, 19, 20)
                if len(r) >= 22 and r[19] in ("대구", "경북"):
                    cat_i = r[18].strip()
                    sgg_i = r[20].strip()
                    if cat_i in ("전력", "열", "폐기물"):
                        indirect_parent = cat_i
                        full_cat = f"간접_{cat_i}_합계"
                    elif cat_i.startswith(("1.", "2.", "3.", "4.", "5.", "A.", "B.", "C.", "D.")):
                        full_cat = f"간접_{indirect_parent}_{cat_i}"
                    else:
                        full_cat = cat_i

                    for yr, c_i in indirect_year_cols.items():
                        if filter_gunwi_only and yr >= 2023:
                            continue
                        if c_i < len(r) and r[c_i] != "":
                            records.append({
                                "scope": "간접",
                                "district": sgg_i,
                                "category": full_cat,
                                "year": yr,
                                "emissions_gg": round(to_float(r[c_i]), 3),
                            })
        z.close()

    parse_workbook(daegu_xlsx, filter_gunwi_only=False)
    parse_workbook(gb_xlsx, filter_gunwi_only=True)

    out_full = PROCESSED_DIR / "ghg_district_2010_2023.csv"
    with open(out_full, "w", encoding="utf-8-sig", newline="") as f:
        w = csv.writer(f)
        w.writerow(["scope", "district", "category", "year", "emissions_gg_co2eq"])
        for rec in records:
            w.writerow([
                rec["scope"],
                rec["district"],
                rec["category"],
                rec["year"],
                rec["emissions_gg"],
            ])

    by_dist_yr = defaultdict(dict)
    for rec in records:
        by_dist_yr[(rec["district"], rec["year"])][(rec["scope"], rec["category"])] = rec["emissions_gg"]

    out_struct = PROCESSED_DIR / "ghg_daegu_14yr_structure.csv"
    struct_rows = []
    with open(out_struct, "w", encoding="utf-8-sig", newline="") as f:
        w = csv.writer(f)
        w.writerow([
            "district",
            "year",
            "direct_total_gg",
            "indirect_elec_total_gg",
            "direct_building_fuel_gg",
            "indirect_building_elec_gg",
            "total_building_gg",
            "transport_total_gg",
            "industry_total_gg",
            "total_city_emissions_gg",
            "building_emissions_share_pct",
            "building_elec_share_in_bldg_pct",
        ])
        for (dist, yr), m in sorted(by_dist_yr.items()):
            direct_tot = m.get(("직접", "총배출량"), 0.0)
            indirect_elec_tot = m.get(("간접", "간접_전력_합계"), 0.0)

            # 건물 직접연료(도시가스·등유 등: 직접 -> 4. 기타) + 건물 간접전력(간접 -> 전력 -> 4. 기타)
            bldg_fuel = m.get(("직접", "4.  기타"), 0.0)
            bldg_elec = m.get(("간접", "간접_전력_4.  기타"), 0.0)
            tot_bldg = bldg_fuel + bldg_elec

            # 수송(직접 + 간접전력) 및 제조업(직접 + 간접전력)
            trans_tot = m.get(("직접", "3.  수송"), 0.0) + m.get(("간접", "간접_전력_3.  수송"), 0.0)
            ind_tot = m.get(("직접", "2.  제조업 및 건설업"), 0.0) + m.get(("간접", "간접_전력_2.  제조업 및 건설업"), 0.0)

            # 지자체 관리 총배출(에너지산업 발전소 자체배출 제외한 지역 총배출 관점: 직접총배출 - 에너지산업 + 간접전력)
            energy_ind = m.get(("직접", "1.  에너지산업"), 0.0)
            city_tot = (direct_tot - energy_ind) + indirect_elec_tot
            if city_tot <= 0:
                city_tot = direct_tot + indirect_elec_tot

            bldg_share = (tot_bldg / city_tot * 100.0) if city_tot > 0 else 0.0
            elec_in_bldg = (bldg_elec / tot_bldg * 100.0) if tot_bldg > 0 else 0.0

            row = {
                "district": dist,
                "year": yr,
                "direct_total_gg": round(direct_tot, 2),
                "indirect_elec_total_gg": round(indirect_elec_tot, 2),
                "direct_building_fuel_gg": round(bldg_fuel, 2),
                "indirect_building_elec_gg": round(bldg_elec, 2),
                "total_building_gg": round(tot_bldg, 2),
                "transport_total_gg": round(trans_tot, 2),
                "industry_total_gg": round(ind_tot, 2),
                "total_city_emissions_gg": round(city_tot, 2),
                "building_emissions_share_pct": round(bldg_share, 1),
                "building_elec_share_in_bldg_pct": round(elec_in_bldg, 1),
            }
            struct_rows.append(row)
            w.writerow(list(row.values()))

    return records, struct_rows


def prev_ym(ym: str) -> str:
    yr, mo = map(int, ym.split("-"))
    return f"{yr - 1}-12" if mo == 1 else f"{yr}-{mo - 1:02d}"


def run_piecewise_threshold_and_sector_decomposition():
    """
    기온 임계점(Threshold Temperature T*) 그리드 최적화 및
    계약종별(주택용 vs 일반용 vs 교육용) 폭염 냉방전력 기여도 분해.
    """
    elec_rows = read_csv_dict(PROCESSED_DIR / "electricity_district_monthly.csv")
    weather_rows = read_csv_dict(PROCESSED_DIR / "weather_monthly_2020_2026.csv")
    w_map = {r["year_month"]: r for r in weather_rows}

    by_dist_ct = defaultdict(lambda: defaultdict(float))
    for r in elec_rows:
        d = r["district"]
        ym = r["year_month"]
        ct = r["contract_type"]
        by_dist_ct[(d, ct)][ym] = float(r["usage_mwh"])

    districts = sorted({r["district"] for r in elec_rows})
    yms = sorted({r["year_month"] for r in elec_rows})

    out_path = PROCESSED_DIR / "model_threshold_and_sector.csv"
    results = []

    with open(out_path, "w", encoding="utf-8-sig", newline="") as f:
        w = csv.writer(f)
        w.writerow([
            "district",
            "optimal_threshold_temp_c",
            "piecewise_r2",
            "cooling_slope_above_threshold_mwh_per_c",
            "heating_slope_below_14c_mwh_per_c",
            "heat_vs_cold_sensitivity_ratio",
            "summer_excess_residential_gwh",
            "summer_excess_commercial_gwh",
            "summer_excess_education_gwh",
            "residential_cooling_share_pct",
            "commercial_cooling_share_pct",
            "dominant_cooling_sector",
        ])

        for d in districts:
            eff_temps = []
            y_bldg = []
            for ym in yms:
                p_ym = prev_ym(ym)
                if ym in w_map and p_ym in w_map:
                    t_eff = 0.5 * float(w_map[ym]["avg_temp_c"]) + 0.5 * float(w_map[p_ym]["avg_temp_c"])
                    b_mwh = (
                        by_dist_ct[(d, "주택용")].get(ym, 0.0)
                        + by_dist_ct[(d, "일반용")].get(ym, 0.0)
                        + by_dist_ct[(d, "교육용")].get(ym, 0.0)
                    )
                    if b_mwh > 0:
                        eff_temps.append(t_eff)
                        y_bldg.append(b_mwh)

            best_t = 21.0
            best_r2 = -1.0
            best_cool_slope = 0.0
            best_heat_slope = 0.0

            for step in range(28):
                t_cand = 18.0 + step * 0.25
                x_cool = [max(0.0, t - t_cand) for t in eff_temps]
                x_heat = [max(0.0, 14.0 - t) for t in eff_temps]
                n = len(y_bldg)
                sx1, sx2, sy = sum(x_cool), sum(x_heat), sum(y_bldg)
                sx1x1 = sum(a * a for a in x_cool)
                sx2x2 = sum(b * b for b in x_heat)
                sx1x2 = sum(a * b for a, b in zip(x_cool, x_heat))
                sx1y = sum(a * y for a, y in zip(x_cool, y_bldg))
                sx2y = sum(b * y for b, y in zip(x_heat, y_bldg))

                A = [
                    [float(n), sx1, sx2, sy],
                    [sx1, sx1x1, sx1x2, sx1y],
                    [sx2, sx1x2, sx2x2, sx2y],
                ]
                for i in range(3):
                    piv = A[i][i]
                    if abs(piv) < 1e-12:
                        continue
                    for j in range(i, 4):
                        A[i][j] /= piv
                    for k in range(3):
                        if k != i:
                            fac = A[k][i]
                            for j in range(i, 4):
                                A[k][j] -= fac * A[i][j]
                b0, b1, b2 = A[0][3], A[1][3], A[2][3]
                y_mean = sy / n
                ss_tot = sum((y - y_mean) ** 2 for y in y_bldg)
                ss_res = sum(
                    (y - (b0 + b1 * c + b2 * h)) ** 2
                    for c, h, y in zip(x_cool, x_heat, y_bldg)
                )
                r2 = 1.0 - (ss_res / ss_tot) if ss_tot > 0 else 0.0
                if r2 > best_r2:
                    best_r2 = r2
                    best_t = t_cand
                    best_cool_slope = b1
                    best_heat_slope = b2

            def calc_excess_gwh(ct_name: str) -> float:
                m_series = by_dist_ct[(d, ct_name)]
                base = (m_series.get("2025-04", 0.0) + m_series.get("2025-05", 0.0)) / 2.0
                peak = (m_series.get("2025-07", 0.0) + m_series.get("2025-08", 0.0)) / 2.0
                return max(0.0, (peak - base) * 2.0 / 1000.0)

            res_ex = calc_excess_gwh("주택용")
            com_ex = calc_excess_gwh("일반용")
            edu_ex = calc_excess_gwh("교육용")
            tot_ex = res_ex + com_ex + edu_ex
            res_share = (res_ex / tot_ex * 100.0) if tot_ex > 0 else 0.0
            com_share = (com_ex / tot_ex * 100.0) if tot_ex > 0 else 0.0

            if res_share >= 51.5:
                dom_sector = "주거(공동·단독주택) 에어컨 주도형"
            elif com_share >= 53.0:
                dom_sector = "상업·업무빌딩 냉방 주도형"
            else:
                dom_sector = "주거·상업 복합 냉방 피크형"

            ratio = (best_cool_slope / best_heat_slope) if best_heat_slope > 0 else 0.0
            rec = {
                "district": d,
                "optimal_threshold_temp_c": round(best_t, 2),
                "piecewise_r2": round(best_r2, 3),
                "cooling_slope_above_threshold_mwh_per_c": round(best_cool_slope, 1),
                "heating_slope_below_14c_mwh_per_c": round(best_heat_slope, 1),
                "heat_vs_cold_sensitivity_ratio": round(ratio, 2),
                "summer_excess_residential_gwh": round(res_ex, 2),
                "summer_excess_commercial_gwh": round(com_ex, 2),
                "summer_excess_education_gwh": round(edu_ex, 2),
                "residential_cooling_share_pct": round(res_share, 1),
                "commercial_cooling_share_pct": round(com_share, 1),
                "dominant_cooling_sector": dom_sector,
            }
            results.append(rec)
            w.writerow(list(rec.values()))

    return results


def match_priority_public_buildings():
    """대구 공공건축물 현황과 법정동 냉방전력 급증·구군 우선순위를 결합하여 그린리모델링 Top 20 도출."""
    raw_candidates = list(RAW_DIR.glob("*공공건축물*.csv"))
    if not raw_candidates:
        return []
    dong_elec = read_csv_dict(PROCESSED_DIR / "electricity_dong_2025.csv")
    prio_rows = read_csv_dict(PROCESSED_DIR / "model_district_priority.csv")

    dong_surge = {(r["district"], r["dong"]): float(r["summer_surge_ratio"]) for r in dong_elec}
    dist_score = {r["district"]: float(r["priority_score"]) for r in prio_rows}

    rows = []
    for enc in ("cp949", "utf-8-sig", "euc-kr"):
        try:
            with open(raw_candidates[0], "r", encoding=enc, newline="") as f:
                rows = list(csv.reader(f))
            break
        except Exception:
            continue

    candidates = []
    for r in rows[1:]:
        if len(r) < 4:
            continue
        name, addr, area = r[1].strip(), r[2].strip(), to_float(r[3])
        if area < 500:
            continue
        dist = next((d for d in dist_score if f" {d} " in addr), "")
        if not dist:
            continue
        m_dong = re.search(r"\(([가-힣0-9]+동|[가-힣]+읍|[가-힣]+면)\)", addr)
        dong = m_dong.group(1) if m_dong else ""
        surge = dong_surge.get((dist, dong), 1.35)
        score = round(dist_score[dist] * 0.5 + min(100.0, math.log10(max(10.0, area)) * 20.0) * 0.3 + min(100.0, (surge - 1.0) * 100.0) * 0.2, 1)
        candidates.append({
            "district": dist,
            "dong": dong,
            "building_name": name,
            "address": addr,
            "floor_area_m2": round(area, 1),
            "dong_summer_surge_pct": round((surge - 1.0) * 100.0, 1),
            "retrofit_priority_score": score,
        })

    candidates.sort(key=lambda x: (x["retrofit_priority_score"], x["floor_area_m2"]), reverse=True)
    out_path = PROCESSED_DIR / "model_public_building_targets_top20.csv"
    with open(out_path, "w", encoding="utf-8-sig", newline="") as f:
        w = csv.writer(f)
        w.writerow(["rank", "district", "dong", "building_name", "address", "floor_area_m2", "dong_summer_surge_pct", "retrofit_priority_score"])
        for i, c in enumerate(candidates[:20], 1):
            w.writerow([i, c["district"], c["dong"], c["building_name"], c["address"], c["floor_area_m2"], c["dong_summer_surge_pct"], c["retrofit_priority_score"]])
    return candidates[:20]


if __name__ == "__main__":
    records, struct_rows = extract_full_14yr_ghg()
    thresh_results = run_piecewise_threshold_and_sector_decomposition()
    bldg_targets = match_priority_public_buildings()

    print("=== [1] 대구 광역 온실가스 14년(2010~2023) 건물 직접(연료) vs 간접(전력) 구조 변화 ===")
    for r in struct_rows:
        if r["district"] == "광역" and r["year"] in (2010, 2015, 2018, 2020, 2023):
            print(
                f" {r['year']}년 | 건물총배출: {r['total_building_gg']:6.1f} Gg "
                f"(도시배출의 {r['building_emissions_share_pct']:4.1f}%) | "
                f"건물직접연료: {r['direct_building_fuel_gg']:6.1f} Gg vs 건물전력(간접): {r['indirect_building_elec_gg']:6.1f} Gg "
                f"(전력비중 {r['building_elec_share_in_bldg_pct']:4.1f}%)"
            )

    print("\n=== [2] 2023년 대구 9개 구·군별 건물 온실가스(직접연료 + 간접전력) 비중 ===")
    for r in struct_rows:
        if r["year"] == 2023 and r["district"] != "광역":
            print(
                f" - {r['district']:4s}: 건물총배출 {r['total_building_gg']:6.1f} Gg "
                f"(구 전체의 {r['building_emissions_share_pct']:4.1f}%, 건물 내 전력비중 {r['building_elec_share_in_bldg_pct']:4.1f}%)"
            )
