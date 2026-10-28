# -*- coding: utf-8 -*-
"""
data/processed/ 의 정제 및 모델링 결과 CSV를 기반으로
단일 파일 인터랙티브 웹 대시보드 (web/index.html) 를 생성하는 스크립트.
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
    hotspots = read_csv_dict(PROCESSED_DIR / "model_dong_cooling_hotspots_top20.csv")
    seniors = read_csv_dict(PROCESSED_DIR / "dong_senior_vulnerability.csv")
    weather = read_csv_dict(PROCESSED_DIR / "weather_monthly_2020_2026.csv")
    elec_m = read_csv_dict(PROCESSED_DIR / "electricity_district_monthly.csv")

    # Build monthly building electricity time series (2025-01 ~ 2026-08) by district
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

    # Top 5 senior dongs per available district
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
      --bg: #0f1419;
      --surface: #171f26;
      --surface-2: #1f2a33;
      --border: #2c3b47;
      --text: #eef3f7;
      --muted: #97a8b8;
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
      padding: 28px 20px 60px;
    }}
    .container {{ max-width: 1240px; margin: 0 auto; }}
    header {{
      border-bottom: 1px solid var(--border);
      padding-bottom: 20px;
      margin-bottom: 24px;
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
    h1 {{ font-size: 26px; font-weight: 700; letter-spacing: -0.02em; }}
    .subtitle {{ color: var(--muted); font-size: 14px; margin-top: 6px; }}
    .kpi-grid {{
      display: grid;
      grid-template-columns: repeat(4, 1fr);
      gap: 14px;
      margin-bottom: 22px;
    }}
    .kpi-card {{
      background: var(--surface);
      border: 1px solid var(--border);
      border-radius: 10px;
      padding: 16px 18px;
    }}
    .kpi-label {{ font-size: 12px; color: var(--muted); }}
    .kpi-val {{ font-size: 24px; font-weight: 700; margin-top: 6px; }}
    .kpi-sub {{ font-size: 12px; color: var(--muted); margin-top: 4px; }}
    .callout {{
      background: var(--surface-2);
      border-left: 4px solid var(--accent);
      border-radius: 8px;
      padding: 15px 18px;
      margin-bottom: 24px;
      font-size: 14px;
    }}
    .callout strong {{ color: var(--accent); }}
    .grid-2 {{
      display: grid;
      grid-template-columns: 1.15fr 0.85fr;
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
      margin-bottom: 12px;
      gap: 12px;
      flex-wrap: wrap;
    }}
    .panel-title {{ font-size: 16px; font-weight: 700; }}
    .panel-caption {{ font-size: 12px; color: var(--muted); margin-bottom: 12px; }}
    select, button {{
      background: var(--surface-2);
      color: var(--text);
      border: 1px solid var(--border);
      border-radius: 6px;
      padding: 6px 12px;
      font-size: 13px;
      cursor: pointer;
    }}
    button.active {{
      background: var(--accent);
      color: #0b131a;
      border-color: var(--accent);
      font-weight: 700;
    }}
    .chart-box {{ position: relative; height: 290px; width: 100%; }}
    table {{
      width: 100%;
      border-collapse: collapse;
      font-size: 13px;
    }}
    th, td {{
      padding: 9px 10px;
      border-bottom: 1px solid var(--border);
      text-align: left;
    }}
    th {{ color: var(--muted); font-weight: 600; font-size: 12px; background: rgba(255,255,255,0.02); }}
    td.num, th.num {{ text-align: right; font-variant-numeric: tabular-nums; }}
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
    @media (max-width: 960px) {{
      .kpi-grid, .grid-2, .grid-equal {{ grid-template-columns: 1fr; }}
    }}
  </style>
</head>
<body>
  <div class="container">
    <header>
      <div>
        <span class="badge">2026 대구광역시 기후·환경·탄소중립 공공데이터 AI 활용대회 · 부문 2</span>
        <h1>폭염이 밀어 올리는 대구 건물 탄소배출: 구·동 단위 핀셋 투자 지도</h1>
        <p class="subtitle">기상청 일별기온(2020–2026) × 한전 구·법정동 전력사용량 × 온실가스 인벤토리 × 고령·독거노인 취약계층 결합 분석</p>
      </div>
      <div style="text-align:right; font-size:12px; color:var(--muted);">
        <div>분석 공간: 대구광역시 9개 구·군 및 법정동·행정동</div>
        <div>모델: 검침시차 보정 유효 냉방도일(CDD) 다중회귀 및 다차원 우선순위 모델</div>
      </div>
    </header>

    <section class="kpi-grid">
      <div class="kpi-card">
        <div class="kpi-label">구·군별 기온→건물전력 회귀 설명력 (R²)</div>
        <div class="kpi-val" style="color:var(--success);">0.905 ~ 0.929</div>
        <div class="kpi-sub">검침시차(전월 50%+당월 50%) 유효 CDD·HDD 보정 후</div>
      </div>
      <div class="kpi-card">
        <div class="kpi-label">여름 평균기온 +2℃ 상승 시 대구 건물 추가배출</div>
        <div class="kpi-val" style="color:var(--danger);">+283,270 tCO₂eq</div>
        <div class="kpi-sub">여름 추가 전력 +616.6 GWh (달서·북·수성·동구 68% 차지)</div>
      </div>
      <div class="kpi-card">
        <div class="kpi-label">폭염기(7~8월) 건물전력 급증률 1위</div>
        <div class="kpi-val" style="color:var(--warn);">중구 +52.9%</div>
        <div class="kpi-sub">봄(4~5월) 대비 증가율 · 남구(+49.9%, '26년) 2위</div>
      </div>
      <div class="kpi-card">
        <div class="kpi-label">냉방탄소 감축 × 독거노인 최우선 핀셋 타깃</div>
        <div class="kpi-val" style="color:var(--accent);">북구 산격동 · 달서 진천동</div>
        <div class="kpi-sub">산격동 여름초과 1위(272.7MWh) & 독거노인 1,379명</div>
      </div>
    </section>

    <div class="callout">
      <strong>핵심 발견:</strong> 대구 온실가스 배출의 58%를 차지하는 건물 부문은 여름철 폭염(냉방도일)에 극도로 민감합니다.
      한전 월별 전력판매량의 <strong>검침 시차(0.5개월)를 보정한 다중선형회귀 모델</strong>을 적용한 결과,
      구별 건물전력 변동의 <strong>90.5%~92.9%를 기온(CDD·HDD)만으로 설명·예측</strong>할 수 있었습니다.
      총량 감축은 <strong>달서구·수성구·북구·동구(유형 I)</strong>의 대형·공공건축물 그린리모델링에, 기후적응형 에너지 복지는 <strong>중구·남구·서구(유형 II) 및 산격동·진천동·상중이동</strong> 쿨루프에 집중해야 합니다.
    </div>

    <section class="grid-2">
      <div class="panel">
        <div class="panel-header">
          <div class="panel-title">1. 구·군별 월별 건물전력 추이 및 폭염(냉방도일) 동조화 (2025.01–2026.08)</div>
          <select id="districtSelect"></select>
        </div>
        <p class="panel-caption">막대: 선택 구·군의 월별 건물전력 사용량(주택+일반+교육용, GWh) / 선: 대구 월간 냉방도일(CDD, 기준 24℃)</p>
        <div class="chart-box">
          <canvas id="timelineChart"></canvas>
        </div>
      </div>

      <div class="panel">
        <div class="panel-header">
          <div class="panel-title">2. 폭염 심화 시나리오별 구·군 추가 탄소배출량 예측</div>
          <div>
            <button id="btnPlus1" onclick="setScenario(1)">+1℃ 시나리오</button>
            <button id="btnPlus2" class="active" onclick="setScenario(2)">+2℃ 시나리오</button>
          </div>
        </div>
        <p class="panel-caption">유효 냉방도일 회귀기울기(MWh/CDD) 기반 여름철 추가 간접배출량 (단위: tCO₂eq)</p>
        <div class="chart-box">
          <canvas id="scenarioChart"></canvas>
        </div>
      </div>
    </section>

    <section class="panel" style="margin-bottom:22px;">
      <div class="panel-header">
        <div class="panel-title">3. 대구 9개 구·군 탄소중립 투자 우선순위 스코어카드 및 4대 맞춤형 처방</div>
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
              <th class="num">CDD 민감도 (MWh/CDD)</th>
              <th class="num">회귀 설명력 (R²)</th>
              <th class="num">여름 급증률 ('25)</th>
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
          <div class="panel-title">4. 법정동별 여름철(7~8월) 냉방전력 급증 Top 12 핫스팟</div>
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
          <div class="panel-title">5. 행정동별 고령·독거노인 밀집 Top 5 (쿨루프·무더위쉼터 타깃)</div>
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
      <div><strong>활용 공공데이터 출처 (공공누리 제1유형 및 제한없음):</strong> ① 기후에너지환경부 온실가스종합정보센터(GIR) 2025 지역 온실가스 통계(2010–2023) · ② 기상청 기상자료개방포털 대구(143) 일별 기온자료(2020.01–2026.09) · ③ 한국전력공사 시군구별(2025.01–2026.08) 및 법정동별(2025) 전력판매량 · ④ 대구광역시 공공건축물 현황(2026.09) 및 달서구·북구·서구·중구 노인·독거노인 인구통계</div>
    </footer>
  </div>

  <script>
    const DATA = {data_json};

    // Populate Priority Table
    const tbody = document.querySelector('#priorityTable tbody');
    DATA.priority.forEach(r => {{
      let tagClass = 'tag-4';
      if (r.cluster_type.includes('유형 I:')) tagClass = 'tag-1';
      else if (r.cluster_type.includes('유형 II:')) tagClass = 'tag-2';
      else if (r.cluster_type.includes('유형 III:')) tagClass = 'tag-3';

      const tr = document.createElement('tr');
      tr.innerHTML = `
        <td><strong>${{r.rank}}</strong></td>
        <td><strong>${{r.district}}</strong></td>
        <td><span class="tag ${{tagClass}}">${{r.cluster_type}}</span></td>
        <td class="num"><strong>${{Number(r.priority_score).toFixed(1)}}점</strong></td>
        <td class="num">${{Number(r.cdd_slope_mwh_per_cdd).toFixed(1)}}</td>
        <td class="num" style="color:#10b981;font-weight:600;">${{Number(r.r_squared).toFixed(3)}}</td>
        <td class="num">+${{Number(r.summer_2025_surge_pct).toFixed(1)}}%</td>
        <td class="num">${{Number(r.cooling_excess_2025_gwh).toFixed(1)}} GWh</td>
        <td class="num">${{Number(r.elec_building_share_pct).toFixed(1)}}%</td>
        <td class="num">${{r.public_building_count}}개소 (${{Math.round(Number(r.public_building_area_m2)/1000).toLocaleString()}}천㎡)</td>
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

    // Chart 1: District monthly building electricity vs CDD
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
            label: '월별 건물전력 (GWh)',
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
          x: {{ ticks: {{ color: '#97a8b8', maxRotation: 45 }}, grid: {{ color: 'rgba(255,255,255,0.04)' }} }},
          y: {{ position: 'left', title: {{ display: true, text: '건물전력 (GWh)', color: '#97a8b8' }}, ticks: {{ color: '#97a8b8' }}, grid: {{ color: 'rgba(255,255,255,0.06)' }} }},
          y1: {{ position: 'right', title: {{ display: true, text: '냉방도일 (CDD)', color: '#f43f5e' }}, ticks: {{ color: '#f43f5e' }}, grid: {{ drawOnChartArea: false }} }}
        }}
      }}
    }});

    distSelect.addEventListener('change', (e) => {{
      const d = e.target.value;
      timelineChart.data.datasets[0].data = labels.map(ym => DATA.district_series_gwh[d][ym]);
      timelineChart.data.datasets[0].label = `${{d}} 건물전력 (GWh)`;
      timelineChart.update();
    }});

    // Chart 2: Scenario (+1C vs +2C) additional CO2 emissions
    const sensMap = {{}};
    DATA.sensitivity.forEach(s => {{ sensMap[s.district] = s; }});
    const orderedDistricts = DATA.priority.map(p => p.district);

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
          x: {{ ticks: {{ color: '#97a8b8' }}, grid: {{ color: 'rgba(255,255,255,0.06)' }} }},
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

    // Chart 3: Senior vulnerability by administrative dong
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
          x: {{ ticks: {{ color: '#97a8b8' }}, grid: {{ color: 'rgba(255,255,255,0.06)' }} }},
          y: {{ ticks: {{ color: '#eef3f7' }}, grid: {{ display: false }} }}
        }}
      }}
    }});

    seniorSelect.addEventListener('change', (e) => {{
      const dist = e.target.value;
      const items = DATA.senior_top[dist] || [];
      seniorChart.data.labels = items.map(x => x.share ? `${{x.dong}} (고령화 ${{x.share}}%)` : x.dong);
      seniorChart.data.datasets[0].data = items.map(x => x.count);
      seniorChart.update();
    }});
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
    print(f"[OK] Generated interactive dashboard: {out_file} ({out_file.stat().st_size:,} bytes)")
