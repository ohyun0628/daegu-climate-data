# Daegu Climate & Carbon Neutrality Data Analysis

**2026 대구광역시 기후·환경·탄소중립 공공데이터 AI 활용대회 (부문 2: 공공데이터 분석·시각화)** 프로젝트 저장소입니다.

- **인터랙티브 대시보드:** `index.html` (또는 `web/index.html`) 실행 / GitHub Pages 배포 지원

---

## 1. 핵심 질문 및 분석 요약
- **배경:** 2010~2023년 대구 온실가스 인벤토리 분석 결과, 건물 부문 배출 내 **간접전력 배출 비중이 63.8%(2010년)에서 69.0%(2023년, 중구 74.7%·달서구 73.3%)로 상승**하여 여름철 폭염 냉방전력 관리가 탄소중립의 핵심 과제로 부상함.
- **방법론:**
  1. **검침시차 보정 다중회귀 모델:** 한전 월별 전력판매량의 검침 시차(0.5개월)를 반영한 유효 냉방도일(Effective CDD)·난방도일(HDD) 모델로 9개 구·군 설명력 **$R^2 = 0.905 \sim 0.929$** 달성.
  2. **비선형 폭염 임계점($T^*$) 탐색:** 유효 평균기온 **$19.0 \sim 19.75^\circ\text{C}$ 돌파 시 냉방전력 기울기가 난방 대비 $2.79 \sim 5.89$배 급증**함을 규명 (최대 $R^2 = 0.955$).
  3. **구·동·건축물 3단계 핀셋 타깃팅:** 9개 구·군 4대 유형 분류 → 법정동 냉방전력 핫스팟 및 9개 구·군 고령화율(2026.09)·75개 행정동 고령·독거노인 결합 → 그린리모델링 우선 도입 공공건축물 Top 20 도출.
  4. **감축 시뮬레이터:** 유형 I/II·전체·선택 구에 냉방전력 5~30% 절감을 적용해 2025 여름 초과전력 및 +2℃ 추가배출 회피량을 실시간 산출.

---

## 2. 디렉터리 및 데이터셋 구조
```text
daegu-climate-data/
├── index.html                                         # 인터랙티브 웹 대시보드 (루트 진입점)
├── web/index.html                                     # 인터랙티브 웹 대시보드 원본
├── data/processed/
│   ├── weather_monthly_2020_2026.csv                  # 기상청 대구(143) 월별 기온·폭염일수·냉방도일
│   ├── electricity_district_monthly.csv               # 대구 9개 구·군 × 계약종별 월별 전력사용량
│   ├── electricity_dong_2025.csv                      # 대구 법정동별 연간 전력 및 여름 급증률
│   ├── ghg_district_2010_2023.csv                     # 대구·군위군 2010~2023 직·간접 온실가스 전체
│   ├── ghg_daegu_14yr_structure.csv                   # 구·군별 건물 직접연료 vs 간접전력 장기 구조
│   ├── dong_senior_vulnerability.csv                  # 75개 행정동 고령·독거노인 취약계층 현황
│   ├── district_senior_aging.csv                      # 9개 구·군 고령화율 (행정안전부 2026.09)
│   ├── model_district_climate_sensitivity.csv         # 검침시차 보정 구·군별 기후민감도 회귀 결과
│   ├── model_threshold_and_sector.csv                 # 비선형 폭염 임계온도(T*) 및 주택/상업 분해
│   ├── model_district_priority.csv                    # 대구 9개 구·군 4대 유형 및 투자 우선순위
│   ├── model_dong_cooling_hotspots_top20.csv          # 법정동별 여름 냉방전력 급증 Top 20
│   └── model_public_building_targets_top20.csv        # 그린리모델링 최우선 공공건축물 Top 20
├── src/
│   ├── preprocess/pipeline.py                         # 12종 원본 공공데이터 통합 전처리 파이프라인
│   └── model/
│       ├── analyze.py                                 # 검침시차 보정 회귀 및 구·동 우선순위 모델링
│       ├── advanced_ai_analysis.py                    # 직·간접 배출 분리, 임계온도 탐색, 공공건축물 매칭
│       └── build_dashboard.py                         # 인터랙티브 SVG 지도·차트 대시보드 빌더
└── docs/
    ├── data_sources.md                                # [붙임 5] 공공데이터 사용 내역서 (12종)
    └── submission_checklist.md                        # 제출 서류 체크리스트 및 분석보고서 본문
```

## 3. 재현 실행 방법
```powershell
python -X utf8 src/preprocess/pipeline.py
python -X utf8 src/model/analyze.py
python -X utf8 src/model/advanced_ai_analysis.py
python -X utf8 src/model/build_dashboard.py
```
