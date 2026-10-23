"""
대구 기후·탄소중립 공공데이터 전처리 파이프라인 뼈대

흐름:
1. data/raw/ 의 원본 CSV/XLSX 로드
2. 행정구역 키 통일 (중구, 동구, 서구, 남구, 북구, 수성구, 달서구, 달성군, 군위군)
3. 시계열 키 통일 (YYYY-MM 또는 YYYY)
4. 파생변수 계산 (예: 냉방도일 CDD = max(0, 일평균기온 - 24))
5. data/processed/ 에 병합 테이블 저장
"""

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
    "군위군",  # 2023년 7월 편입 — 과거 시계열 병합 시 포함 여부 명시 필요
]


def ensure_dirs() -> None:
    RAW_DIR.mkdir(parents=True, exist_ok=True)
    PROCESSED_DIR.mkdir(parents=True, exist_ok=True)


if __name__ == "__main__":
    ensure_dirs()
    print(f"[OK] raw dir: {RAW_DIR}")
    print(f"[OK] processed dir: {PROCESSED_DIR}")
