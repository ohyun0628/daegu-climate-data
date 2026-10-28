# -*- coding: utf-8 -*-
"""
대구 기후·탄소중립 공공데이터 AI/통계 모델링 스크립트

수행 분석:
1. 구·군별 기온(검침시차 보정 유효 냉방도일 Effective CDD/HDD) -> 건물전력 수요 다중선형회귀 모델 (OLS)
   - 한전 전력판매량 통계의 검침 시차(당월 50% + 전월 50%)를 반영하여 설명력(R²)을 0.37 -> 0.88+ 수준으로 고도화
   - 폭염 심화(+1℃, +2℃) 시나리오별 구·군 추가 전력수요(MWh) 및 간접 온실가스 배출량(tCO2eq) 예측
2. 구·군별 에너지·탄소 특성 기반 4대 유형 분류 및 건물 탄소중립 우선순위 스코어링
3. 동(洞) 단위 전력 폭염 급증 핫스팟 Top 20 및 행정동 고령/독거노인 취약계층 결합 타깃 도출
"""

import csv
import math
from collections import defaultdict
from pathlib import Path

ROOT_DIR = Path(__file__).resolve().parents[2]
PROCESSED_DIR = ROOT_DIR / "data" / "processed"

# 국가 전력 간접배출계수 (환경부/GIR 기준 0.4594 tCO2eq / MWh)
GRID_EMISSION_FACTOR_TCO2_PER_MWH = 0.4594


def read_csv_dict(path: Path):
    with open(path, "r", encoding="utf-8-sig", newline="") as f:
        return list(csv.DictReader(f))


def prev_year_month(ym: str) -> str:
    yr, mo = map(int, ym.split("-"))
    if mo == 1:
        return f"{yr - 1}-12"
    return f"{yr}-{mo - 1:02d}"


def fit_ols_2var(x1_list, x2_list, y_list):
    """
    Fit y = b0 + b1 * x1 + b2 * x2 via exact normal equations.
    x1 = Effective CDD (유효 냉방도일), x2 = Effective HDD (유효 난방도일), y = 월별 건물전력(MWh)
    """
    n = len(y_list)
    if n < 4:
        return {"b0": 0.0, "b1": 0.0, "b2": 0.0, "r2": 0.0, "rmse": 0.0}

    sx1 = sum(x1_list)
    sx2 = sum(x2_list)
    sy = sum(y_list)
    sx1x1 = sum(x * x for x in x1_list)
    sx2x2 = sum(x * x for x in x2_list)
    sx1x2 = sum(a * b for a, b in zip(x1_list, x2_list))
    sx1y = sum(a * y for a, y in zip(x1_list, y_list))
    sx2y = sum(a * y for a, y in zip(x2_list, y_list))

    A = [
        [float(n), sx1, sx2, sy],
        [sx1, sx1x1, sx1x2, sx1y],
        [sx2, sx1x2, sx2x2, sx2y],
    ]
    for i in range(3):
        pivot = A[i][i]
        if abs(pivot) < 1e-12:
            continue
        for j in range(i, 4):
            A[i][j] /= pivot
        for k in range(3):
            if k != i:
                factor = A[k][i]
                for j in range(i, 4):
                    A[k][j] -= factor * A[i][j]

    b0, b1, b2 = A[0][3], A[1][3], A[2][3]
    y_mean = sy / n
    ss_tot = sum((y - y_mean) ** 2 for y in y_list)
    ss_res = sum((y - (b0 + b1 * x1 + b2 * x2)) ** 2 for x1, x2, y in zip(x1_list, x2_list, y_list))
    r2 = 1.0 - (ss_res / ss_tot) if ss_tot > 0 else 0.0
    rmse = math.sqrt(ss_res / n)
    return {"b0": b0, "b1": b1, "b2": b2, "r2": r2, "rmse": rmse}


def run_cdd_regression():
    """1. 구·군별 검침시차 보정 기온 민감도(Effective CDD/HDD -> 건물전력) 회귀모델 및 시나리오 예측."""
    elec_rows = read_csv_dict(PROCESSED_DIR / "electricity_district_monthly.csv")
    weather_rows = read_csv_dict(PROCESSED_DIR / "weather_monthly_2020_2026.csv")
    w_map = {r["year_month"]: r for r in weather_rows}

    bldg_monthly = defaultdict(float)
    res_monthly = defaultdict(float)
    gen_monthly = defaultdict(float)

    for r in elec_rows:
        ym = r["year_month"]
        d = r["district"]
        ct = r["contract_type"]
        mwh = float(r["usage_mwh"])
        if ct in ("주택용", "일반용", "교육용"):
            bldg_monthly[(d, ym)] += mwh
        if ct == "주택용":
            res_monthly[(d, ym)] += mwh
        elif ct == "일반용":
            gen_monthly[(d, ym)] += mwh

    districts = sorted({r["district"] for r in elec_rows})
    yms = sorted({r["year_month"] for r in elec_rows})

    ADD_CDD_PLUS_1C = 95.0
    ADD_CDD_PLUS_2C = 195.0

    results = []
    out_path = PROCESSED_DIR / "model_district_climate_sensitivity.csv"
    with open(out_path, "w", encoding="utf-8-sig", newline="") as f:
        w = csv.writer(f)
        w.writerow([
            "district",
            "base_monthly_mwh",
            "cdd_slope_mwh_per_cdd",
            "hdd_slope_mwh_per_hdd",
            "r_squared_unadjusted",
            "r_squared_lag_adjusted",
            "rmse_mwh",
            "res_cdd_slope",
            "gen_cdd_slope",
            "pred_plus1c_summer_mwh",
            "pred_plus2c_summer_mwh",
            "pred_plus2c_co2_ton",
        ])
        for d in districts:
            raw_cdd, raw_hdd = [], []
            eff_cdd, eff_hdd = [], []
            y_bldg, y_res, y_gen = [], [], []

            for ym in yms:
                prev_ym = prev_year_month(ym)
                if (d, ym) in bldg_monthly and ym in w_map and prev_ym in w_map:
                    c_now = float(w_map[ym]["cooling_degree_days_24c"])
                    c_prev = float(w_map[prev_ym]["cooling_degree_days_24c"])
                    h_now = float(w_map[ym]["heating_degree_days_18c"])
                    h_prev = float(w_map[prev_ym]["heating_degree_days_18c"])

                    raw_cdd.append(c_now)
                    raw_hdd.append(h_now)
                    # 한전 월별 판매량은 전월 검침분(약 50%)과 당월 검침분(약 50%)의 결합
                    eff_cdd.append(0.5 * c_now + 0.5 * c_prev)
                    eff_hdd.append(0.5 * h_now + 0.5 * h_prev)

                    y_bldg.append(bldg_monthly[(d, ym)])
                    y_res.append(res_monthly[(d, ym)])
                    y_gen.append(gen_monthly[(d, ym)])

            fit_raw = fit_ols_2var(raw_cdd, raw_hdd, y_bldg)
            fit_eff = fit_ols_2var(eff_cdd, eff_hdd, y_bldg)
            fit_res = fit_ols_2var(eff_cdd, eff_hdd, y_res)
            fit_gen = fit_ols_2var(eff_cdd, eff_hdd, y_gen)

            plus1_mwh = max(0.0, fit_eff["b1"] * ADD_CDD_PLUS_1C)
            plus2_mwh = max(0.0, fit_eff["b1"] * ADD_CDD_PLUS_2C)
            plus2_co2 = plus2_mwh * GRID_EMISSION_FACTOR_TCO2_PER_MWH

            rec = {
                "district": d,
                "base_monthly_mwh": round(fit_eff["b0"], 1),
                "cdd_slope_mwh_per_cdd": round(fit_eff["b1"], 2),
                "hdd_slope_mwh_per_hdd": round(fit_eff["b2"], 2),
                "r_squared_unadjusted": round(fit_raw["r2"], 3),
                "r_squared_lag_adjusted": round(fit_eff["r2"], 3),
                "rmse_mwh": round(fit_eff["rmse"], 1),
                "res_cdd_slope": round(fit_res["b1"], 2),
                "gen_cdd_slope": round(fit_gen["b1"], 2),
                "pred_plus1c_summer_mwh": round(plus1_mwh, 1),
                "pred_plus2c_summer_mwh": round(plus2_mwh, 1),
                "pred_plus2c_co2_ton": round(plus2_co2, 1),
            }
            results.append(rec)
            w.writerow(list(rec.values()))
    return results


def run_district_clustering_and_priority(reg_results):
    """2. 구·군별 특성 군집화 및 건물 탄소중립 투자 우선순위 지수 산출."""
    summary_rows = read_csv_dict(PROCESSED_DIR / "district_summary_metrics.csv")
    reg_map = {r["district"]: r for r in reg_results}

    merged = []
    for r in summary_rows:
        d = r["district"]
        reg = reg_map.get(d, {})
        bldg_share = float(r["elec_building_share_pct"])
        surge_25 = float(r["summer_2025_surge_pct"])
        excess_gwh = float(r["cooling_excess_2025_gwh"])
        cdd_slope = float(reg.get("cdd_slope_mwh_per_cdd", 0.0))
        pub_area = float(r["public_building_area_m2"])
        ghg_tot = float(r["ghg_total_2023_gg"])

        merged.append({
            "district": d,
            "ghg_total_2023_gg": ghg_tot,
            "elec_building_share_pct": bldg_share,
            "summer_2025_surge_pct": surge_25,
            "cooling_excess_2025_gwh": excess_gwh,
            "cdd_slope_mwh_per_cdd": cdd_slope,
            "r_squared": float(reg.get("r_squared_lag_adjusted", 0.0)),
            "pred_plus2c_co2_ton": float(reg.get("pred_plus2c_co2_ton", 0.0)),
            "public_building_count": int(r["public_building_count"]),
            "public_building_area_m2": pub_area,
        })

    def minmax(vals):
        lo, hi = min(vals), max(vals)
        return [(v - lo) / (hi - lo) if hi > lo else 0.0 for v in vals]

    n_slope = minmax([m["cdd_slope_mwh_per_cdd"] for m in merged])
    n_surge = minmax([m["summer_2025_surge_pct"] for m in merged])
    n_bldg = minmax([m["elec_building_share_pct"] for m in merged])
    n_pub = minmax([m["public_building_area_m2"] for m in merged])

    out_path = PROCESSED_DIR / "model_district_priority.csv"
    with open(out_path, "w", encoding="utf-8-sig", newline="") as f:
        w = csv.writer(f)
        w.writerow([
            "rank",
            "district",
            "cluster_type",
            "priority_score",
            "cdd_slope_mwh_per_cdd",
            "r_squared",
            "summer_2025_surge_pct",
            "cooling_excess_2025_gwh",
            "elec_building_share_pct",
            "pred_plus2c_co2_ton",
            "public_building_count",
            "public_building_area_m2",
            "policy_recommendation",
        ])

        for i, m in enumerate(merged):
            score = (
                0.40 * n_slope[i]
                + 0.25 * n_surge[i]
                + 0.20 * n_bldg[i]
                + 0.15 * n_pub[i]
            ) * 100.0
            m["priority_score"] = round(score, 1)

            if m["cooling_excess_2025_gwh"] >= 85.0 and m["elec_building_share_pct"] >= 50.0:
                m["cluster_type"] = "유형 I: 대규모 냉방피크 핵심감축권"
                m["policy"] = "공공·대형건물 그린리모델링 및 고효율 냉방기기(BEMS) 집중 투자"
            elif m["elec_building_share_pct"] >= 60.0 and m["summer_2025_surge_pct"] >= 45.0:
                m["cluster_type"] = "유형 II: 고밀도 도심·주거 폭염민감권"
                m["policy"] = "노후 주거·상가 쿨루프 시공 및 폭염 취약계층 무더위쉼터 확충"
            elif m["elec_building_share_pct"] < 35.0 and m["ghg_total_2023_gg"] > 1000.0:
                m["cluster_type"] = "유형 III: 산업단지 공정·산단태양광 전환권"
                m["policy"] = "스마트그린산단 지붕형 태양광 및 산업공정 고효율 인버터 보급"
            else:
                m["cluster_type"] = "유형 IV: 저밀도 농촌·도농복합 관리권"
                m["policy"] = "영농형·주민참여형 태양광(햇빛소득마을) 및 경로당 소규모 단열 지원"

        merged.sort(key=lambda x: x["priority_score"], reverse=True)
        for rank_idx, m in enumerate(merged, start=1):
            m["rank"] = rank_idx
            w.writerow([
                rank_idx,
                m["district"],
                m["cluster_type"],
                m["priority_score"],
                m["cdd_slope_mwh_per_cdd"],
                m["r_squared"],
                m["summer_2025_surge_pct"],
                m["cooling_excess_2025_gwh"],
                m["elec_building_share_pct"],
                m["pred_plus2c_co2_ton"],
                m["public_building_count"],
                m["public_building_area_m2"],
                m["policy"],
            ])
    return merged


def run_dong_hotspot_analysis():
    """3. 법정동별 여름 전력 급증 상위 핫스팟 및 행정동 고령·독거노인 취약순위 도출."""
    dong_elec = read_csv_dict(PROCESSED_DIR / "electricity_dong_2025.csv")
    seniors = read_csv_dict(PROCESSED_DIR / "dong_senior_vulnerability.csv")

    valid_dongs = [
        {
            "district": r["district"],
            "dong": r["dong"],
            "annual_mwh": float(r["annual_mwh"]),
            "summer_surge_pct": round((float(r["summer_surge_ratio"]) - 1.0) * 100.0, 1),
            "summer_excess_mwh": float(r["summer_excess_mwh"]),
            "summer_co2_ton": round(float(r["summer_excess_mwh"]) * GRID_EMISSION_FACTOR_TCO2_PER_MWH, 1),
        }
        for r in dong_elec
        if float(r["annual_mwh"]) >= 300.0
    ]
    valid_dongs.sort(key=lambda x: x["summer_excess_mwh"], reverse=True)

    out_path = PROCESSED_DIR / "model_dong_cooling_hotspots_top20.csv"
    with open(out_path, "w", encoding="utf-8-sig", newline="") as f:
        w = csv.writer(f)
        w.writerow([
            "rank",
            "district",
            "dong",
            "annual_mwh",
            "summer_surge_pct",
            "summer_excess_mwh",
            "summer_co2_ton",
        ])
        for idx, d in enumerate(valid_dongs[:20], start=1):
            w.writerow([
                idx,
                d["district"],
                d["dong"],
                d["annual_mwh"],
                d["summer_surge_pct"],
                d["summer_excess_mwh"],
                d["summer_co2_ton"],
            ])

    by_dist = defaultdict(list)
    for s in seniors:
        by_dist[s["district"]].append({
            "district": s["district"],
            "dong": s["dong"],
            "metric_type": s["metric_type"],
            "senior_count": int(s["senior_count"]),
            "senior_share_pct": float(s["senior_share_pct"]) if s["senior_share_pct"] else None,
        })
    for dist in by_dist:
        by_dist[dist].sort(key=lambda x: x["senior_count"], reverse=True)

    return valid_dongs[:15], by_dist


if __name__ == "__main__":
    reg = run_cdd_regression()
    priority = run_district_clustering_and_priority(reg)
    top_dongs, senior_by_dist = run_dong_hotspot_analysis()

    print("=== [1] 구·군별 기온(유효 냉방도일 CDD) 회귀모델 및 탄소배출 민감도 우선순위 ===")
    print("순위 | 구군 | 우선점수 | 유형 | CDD기울기(MWh/CDD) | 보정R² | +2℃시 추가CO2(톤) | 여름초과(GWh)")
    for p in priority:
        print(
            f" {p['rank']:2d}  | {p['district']:4s} | {p['priority_score']:6.1f}점 | "
            f"{p['cluster_type']:28s} | {p['cdd_slope_mwh_per_cdd']:16.2f} | "
            f" {p['r_squared']:.3f} | {p['pred_plus2c_co2_ton']:15.1f} | {p['cooling_excess_2025_gwh']:10.2f}"
        )

    print("\n=== [2] 대구 법정동별 여름철 냉방전력 급증 Top 10 핫스팟 ===")
    for idx, d in enumerate(top_dongs[:10], start=1):
        print(
            f" {idx:2d}. {d['district']:4s} {d['dong']:6s} | 여름초과: {d['summer_excess_mwh']:6.1f} MWh "
            f"(+{d['summer_surge_pct']:5.1f}%) | 냉방탄소: {d['summer_co2_ton']:5.1f} tCO2eq"
        )

    print("\n=== [3] 구별 고령·독거노인 밀집 Top 3 행정동 (쿨루프·무더위쉼터 최우선지) ===")
    for dist, items in senior_by_dist.items():
        top3 = ", ".join(f"{x['dong']}({x['senior_count']:,}명)" for x in items[:3])
        print(f" - {dist}: {top3}")
