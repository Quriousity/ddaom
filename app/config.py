"""설정. 경로 기준점(BASE)은 PyInstaller 동결 대응으로 여기서만 계산한다 (명세 §2.2)."""
import os
import sys

BASE = getattr(sys, "_MEIPASS", os.path.dirname(os.path.abspath(__file__)))
MODEL_DIR = os.path.join(BASE, "models")

RENDER_DPI_BASE = 96
EXPORT_DPI = 300
OCR_DPI = 300

# --- OCR 모델 경로 (세 개 모두 명시. 생략 시 런타임 다운로드 위험, 명세 §2.1) ---
# 언어 전환 = rec 모델 + 사전 교체. 별도 lang 문자열 설정은 두지 않는다.
OCR_DET_MODEL = os.path.join(MODEL_DIR, "det.onnx")
OCR_REC_MODEL = os.path.join(MODEL_DIR, "korean_rec.onnx")
OCR_REC_KEYS = os.path.join(MODEL_DIR, "korean_dict.txt")

# --- OCR 실행 ---
OCR_THREADS = 4
OCR_PRELOAD_ON_START = True
SINGLE_LINE_RATIO = 0.25  # crop_h / crop_w 가 이 값 미만이면 det 생략 (명세 §4.2.2)
SINGLE_LINE_MAX_H_PX = 160  # 이 높이(OCR_DPI px) 초과면 넓어도 단일라인이 아니다 (두 줄 오판 방지)
SINGLE_LINE_MIN_SCORE = 0.75  # 고속 경로 평균 점수가 이 미만이면 det 경로로 재시도
OCR_PAD_PX = 10
OCR_MIN_SHORT_SIDE = 32  # 미만이면 2배 업스케일

# --- 후처리 ---
MIN_CHARS_FOR_TEXT_LAYER = 2
JOIN_HYPHENATED_LINES = True
LINE_GROUP_FACTOR = 0.6  # 라인 그룹핑 임계 = 평균 글자높이 * 이 값

# --- 리댁션 ---
REDACT_FILL_COLOR = (1, 1, 1)

# --- 담은 목록 오버레이 (담긴 영역 표시 — 저장 전까지 아무것도 파괴하지 않는다) ---
DELETE_REGION_PEN = (239, 68, 68, 200)   # red-500
DELETE_REGION_FILL = (239, 68, 68, 70)

# --- 렌더 캐시 ---
PAGE_CACHE_SIZE = 8
THUMB_WIDTH = 140

# --- 페이지 텍스트 박스 자동 스캔 (호버→클릭 복사) ---
SCAN_ON_PAGE_SHOW = True
SCAN_DPI = 200  # 전체 페이지 OCR 렌더 dpi (rapidocr 가 내부에서 max_side 2000 으로 제한)
CLICK_DRAG_THRESHOLD_PX = 4  # 이하 이동이면 드래그가 아니라 클릭
