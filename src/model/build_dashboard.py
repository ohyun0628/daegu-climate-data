# -*- coding: utf-8 -*-
"""
data/processed/ 의 정제 및 심층 AI 모델링 결과 CSV를 기반으로
대구 9개 구·군 인터랙티브 지도(SVG Choropleth) + 14년 온실가스 구조 변화 +
비선형 임계온도(T*) 및 계약종별 분해가 포함된 웹 대시보드 (web/index.html) 생성 스크립트.
"""

import csv
import json
from pathlib import Path

ROOT_DIR = Path(__file__).resolve().parents[2]
PROCESSED_DIR = ROOT_DIR / "data" / "processed"
WEB_DIR = ROOT_DIR / "web"


def read_csv_dict(path: Path):
    with open(path, "r", encoding="utf-8-sig", newline="") as f:
        return list(csv.DictReader(f))


def load_dashboard_payload():
    priority = read_csv_dict(PROCESSED_DIR / "model_district_priority.csv")
    sensitivity = read_csv_dict(PROCESSED_DIR / "model_district_climate_sensitivity.csv")
    threshold = read_csv_dict(PROCESSED_DIR / "model_threshold_and_sector.csv")
    ghg_14yr = read_csv_dict(PROCESSED_DIR / "ghg_daegu_14yr_structure.csv")
    hotspots = read_csv_dict(PROCESSED_DIR / "model_dong_cooling_hotspots_top20.csv")
    seniors = read_csv_dict(PROCESSED_DIR / "dong_senior_vulnerability.csv")
    weather = read_csv_dict(PROCESSED_DIR / "weather_monthly_2020_2026.csv")
    elec_m = read_csv_dict(PROCESSED_DIR / "electricity_district_monthly.csv")

    yms = sorted({r["year_month"] for r in elec_m})
    dist_series = {}
    for d_row in priority:
        d = d_row["district"]
        dist_series[d] = {ym: 0.0 for ym in yms}

    for r in elec_m:
        d = r["district"]
        ym = r["year_month"]
        if r["contract_type"] in ("주택용", "일반용", "교육용") and d in dist_series:
            dist_series[d][ym] = round(dist_series[d][ym] + float(r["usage_mwh"]) / 1000.0, 2)

    w_map = {r["year_month"]: r for r in weather}
    monthly_timeline = []
    for ym in yms:
        w = w_map.get(ym, {})
        monthly_timeline.append({
            "ym": ym,
            "avg_temp": float(w.get("avg_temp_c", 0.0)),
            "peak_temp": float(w.get("peak_max_temp_c", 0.0)),
            "heatwave_days": int(w.get("heatwave_days_33c", 0)),
            "cdd": float(w.get("cooling_degree_days_24c", 0.0)),
        })

    # 14-year GHG series by district (including 광역)
    ghg_by_dist = {}
    for r in ghg_14yr:
        d = r["district"]
        if d == "기타":
            continue
        ghg_by_dist.setdefault(d, []).append({
            "year": int(r["year"]),
            "direct_bldg": float(r["direct_building_fuel_gg"]),
            "indirect_bldg_elec": float(r["indirect_building_elec_gg"]),
            "total_bldg": float(r["total_building_gg"]),
            "bldg_share": float(r["building_emissions_share_pct"]),
            "elec_in_bldg_share": float(r["building_elec_share_in_bldg_pct"]),
        })
    for d in ghg_by_dist:
        ghg_by_dist[d].sort(key=lambda x: x["year"])

    senior_top = {}
    for s in seniors:
        dist = s["district"]
        senior_top.setdefault(dist, []).append({
            "dong": s["dong"],
            "metric_type": s["metric_type"],
            "count": int(s["senior_count"]),
            "share": float(s["senior_share_pct"]) if s["senior_share_pct"] else None,
        })
    for dist in senior_top:
        senior_top[dist].sort(key=lambda x: x["count"], reverse=True)
        senior_top[dist] = senior_top[dist][:5]

    return {
        "priority": priority,
        "sensitivity": sensitivity,
        "threshold": threshold,
        "ghg_14yr": ghg_by_dist,
        "hotspots": hotspots[:12],
        "senior_top": senior_top,
        "timeline": monthly_timeline,
        "district_series_gwh": dist_series,
    }


def generate_html(payload: dict) -> str:
    data_json = json.dumps(payload, ensure_ascii=False)
    return f"""<!DOCTYPE html>
<html lang="ko">
<head>
  <meta charset="UTF-8" />
  <meta name="viewport" content="width=device-width, initial-scale=1.0" />
  <title>대구 폭염-건물전력 탄소민감도 분석 및 그린리모델링 우선순위 대시보드</title>
  <script src="https://cdn.jsdelivr.net/npm/chart.js@4.4.1/dist/chart.umd.min.js"></script>
  <style>
    :root {{
      --bg: #0d1217;
      --surface: #151d24;
      --surface-2: #1c2731;
      --border: #2a3946;
      --text: #eef3f7;
      --muted: #95a7b8;
      --accent: #38bdf8;
      --warn: #f59e0b;
      --danger: #f43f5e;
      --success: #10b981;
    }}
    * {{ box-sizing: border-box; margin: 0; padding: 0; }}
    body {{
      font-family: 'Pretendard', -apple-system, BlinkMacSystemFont, 'Malgun Gothic', sans-serif;
      background: var(--bg);
      color: var(--text);
      line-height: 1.55;
      padding: 26px 20px 64px;
    }}
    .container {{ max-width: 1280px; margin: 0 auto; }}
    header {{
      border-bottom: 1px solid var(--border);
      padding-bottom: 18px;
      margin-bottom: 22px;
      display: flex;
      justify-content: space-between;
      align-items: flex-end;
      flex-wrap: wrap;
      gap: 16px;
    }}
    .badge {{
      display: inline-block;
      font-size: 12px;
      font-weight: 600;
      color: var(--accent);
      border: 1px solid rgba(56, 189, 248, 0.4);
      padding: 4px 10px;
      border-radius: 999px;
      margin-bottom: 8px;
    }}
    h1 {{ font-size: 25px; font-weight: 700; letter-spacing: -0.02em; }}
    .subtitle {{ color: var(--muted); font-size: 13.5px; margin-top: 6px; }}
    .kpi-grid {{
      display: grid;
      grid-template-columns: repeat(4, 1fr);
      gap: 14px;
      margin-bottom: 20px;
    }}
    .kpi-card {{
      background: var(--surface);
      border: 1px solid var(--border);
      border-radius: 10px;
      padding: 15px 18px;
    }}
    .kpi-label {{ font-size: 12px; color: var(--muted); }}
    .kpi-val {{ font-size: 23px; font-weight: 700; margin-top: 5px; }}
    .kpi-sub {{ font-size: 11.5px; color: var(--muted); margin-top: 4px; }}
    .callout {{
      background: var(--surface-2);
      border-left: 4px solid var(--accent);
      border-radius: 8px;
      padding: 14px 18px;
      margin-bottom: 22px;
      font-size: 13.5px;
    }}
    .callout strong {{ color: var(--accent); }}
    .grid-map-hero {{
      display: grid;
      grid-template-columns: 1.05fr 0.95fr;
      gap: 18px;
      margin-bottom: 22px;
    }}
    .grid-2 {{
      display: grid;
      grid-template-columns: 1.12fr 0.88fr;
      gap: 18px;
      margin-bottom: 22px;
    }}
    .grid-equal {{
      display: grid;
      grid-template-columns: 1fr 1fr;
      gap: 18px;
      margin-bottom: 22px;
    }}
    .panel {{
      background: var(--surface);
      border: 1px solid var(--border);
      border-radius: 10px;
      padding: 18px 20px;
    }}
    .panel-header {{
      display: flex;
      justify-content: space-between;
      align-items: center;
      margin-bottom: 10px;
      gap: 10px;
      flex-wrap: wrap;
    }}
    .panel-title {{ font-size: 15.5px; font-weight: 700; }}
    .panel-caption {{ font-size: 12px; color: var(--muted); margin-bottom: 12px; }}
    select, button {{
      background: var(--surface-2);
      color: var(--text);
      border: 1px solid var(--border);
      border-radius: 6px;
      padding: 6px 11px;
      font-size: 12.5px;
      cursor: pointer;
    }}
    button.active {{
      background: var(--accent);
      color: #0b131a;
      border-color: var(--accent);
      font-weight: 700;
    }}
    .btn-group {{ display: flex; gap: 6px; flex-wrap: wrap; }}
    .chart-box {{ position: relative; height: 275px; width: 100%; }}
    .map-wrap {{
      display: flex;
      flex-direction: column;
      align-items: center;
      justify-content: center;
    }}
    svg#daeguMap {{
      width: 100%;
      max-width: 490px;
      height: 360px;
      user-select: none;
    }}
    .dist-poly {{
      stroke: #0d1217;
      stroke-width: 2.2px;
      cursor: pointer;
      transition: opacity 0.15s, stroke-width 0.15s;
    }}
    .dist-poly:hover {{ opacity: 0.88; }}
    .dist-poly.selected {{
      stroke: #ffffff;
      stroke-width: 3.5px;
    }}
    .dist-label {{
      fill: #ffffff;
      font-size: 12px;
      font-weight: 700;
      text-anchor: middle;
      pointer-events: none;
    }}
    .dist-val-label {{
      fill: rgba(255,255,255,0.88);
      font-size: 10.5px;
      text-anchor: middle;
      pointer-events: none;
    }}
    .detail-box {{
      background: var(--surface-2);
      border: 1px solid var(--border);
      border-radius: 8px;
      padding: 14px 16px;
      margin-top: 10px;
    }}
    .detail-grid {{
      display: grid;
      grid-template-columns: repeat(3, 1fr);
      gap: 10px;
      margin-top: 10px;
    }}
    .mini-stat {{
      background: var(--surface);
      border: 1px solid var(--border);
      border-radius: 6px;
      padding: 8px 10px;
    }}
    .mini-stat .k {{ font-size: 11px; color: var(--muted); }}
    .mini-stat .v {{ font-size: 15px; font-weight: 700; margin-top: 2px; }}
    table {{
      width: 100%;
      border-collapse: collapse;
      font-size: 12.8px;
    }}
    th, td {{
      padding: 8.5px 10px;
      border-bottom: 1px solid var(--border);
      text-align: left;
    }}
    th {{ color: var(--muted); font-weight: 600; font-size: 11.8px; background: rgba(255,255,255,0.02); }}
    td.num, th.num {{ text-align: right; font-variant-numeric: tabular-nums; }}
    tr.clickable-row {{ cursor: pointer; }}
    tr.clickable-row:hover {{ background: rgba(56, 189, 248, 0.08); }}
    .tag {{
      display: inline-block;
      padding: 2px 8px;
      border-radius: 4px;
      font-size: 11px;
      font-weight: 600;
    }}
    .tag-1 {{ background: rgba(244, 63, 94, 0.18); color: #fda4af; }}
    .tag-2 {{ background: rgba(245, 158, 11, 0.18); color: #fcd34d; }}
    .tag-3 {{ background: rgba(56, 189, 248, 0.18); color: #7dd3fc; }}
    .tag-4 {{ background: rgba(16, 185, 129, 0.18); color: #6ee7b7; }}
    footer {{
      margin-top: 32px;
      padding-top: 16px;
      border-top: 1px solid var(--border);
      font-size: 12px;
      color: var(--muted);
    }}
    @media (max-width: 980px) {{
      .kpi-grid, .grid-map-hero, .grid-2, .grid-equal {{ grid-template-columns: 1fr; }}
    }}
  </style>
</head>
<body>
  <div class="container">
    <header>
      <div>
        <span class="badge">2026 대구광역시 기후·환경·탄소중립 공공데이터 AI 활용대회 · 부문 2</span>
        <h1>폭염이 밀어 올리는 대구 건물 탄소배출: 구·동 단위 핀셋 투자 지도</h1>
        <p class="subtitle">온실가스 14년 인벤토리(2010–2023) × 기상청 일별기온(2020–2026) × 한전 구·법정동 전력 × 취약계층 통합 AI 모델링</p>
      </div>
      <div style="text-align:right; font-size:12px; color:var(--muted);">
        <div>지도에서 구·군을 클릭하면 모든 차트가 연동됩니다</div>
        <div>모델: 검침시차 보정 다중회귀(R² 0.91~0.93) 및 비선형 임계온도(T*) 탐색</div>
      </div>
    </header>

    <section class="kpi-grid">
      <div class="kpi-card">
        <div class="kpi-label">비선형 임계온도(T*) 회귀 설명력 (R²)</div>
        <div class="kpi-val" style="color:var(--success);">최대 0.955</div>
        <div class="kpi-sub">유효기온 19.0~19.8℃ 돌파 시 냉방기울기 2.8~5.9배 폭증</div>
      </div>
      <div class="kpi-card">
        <div class="kpi-label">대구 건물 배출 내 간접전력 비중 (2023)</div>
        <div class="kpi-val" style="color:var(--accent);">69.0% (4,069Gg)</div>
        <div class="kpi-sub">2010년 63.8% → 2023년 69.0% (중구 74.7% · 달서구 73.3%)</div>
      </div>
      <div class="kpi-card">
        <div class="kpi-label">여름 평균기온 +2℃ 상승 시 대구 건물 추가배출</div>
        <div class="kpi-val" style="color:var(--danger);">+283,270 tCO₂eq</div>
        <div class="kpi-sub">달서·북·수성·동구 4개 구가 추가 배출의 68% 차지</div>
      </div>
      <div class="kpi-card">
        <div class="kpi-label">냉방탄소 감축 × 독거노인 최우선 핀셋 타깃</div>
        <div class="kpi-val" style="color:var(--warn);">북구 산격동 · 달서 진천동</div>
        <div class="kpi-sub">산격동 여름초과 1위(272.7MWh) & 독거노인 1,379명</div>
      </div>
    </section>

    <div class="callout">
      <strong>핵심 스토리라인:</strong> 대구 건물 온실가스의 <strong>69.0%(중구 74.7%, 달서구 73.3%)는 도시가스가 아닌 '전력(간접배출)'</strong>에서 발생하며,
      비선형 임계점 AI 탐색 결과 유효 평균기온이 <strong>19.0~19.75℃를 넘어서는 순간 냉방 전력 증가율이 난방 대비 최대 5.89배(서구)·3.42배(달서구)</strong>로 꺾여 올라갑니다.
      아래 <strong>대구 9개 구·군 인터랙티브 지도</strong>를 클릭하여 구별 맞춤형 처방과 시계열 추이를 확인해 보세요.
    </div>

    <!-- HERO SECTION: Interactive Daegu Map + Selected District Diagnostic & 14-Year GHG Trend -->
    <section class="grid-map-hero">
      <div class="panel">
        <div class="panel-header">
          <div class="panel-title">1. 대구 9개 구·군 기후민감도 공간 지도 (클릭 시 구별 상세 연동)</div>
          <div class="btn-group">
            <button id="mapBtnPriority" class="active" onclick="setMapMetric('priority')">투자 우선점수</button>
            <button id="mapBtnSlope" onclick="setMapMetric('slope')">냉방 민감도(MWh/CDD)</button>
            <button id="mapBtnSurge" onclick="setMapMetric('surge')">여름 급증률(%)</button>
            <button id="mapBtnElecShare" onclick="setMapMetric('elecShare')">건물전력 비중(%)</button>
          </div>
        </div>
        <p class="panel-caption" id="mapCaption">현재 표시: 건물 탄소중립·쿨루프 투자 우선순위 종합점수 (100점 만점, 붉을수록 최우선)</p>
        <div class="map-wrap">
          <svg id="daeguMap" viewBox="0 0 500 390" xmlns="http://www.w3.org/2000/svg">
            <!-- 군위군 (북부 편입 구역) -->
            <polygon id="poly-군위군" class="dist-poly" points="195,12 365,12 385,78 320,118 205,112 175,65" onclick="selectDistrict('군위군')" />
            <text x="282" y="58" class="dist-label">군위군</text>
            <text id="val-군위군" x="282" y="75" class="dist-val-label"></text>

            <!-- 동구 (팔공산·혁신도시 동북부) -->
            <polygon id="poly-동구" class="dist-poly" points="265,116 420,115 445,195 385,235 280,220 262,168" onclick="selectDistrict('동구')" />
            <text x="352" y="172" class="dist-label">동구</text>
            <text id="val-동구" x="352" y="189" class="dist-val-label"></text>

            <!-- 북구 (금호강 북부·산격·칠곡) -->
            <polygon id="poly-북구" class="dist-poly" points="155,112 265,116 262,168 232,198 158,195 140,152" onclick="selectDistrict('북구')" />
            <text x="205" y="154" class="dist-label">북구</text>
            <text id="val-북구" x="205" y="171" class="dist-val-label"></text>

            <!-- 서구 (도심 서측) -->
            <polygon id="poly-서구" class="dist-poly" points="138,195 212,196 210,235 145,238 128,215" onclick="selectDistrict('서구')" />
            <text x="172" y="214" class="dist-label">서구</text>
            <text id="val-서구" x="172" y="229" class="dist-val-label"></text>

            <!-- 중구 (도심 핵심) -->
            <polygon id="poly-중구" class="dist-poly" points="212,196 272,198 270,236 210,235" onclick="selectDistrict('중구')" />
            <text x="241" y="214" class="dist-label">중구</text>
            <text id="val-중구" x="241" y="229" class="dist-val-label"></text>

            <!-- 남구 (도심 남측) -->
            <polygon id="poly-남구" class="dist-poly" points="205,235 268,236 262,282 198,278" onclick="selectDistrict('남구')" />
            <text x="233" y="256" class="dist-label">남구</text>
            <text id="val-남구" x="233" y="271" class="dist-val-label"></text>

            <!-- 수성구 (동남측 주거·학원 밀집) -->
            <polygon id="poly-수성구" class="dist-poly" points="272,208 385,235 375,305 262,288 268,236" onclick="selectDistrict('수성구')" />
            <text x="322" y="255" class="dist-label">수성구</text>
            <text id="val-수성구" x="322" y="272" class="dist-val-label"></text>

            <!-- 달서구 (서남측 대규모 주거·성서) -->
            <polygon id="poly-달서구" class="dist-poly" points="122,238 205,235 198,278 182,315 112,298 105,260" onclick="selectDistrict('달서구')" />
            <text x="155" y="272" class="dist-label">달서구</text>
            <text id="val-달서구" x="155" y="289" class="dist-val-label"></text>

            <!-- 달성군 (서부·남부 산업단지 및 외곽) -->
            <polygon id="poly-달성군" class="dist-poly" points="52,175 138,175 128,215 105,260 112,298 182,315 262,288 310,335 245,378 85,372 42,295" onclick="selectDistrict('달성군')" />
            <text x="135" y="346" class="dist-label">달성군</text>
            <text id="val-달성군" x="135" y="363" class="dist-val-label"></text>
          </svg>
        </div>

        <div class="detail-box" id="selectedDistrictCard">
          <div style="display:flex; justify-content:space-between; align-items:center;">
            <strong id="selTitle" style="font-size:15px; color:var(--accent);">달서구 (우선순위 1위 · 81.7점)</strong>
            <span id="selCluster" class="tag tag-1">유형 I: 대규모 냉방피크 핵심감축권</span>
          </div>
          <p id="selPolicy" style="font-size:12.5px; color:var(--text); margin-top:6px;"></p>
          <div class="detail-grid">
            <div class="mini-stat"><div class="k">폭염 임계기온 (T*)</div><div class="v" id="selThresh">-</div></div>
            <div class="mini-stat"><div class="k">냉방/난방 민감도 배수</div><div class="v" id="selRatio">-</div></div>
            <div class="mini-stat"><div class="k">주도 냉방 부문</div><div class="v" id="selDominant" style="font-size:12.5px;">-</div></div>
          </div>
        </div>
      </div>

      <div class="panel">
        <div class="panel-header">
          <div class="panel-title">2. 건물 온실가스 14년 추이: 직접연료(가스) vs 간접전력 (2010–2023)</div>
          <select id="ghgDistSelect"></select>
        </div>
        <p class="panel-caption">기후에너지환경부(GIR) 공식 인벤토리 좌·우 시트 분리 추출 결과 (단위: Gg CO₂eq = 천톤)</p>
        <div class="chart-box" style="height:245px;">
          <canvas id="ghg14YrChart"></canvas>
        </div>
        <hr style="border:none; border-top:1px solid var(--border); margin:16px 0;" />
        <div class="panel-header" style="margin-bottom:6px;">
          <div class="panel-title" style="font-size:14.5px;">3. 구·군별 여름 폭염 초과전력 부문 분해 (주택용 vs 상업·일반용)</div>
        </div>
        <p class="panel-caption">2025년 폭염기(7~8월) 건물 냉방 초과전력(GWh)의 계약종별 기여 비중</p>
        <div class="chart-box" style="height:195px;">
          <canvas id="sectorDecompChart"></canvas>
        </div>
      </div>
    </section>

    <section class="grid-2">
      <div class="panel">
        <div class="panel-header">
          <div class="panel-title">4. 구·군별 월별 건물전력 추이 및 폭염(냉방도일) 동조화 (2025.01–2026.08)</div>
          <select id="districtSelect"></select>
        </div>
        <p class="panel-caption">막대: 선택 구·군의 월별 건물전력 사용량(주택+일반+교육용, GWh) / 선: 대구 월간 냉방도일(CDD, 기준 24℃)</p>
        <div class="chart-box">
          <canvas id="timelineChart"></canvas>
        </div>
      </div>

      <div class="panel">
        <div class="panel-header">
          <div class="panel-title">5. 폭염 심화 시나리오별 구·군 추가 탄소배출량 예측</div>
          <div class="btn-group">
            <button id="btnPlus1" onclick="setScenario(1)">+1℃ 시나리오</button>
            <button id="btnPlus2" class="active" onclick="setScenario(2)">+2℃ 시나리오</button>
          </div>
        </div>
        <p class="panel-caption">검침시차 보정 유효 냉방도일 회귀모델 기반 여름철 추가 간접배출량 (단위: tCO₂eq)</p>
        <div class="chart-box">
          <canvas id="scenarioChart"></canvas>
        </div>
      </div>
    </section>

    <section class="panel" style="margin-bottom:22px;">
      <div class="panel-header">
        <div class="panel-title">6. 대구 9개 구·군 탄소중립 투자 우선순위 스코어카드 (행 클릭 시 지도·차트 연동)</div>
      </div>
      <p class="panel-caption">
        우선순위 점수(100점 만점) = 냉방전력 민감도 기울기(40%) + 여름철 전력 급증률(25%) + 건물전력 비중(20%) + 공공건축물 연면적(15%)
      </p>
      <div style="overflow-x:auto;">
        <table id="priorityTable">
          <thead>
            <tr>
              <th>순위</th>
              <th>구·군</th>
              <th>분류 유형</th>
              <th class="num">우선점수</th>
              <th class="num">CDD 민감도</th>
              <th class="num">비선형 임계점(T*)</th>
              <th class="num">설명력 (R²)</th>
              <th class="num">여름 급증률</th>
              <th class="num">여름 초과전력</th>
              <th class="num">건물전력 비중</th>
              <th class="num">공공건축물</th>
              <th>맞춤형 탄소중립 정책 처방</th>
            </tr>
          </thead>
          <tbody></tbody>
        </table>
      </div>
    </section>

    <section class="grid-equal">
      <div class="panel">
        <div class="panel-header">
          <div class="panel-title">7. 법정동별 여름철(7~8월) 냉방전력 급증 Top 12 핫스팟</div>
        </div>
        <p class="panel-caption">2025년 봄·가을(4·5·10월) 대비 여름(7·8월) 초과 전력사용량 및 간접 탄소배출량 상위 법정동</p>
        <div style="overflow-x:auto;">
          <table id="hotspotTable">
            <thead>
              <tr>
                <th>순위</th>
                <th>구·군</th>
                <th>법정동</th>
                <th class="num">연간 전력 (MWh)</th>
                <th class="num">여름 급증률</th>
                <th class="num">여름 초과전력 (MWh)</th>
                <th class="num">냉방 탄소배출 (tCO₂eq)</th>
              </tr>
            </thead>
            <tbody></tbody>
          </table>
        </div>
      </div>

      <div class="panel">
        <div class="panel-header">
          <div class="panel-title">8. 행정동별 고령·독거노인 밀집 Top 5 (쿨루프·무더위쉼터 타깃)</div>
          <select id="seniorDistSelect">
            <option value="달서구">달서구 (65세 이상 노인인구)</option>
            <option value="북구">북구 (65세 이상 독거노인 1인가구)</option>
            <option value="서구">서구 (65세 이상 노인 및 고령화율)</option>
            <option value="중구">중구 (주민등록 독거노인)</option>
          </select>
        </div>
        <p class="panel-caption">폭염 시 냉방 에너지 비용 부담과 온열질환 위험이 동시에 높은 최우선 기후적응 행정동</p>
        <div class="chart-box" style="height:250px;">
          <canvas id="seniorChart"></canvas>
        </div>
      </div>
    </section>

    <footer>
      <div><strong>활용 공공데이터 출처 (공공누리 제1유형 및 제한없음):</strong> ① 기후에너지환경부 온실가스종합정보센터(GIR) 2025 지역 온실가스 통계(대구·경북, 2010–2023) · ② 기상청 기상자료개방포털 대구(143) 일별 기온자료(2020.01–2026.09) · ③ 한국전력공사 시군구별(2025.01–2026.08) 및 법정동별(2025) 전력판매량 · ④ 대구광역시 공공건축물 현황(2026.09) 및 달서구·북구·서구·중구 노인·독거노인 인구통계</div>
    </footer>
  </div>

  <script>
    const DATA = {data_json};

    const prioMap = {{}};
    DATA.priority.forEach(r => {{ prioMap[r.district] = r; }});
    const sensMap = {{}};
    DATA.sensitivity.forEach(s => {{ sensMap[s.district] = s; }});
    const threshMap = {{}};
    DATA.threshold.forEach(t => {{ threshMap[t.district] = t; }});

    let currentMapMetric = 'priority';
    let selectedDist = '달서구';

    function colorScale(normVal) {{
      // Interpolate from cool slate-blue (#1e3a5f) -> amber (#d97706) -> crimson (#e11d48)
      const v = Math.max(0, Math.min(1, normVal));
      if (v < 0.5) {{
        const t = v * 2;
        const r = Math.round(30 + t * (217 - 30));
        const g = Math.round(58 + t * (119 - 58));
        const b = Math.round(95 + t * (6 - 95));
        return `rgb(${{r}},${{g}},${{b}})`;
      }} else {{
        const t = (v - 0.5) * 2;
        const r = Math.round(217 + t * (225 - 217));
        const g = Math.round(119 + t * (29 - 119));
        const b = Math.round(6 + t * (72 - 6));
        return `rgb(${{r}},${{g}},${{b}})`;
      }}
    }}

    function updateMapDisplay() {{
      const vals = DATA.priority.map(r => {{
        if (currentMapMetric === 'priority') return Number(r.priority_score);
        if (currentMapMetric === 'slope') return Number(r.cdd_slope_mwh_per_cdd);
        if (currentMapMetric === 'surge') return Number(r.summer_2025_surge_pct);
        return Number(r.elec_building_share_pct);
      }});
      const minV = Math.min(...vals);
      const maxV = Math.max(...vals);

      DATA.priority.forEach(r => {{
        const d = r.district;
        let raw = Number(r.priority_score);
        let labelTxt = `${{raw.toFixed(1)}}점`;
        if (currentMapMetric === 'slope') {{
          raw = Number(r.cdd_slope_mwh_per_cdd);
          labelTxt = `${{raw.toFixed(0)}}MWh`;
        }} else if (currentMapMetric === 'surge') {{
          raw = Number(r.summer_2025_surge_pct);
          labelTxt = `+${{raw.toFixed(1)}}%`;
        }} else if (currentMapMetric === 'elecShare') {{
          raw = Number(r.elec_building_share_pct);
          labelTxt = `${{raw.toFixed(1)}}%`;
        }}
        const norm = maxV > minV ? (raw - minV) / (maxV - minV) : 0.5;
        const poly = document.getElementById(`poly-${{d}}`);
        const valEl = document.getElementById(`val-${{d}}`);
        if (poly) {{
          poly.setAttribute('fill', colorScale(norm));
          poly.classList.toggle('selected', d === selectedDist);
        }}
        if (valEl) valEl.textContent = labelTxt;
      }});
    }}

    window.setMapMetric = function(metric) {{
      currentMapMetric = metric;
      document.getElementById('mapBtnPriority').classList.toggle('active', metric === 'priority');
      document.getElementById('mapBtnSlope').classList.toggle('active', metric === 'slope');
      document.getElementById('mapBtnSurge').classList.toggle('active', metric === 'surge');
      document.getElementById('mapBtnElecShare').classList.toggle('active', metric === 'elecShare');
      const captions = {{
        priority: '현재 표시: 건물 탄소중립·쿨루프 투자 우선순위 종합점수 (100점 만점, 붉을수록 최우선)',
        slope: '현재 표시: 유효 냉방도일 1 CDD 증가당 월간 건물전력 증가량 (MWh/CDD)',
        surge: '현재 표시: 봄(4~5월) 대비 여름 폭염기(7~8월) 건물전력 급증률 (%)',
        elecShare: '현재 표시: 구·군 전체 전력 중 건물(주택+일반+교육용) 전력 비중 (%)'
      }};
      document.getElementById('mapCaption').textContent = captions[metric];
      updateMapDisplay();
    }};

    // Populate Priority Table
    const tbody = document.querySelector('#priorityTable tbody');
    DATA.priority.forEach(r => {{
      const d = r.district;
      const th = threshMap[d] || {{}};
      let tagClass = 'tag-4';
      if (r.cluster_type.includes('유형 I:')) tagClass = 'tag-1';
      else if (r.cluster_type.includes('유형 II:')) tagClass = 'tag-2';
      else if (r.cluster_type.includes('유형 III:')) tagClass = 'tag-3';

      const tr = document.createElement('tr');
      tr.className = 'clickable-row';
      tr.onclick = () => selectDistrict(d);
      tr.innerHTML = `
        <td><strong>${{r.rank}}</strong></td>
        <td><strong>${{d}}</strong></td>
        <td><span class="tag ${{tagClass}}">${{r.cluster_type}}</span></td>
        <td class="num"><strong>${{Number(r.priority_score).toFixed(1)}}점</strong></td>
        <td class="num">${{Number(r.cdd_slope_mwh_per_cdd).toFixed(1)}}</td>
        <td class="num" style="color:#f59e0b;font-weight:600;">${{th.optimal_threshold_temp_c || '-'}}℃ (${{th.heat_vs_cold_sensitivity_ratio || '-'}}배)</td>
        <td class="num" style="color:#10b981;font-weight:600;">${{Number(th.piecewise_r2 || r.r_squared).toFixed(3)}}</td>
        <td class="num">+${{Number(r.summer_2025_surge_pct).toFixed(1)}}%</td>
        <td class="num">${{Number(r.cooling_excess_2025_gwh).toFixed(1)}} GWh</td>
        <td class="num">${{Number(r.elec_building_share_pct).toFixed(1)}}%</td>
        <td class="num">${{r.public_building_count}}개소</td>
        <td>${{r.policy_recommendation}}</td>
      `;
      tbody.appendChild(tr);
    }});

    // Populate Hotspot Table
    const hbody = document.querySelector('#hotspotTable tbody');
    DATA.hotspots.forEach(h => {{
      const tr = document.createElement('tr');
      tr.innerHTML = `
        <td>${{h.rank}}</td>
        <td>${{h.district}}</td>
        <td><strong>${{h.dong}}</strong></td>
        <td class="num">${{Number(h.annual_mwh).toLocaleString()}}</td>
        <td class="num" style="color:#f59e0b;">+${{Number(h.summer_surge_pct).toFixed(1)}}%</td>
        <td class="num"><strong>${{Number(h.summer_excess_mwh).toFixed(1)}}</strong></td>
        <td class="num">${{Number(h.summer_co2_ton).toFixed(1)}}</td>
      `;
      hbody.appendChild(tr);
    }});

    // Setup GHG 14-year Chart
    const ghgSelect = document.getElementById('ghgDistSelect');
    ['광역', ...DATA.priority.map(r => r.district)].forEach(d => {{
      const opt = document.createElement('option');
      opt.value = d;
      opt.textContent = d === '광역' ? '대구광역시 전체 (광역 합계)' : `${{d}} (2010–2023 추이)`;
      ghgSelect.appendChild(opt);
    }});

    const ctxGhg = document.getElementById('ghg14YrChart').getContext('2d');
    const initGhgSeries = DATA.ghg_14yr['광역'] || [];
    const ghg14YrChart = new Chart(ctxGhg, {{
      type: 'bar',
      data: {{
        labels: initGhgSeries.map(x => x.year),
        datasets: [
          {{
            label: '건물 간접전력 배출 (Gg CO₂eq)',
            data: initGhgSeries.map(x => x.indirect_bldg_elec),
            backgroundColor: 'rgba(56, 189, 248, 0.75)',
            stack: 'bldg'
          }},
          {{
            label: '건물 직접연료(가스·열) 배출 (Gg CO₂eq)',
            data: initGhgSeries.map(x => x.direct_bldg),
            backgroundColor: 'rgba(245, 158, 11, 0.72)',
            stack: 'bldg'
          }}
        ]
      }},
      options: {{
        responsive: true,
        maintainAspectRatio: false,
        plugins: {{ legend: {{ labels: {{ color: '#eef3f7', boxWidth: 12 }} }} }},
        scales: {{
          x: {{ stacked: true, ticks: {{ color: '#95a7b8' }}, grid: {{ display: false }} }},
          y: {{ stacked: true, ticks: {{ color: '#95a7b8' }}, grid: {{ color: 'rgba(255,255,255,0.06)' }} }}
        }}
      }}
    }});

    function updateGhgChart(distKey) {{
      const series = DATA.ghg_14yr[distKey] || [];
      ghg14YrChart.data.labels = series.map(x => x.year);
      ghg14YrChart.data.datasets[0].data = series.map(x => x.indirect_bldg_elec);
      ghg14YrChart.data.datasets[1].data = series.map(x => x.direct_bldg);
      ghg14YrChart.update();
    }}

    ghgSelect.addEventListener('change', e => updateGhgChart(e.target.value));

    // Setup Sector Decomposition Chart (Residential vs Commercial vs Education cooling surge)
    const orderedDistricts = DATA.priority.map(p => p.district);
    const ctxSec = document.getElementById('sectorDecompChart').getContext('2d');
    new Chart(ctxSec, {{
      type: 'bar',
      data: {{
        labels: orderedDistricts,
        datasets: [
          {{
            label: '주택용 냉방초과 (GWh)',
            data: orderedDistricts.map(d => Number(threshMap[d].summer_excess_residential_gwh)),
            backgroundColor: 'rgba(244, 63, 94, 0.75)',
            stack: 'sec'
          }},
          {{
            label: '일반용(상업·업무) 냉방초과 (GWh)',
            data: orderedDistricts.map(d => Number(threshMap[d].summer_excess_commercial_gwh)),
            backgroundColor: 'rgba(56, 189, 248, 0.75)',
            stack: 'sec'
          }},
          {{
            label: '교육용 냉방초과 (GWh)',
            data: orderedDistricts.map(d => Number(threshMap[d].summer_excess_education_gwh)),
            backgroundColor: 'rgba(16, 185, 129, 0.75)',
            stack: 'sec'
          }}
        ]
      }},
      options: {{
        responsive: true,
        maintainAspectRatio: false,
        plugins: {{ legend: {{ labels: {{ color: '#eef3f7', boxWidth: 12 }} }} }},
        scales: {{
          x: {{ stacked: true, ticks: {{ color: '#eef3f7' }}, grid: {{ display: false }} }},
          y: {{ stacked: true, ticks: {{ color: '#95a7b8' }}, grid: {{ color: 'rgba(255,255,255,0.06)' }} }}
        }}
      }}
    }});

    // Timeline Chart
    const distSelect = document.getElementById('districtSelect');
    DATA.priority.forEach(r => {{
      const opt = document.createElement('option');
      opt.value = r.district;
      opt.textContent = `${{r.district}} (우선순위 ${{r.rank}}위 · R²=${{r.r_squared}})`;
      distSelect.appendChild(opt);
    }});

    const labels = DATA.timeline.map(t => t.ym);
    const cddValues = DATA.timeline.map(t => t.cdd);

    const ctx1 = document.getElementById('timelineChart').getContext('2d');
    const timelineChart = new Chart(ctx1, {{
      type: 'bar',
      data: {{
        labels,
        datasets: [
          {{
            label: '달서구 건물전력 (GWh)',
            data: labels.map(ym => DATA.district_series_gwh['달서구'][ym]),
            backgroundColor: 'rgba(56, 189, 248, 0.65)',
            borderRadius: 4,
            yAxisID: 'y',
            order: 2
          }},
          {{
            label: '월간 냉방도일 (CDD)',
            data: cddValues,
            type: 'line',
            borderColor: '#f43f5e',
            backgroundColor: '#f43f5e',
            borderWidth: 2.2,
            pointRadius: 3,
            tension: 0.25,
            yAxisID: 'y1',
            order: 1
          }}
        ]
      }},
      options: {{
        responsive: true,
        maintainAspectRatio: false,
        plugins: {{ legend: {{ labels: {{ color: '#eef3f7' }} }} }},
        scales: {{
          x: {{ ticks: {{ color: '#95a7b8', maxRotation: 45 }}, grid: {{ color: 'rgba(255,255,255,0.04)' }} }},
          y: {{ position: 'left', title: {{ display: true, text: '건물전력 (GWh)', color: '#95a7b8' }}, ticks: {{ color: '#95a7b8' }}, grid: {{ color: 'rgba(255,255,255,0.06)' }} }},
          y1: {{ position: 'right', title: {{ display: true, text: '냉방도일 (CDD)', color: '#f43f5e' }}, ticks: {{ color: '#f43f5e' }}, grid: {{ drawOnChartArea: false }} }}
        }}
      }}
    }});

    distSelect.addEventListener('change', (e) => selectDistrict(e.target.value));

    // Scenario Chart
    const ctx2 = document.getElementById('scenarioChart').getContext('2d');
    const scenarioChart = new Chart(ctx2, {{
      type: 'bar',
      data: {{
        labels: orderedDistricts,
        datasets: [{{
          label: '+2℃ 시나리오 여름 추가 배출량 (tCO₂eq)',
          data: orderedDistricts.map(d => Number(sensMap[d].pred_plus2c_co2_ton)),
          backgroundColor: 'rgba(244, 63, 94, 0.75)',
          borderRadius: 4
        }}]
      }},
      options: {{
        indexAxis: 'y',
        responsive: true,
        maintainAspectRatio: false,
        plugins: {{ legend: {{ labels: {{ color: '#eef3f7' }} }} }},
        scales: {{
          x: {{ ticks: {{ color: '#95a7b8' }}, grid: {{ color: 'rgba(255,255,255,0.06)' }} }},
          y: {{ ticks: {{ color: '#eef3f7' }}, grid: {{ display: false }} }}
        }}
      }}
    }});

    window.setScenario = function(deg) {{
      document.getElementById('btnPlus1').classList.toggle('active', deg === 1);
      document.getElementById('btnPlus2').classList.toggle('active', deg === 2);
      if (deg === 1) {{
        scenarioChart.data.datasets[0].label = '+1℃ 시나리오 여름 추가 배출량 (tCO₂eq)';
        scenarioChart.data.datasets[0].data = orderedDistricts.map(d => Math.round(Number(sensMap[d].pred_plus1c_summer_mwh) * 0.4594));
        scenarioChart.data.datasets[0].backgroundColor = 'rgba(245, 158, 11, 0.78)';
      }} else {{
        scenarioChart.data.datasets[0].label = '+2℃ 시나리오 여름 추가 배출량 (tCO₂eq)';
        scenarioChart.data.datasets[0].data = orderedDistricts.map(d => Number(sensMap[d].pred_plus2c_co2_ton));
        scenarioChart.data.datasets[0].backgroundColor = 'rgba(244, 63, 94, 0.75)';
      }}
      scenarioChart.update();
    }};

    // Senior Vulnerability Chart
    const seniorSelect = document.getElementById('seniorDistSelect');
    const ctx3 = document.getElementById('seniorChart').getContext('2d');
    const initDist = '달서구';
    const seniorChart = new Chart(ctx3, {{
      type: 'bar',
      data: {{
        labels: DATA.senior_top[initDist].map(x => x.dong),
        datasets: [{{
          label: '고령·독거노인 인구 (명)',
          data: DATA.senior_top[initDist].map(x => x.count),
          backgroundColor: 'rgba(16, 185, 129, 0.72)',
          borderRadius: 4
        }}]
      }},
      options: {{
        indexAxis: 'y',
        responsive: true,
        maintainAspectRatio: false,
        plugins: {{ legend: {{ labels: {{ color: '#eef3f7' }} }} }},
        scales: {{
          x: {{ ticks: {{ color: '#95a7b8' }}, grid: {{ color: 'rgba(255,255,255,0.06)' }} }},
          y: {{ ticks: {{ color: '#eef3f7' }}, grid: {{ display: false }} }}
        }}
      }}
    }});

    function updateSeniorChart(dist) {{
      if (!DATA.senior_top[dist]) return;
      seniorSelect.value = dist;
      const items = DATA.senior_top[dist];
      seniorChart.data.labels = items.map(x => x.share ? `${{x.dong}} (고령화 ${{x.share}}%)` : x.dong);
      seniorChart.data.datasets[0].data = items.map(x => x.count);
      seniorChart.update();
    }}

    seniorSelect.addEventListener('change', (e) => updateSeniorChart(e.target.value));

    // Unified District Selection Handler (Map + Cards + Charts)
    window.selectDistrict = function(d) {{
      selectedDist = d;
      updateMapDisplay();

      const p = prioMap[d];
      const th = threshMap[d] || {{}};
      if (p) {{
        document.getElementById('selTitle').textContent = `${{d}} (우선순위 ${{p.rank}}위 · ${{Number(p.priority_score).toFixed(1)}}점)`;
        const clEl = document.getElementById('selCluster');
        clEl.textContent = p.cluster_type;
        clEl.className = 'tag ' + (p.cluster_type.includes('유형 I:') ? 'tag-1' : p.cluster_type.includes('유형 II:') ? 'tag-2' : p.cluster_type.includes('유형 III:') ? 'tag-3' : 'tag-4');
        document.getElementById('selPolicy').textContent = `맞춤형 처방: ${{p.policy_recommendation}} (공공건축물 ${{p.public_building_count}}개소 · 연면적 ${{Math.round(Number(p.public_building_area_m2)/1000).toLocaleString()}}천㎡)`;
        document.getElementById('selThresh').textContent = `${{th.optimal_threshold_temp_c || '-'}}℃ (R²=${{th.piecewise_r2 || p.r_squared}})`;
        document.getElementById('selRatio').textContent = `난방 대비 ${{th.heat_vs_cold_sensitivity_ratio || '-'}}배`;
        document.getElementById('selDominant').textContent = `${{th.dominant_cooling_sector || '-'}} (주택 ${{th.residential_cooling_share_pct}}%)`;
      }}

      distSelect.value = d;
      timelineChart.data.datasets[0].data = labels.map(ym => DATA.district_series_gwh[d][ym]);
      timelineChart.data.datasets[0].label = `${{d}} 건물전력 (GWh)`;
      timelineChart.update();

      ghgSelect.value = d;
      updateGhgChart(d);

      if (DATA.senior_top[d]) {{
        updateSeniorChart(d);
      }}
    }};

    // Initialize default selection
    selectDistrict('달서구');
  </script>
</body>
</html>
"""


if __name__ == "__main__":
    WEB_DIR.mkdir(parents=True, exist_ok=True)
    payload = load_dashboard_payload()
    html = generate_html(payload)
    out_file = WEB_DIR / "index.html"
    with open(out_file, "w", encoding="utf-8") as f:
        f.write(html)
    print(f"[OK] Upgraded interactive map dashboard: {out_file} ({out_file.stat().st_size:,} bytes)")
