# PDF 영역 선택 OCR/추출/리댁션 도구 — 개발 명세

> **상태: 구현 완료 (2026-08-04).** Phase 1~6 전부 + 골든 테스트 30개 통과 + CI 빌드 준비.
> 남은 것 = **`./setup-exe-build.sh` 실행** (GitHub 로그인 → push → exe 자동 빌드·다운로드).
> 개인용·배포 없음 확정 → §2 AGPL 미결과 §11 배포 미결은 소멸. 코드 구조는 §3 그대로.
>
> **2026-08-04 스택 확정** — OCR 은 **RapidOCR 단일 엔진 + PP-OCRv5 한국어 모델 번들**로
> 굳혔다. PaddleOCR 분기는 삭제. 근거와 다른 대안의 기각 사유는 §13 결정 기록.

---

## 1. 목표

PDF를 열어 마우스로 영역(사각형/폴리곤)을 지정하면 **그 영역의 텍스트를 클립보드에 복사**한다.
읽기 대상은 **한국어·영어·숫자 혼용** 문서 (세무 서류: 성명·주민번호·금액·계좌 등).

부가 기능:
- **(A)** 선택 영역을 이미지로 추출 (클립보드 복사 + 파일 저장)
- **(B)** 선택 영역을 파괴적으로 리댁션하고 메타데이터를 제거한 새 PDF 생성

### 범위 확정 — 08-03 축소는 취소

어제 이 문서는 *"변환·파괴는 이 도구가 안 한다 → 직원앱"* 으로 범위를 줄였다. **그 축소는 취소한다.**
파괴·영역추출은 **이 도구가 가져간다.** 따라서 `ustax-staff/docs/llm-extract-plan.md` §6-2
(직원앱 안의 드래그 파괴)는 이 문서로 **대체**된다 — 착수할 때 그 절을 지우거나 이리로 넘긴다.
같은 기능을 두 곳에 두지 않는다.

⚠ 셸 원칙(*로그인 뒤 모든 업무가 하나의 셸 안에서*)과의 마찰은 실재한다 — 도구가 안 깔린 PC 엔
기능이 아예 없다. 그래서 **Phase 7(패키징)이 기능만큼 중요하다.**

---

## 2. 기술 스택 (확정)

| | | 왜 이것인가 |
|---|---|---|
| 언어 | **Python 3.11** | 3.12+ 는 onnxruntime 등 휠 호환성 확인 필요 |
| GUI | **PySide6** (QGraphicsView/Scene) | 클립보드 이미지·드래그 UX 가 네이티브에서 자연스럽다 |
| PDF | **PyMuPDF (fitz)** | 렌더·텍스트·이미지·**리댁션**·메타데이터를 한 라이브러리로. 순수 wheel, 외부 바이너리 0 |
| OCR | **rapidocr-onnxruntime + PP-OCRv5 한국어 모델 번들** — 단일 엔진 | §2.1. 한국어 rec 모델 하나가 **한글+라틴+숫자**를 전부 커버 |
| 이미지 | Pillow, numpy | 마스킹·전처리 |
| 클립보드 | `QtGui.QClipboard` | 텍스트/이미지 모두 |
| 패키징 | **PyInstaller (onedir)** | onefile 은 기동 지연 + 백신 오탐. Nuitka 는 예비 |

**엔진은 하나다.** PaddleOCR 분기는 두지 않는다 — 한국어에서 Paddle 이 쓰는 인식 모델이
RapidOCR 이 돌리는 것과 **동일**(`korean_PP-OCRv5_mobile_rec`)해서 정확도 이득 없이
`paddlepaddle` 수백 MB 와 동결 빌드 문제만 얹는다 (§13-B).

### 의존성

```
PySide6
PyMuPDF
rapidocr-onnxruntime
Pillow
numpy
```

빌드타임에만 필요 (런타임 의존성 아님):

```
huggingface_hub     # 모델 파일 1회 취득용. 취득 후 저장소에 커밋하고 제거 가능
```

### 2.1 OCR 모델 번들

**추론은 전부 로컬에서 돈다.** onnxruntime 이 CPU 에서 실행하며 실행 중 네트워크를 쓰지 않는다.
네트워크가 필요한 유일한 시점은 **모델 파일 최초 취득 1회**이고, 이는 개발자 머신에서 끝낸다.

⚠ **한국어 rec 모델은 `rapidocr-onnxruntime` 패키지에 들어있지 않다** (동봉 모델은 중국어/영어).
아래 3종을 직접 받아 번들하는 것이 오프라인 한국어 OCR 의 **성립 조건**이다:

```
models/
  det.onnx           # PP-OCRv5 detection (언어 무관 공용)
  korean_rec.onnx    # korean_PP-OCRv5_mobile_rec — 한글+라틴+숫자
  korean_dict.txt    # 한국어 문자 사전
```

총 20~60MB 수준. 인스톨러에 그대로 포함한다.

**세 경로를 모두 명시적으로 넘긴다.**

```python
from rapidocr_onnxruntime import RapidOCR

ocr = RapidOCR(
    det_model_path=config.OCR_DET_MODEL,
    rec_model_path=config.OCR_REC_MODEL,
    rec_keys_path=config.OCR_REC_KEYS,
    intra_op_num_threads=config.OCR_THREADS,
)
```

> ⚠ **경로를 생략하면 일부 버전이 런타임에 조용히 다운로드를 시도한다.** 인터넷 없는 PC 에서
> 첫 실행이 멈춘다. 세 경로 명시를 **기본값이자 불변 규칙**으로 둔다. §9의 오프라인 항목과 직결.

### 2.2 모델 경로 해석 (PyInstaller 동결 대응)

동결 빌드에서 상대 경로는 깨진다. 경로 기준점을 한 곳에서만 계산한다.

```python
# config.py
import sys, os
BASE = getattr(sys, "_MEIPASS", os.path.dirname(os.path.abspath(__file__)))
MODEL_DIR = os.path.join(BASE, "models")
```

빌드 시 `--add-data "models;models"`, 그리고 `--collect-all onnxruntime`.

### 2.3 GPU

`onnxruntime-directml` 을 쓰면 NVIDIA 가 아니어도(내장 그래픽 포함) 가속된다.
**다만 선택 영역 단위 작업이라 이득이 작다 — CPU 고정을 기본으로 한다.**

### ⚠ 라이선스 주의

PyMuPDF 는 **AGPL-3.0**. 소스 비공개 배포 계획이 있으면 상용 라이선스 구매 또는
`pypdfium2`(렌더링/텍스트) + `pikepdf`(구조/메타데이터) 조합으로 교체.
단, **후자는 진짜 리댁션 기능이 없어 직접 구현이 필요하다.** 이건 (B)의 근간이므로
교체 결정은 착수 전에 내려야 한다 → §11.

**OCR 쪽은 제약이 없다.** PP-OCR 모델과 RapidOCR 모두 Apache 2.0 이다.
즉 **라이선스 병목은 OCR 이 아니라 PDF 스택 하나뿐이다.**

---

## 3. 아키텍처

```
app/
  main.py            # 진입점, QApplication 부팅
  models/            # ← 번들 OCR 모델 (det.onnx / korean_rec.onnx / korean_dict.txt)
  ui/
    main_window.py   # 메뉴, 툴바, 단축키, 페이지 네비게이션
    pdf_view.py      # QGraphicsView 서브클래스. 렌더/줌/팬/선택 이벤트
    selection.py     # RectSelection / PolygonSelection 아이템, 핸들 리사이즈
  core/
    document.py      # fitz.Document 래퍼. 열기/페이지수/렌더 캐시
    coords.py        # 좌표 변환 (화면 <-> 씬 <-> PDF point <-> crop 픽셀)
    extractor.py     # 영역 텍스트 추출 (텍스트 레이어 우선, OCR 폴백)
    ocr_engine.py    # OCR 백엔드 추상화 (§4.6 계약) — 구현체는 RapidOCR 하나
    redactor.py      # 리댁션 + 메타데이터 제거 + 저장
    clipboard.py     # 텍스트/이미지 클립보드 유틸
  config.py          # 설정 (DPI, 모델 경로, 후처리 옵션)
```

---

## 4. 핵심 구현 규칙

### 4.1 좌표계 (가장 중요)

네 개의 좌표계를 명확히 분리하고 **변환은 `coords.py` 한 곳에서만** 수행한다.

1. **PDF point 좌표** (72dpi 기준, PyMuPDF 는 좌상단 원점)
2. **렌더 픽셀 좌표** (zoom 배율 적용)
3. **Qt 씬/뷰 좌표**
4. **crop 픽셀 좌표** — OCR 이 돌려주는 폴리곤은 잘라낸 이미지 기준이다.
   `OCR_DPI` 배율과 crop 원점 오프셋을 역으로 적용해야 PDF 좌표가 된다.
   4.2의 라인 그룹핑과 후순위 §12(invisible text 되붙이기)가 모두 이 변환에 의존한다.

변환 규칙:
- 렌더: `mat = fitz.Matrix(zoom, zoom)`, `pix = page.get_pixmap(matrix=mat)`
- 화면 → PDF: `rect_pdf = rect_screen * ~mat` (`~mat`는 역행렬)
- PDF → 화면: `rect_screen = rect_pdf * mat`
- 페이지 rotation 이 0 이 아닌 경우 `page.rotation_matrix` / `page.derotation_matrix` 를
  **반드시 함께 적용할 것.**
- **절대 뷰 위젯 안에서 직접 좌표 산술을 하지 말 것.** 모든 변환은 `coords.py` 경유.

### 4.2 텍스트 추출 전략 (텍스트 우선, OCR 폴백)

```
1) text = page.get_text("text", clip=rect_pdf).strip()
2) if len(text) >= MIN_CHARS (기본 2):  -> 그대로 사용 (OCR 생략)
3) else: 해당 영역을 고해상도 렌더 후 OCR
     pix = page.get_pixmap(clip=rect_pdf, dpi=300)
     -> PIL Image -> 전처리(4.2.1) -> numpy -> ocr_engine.run()
4) 결과 후처리: 줄바꿈 정규화, 하이픈 줄바꿈 병합, 좌->우/상->하 정렬
```

정렬은 OCR 결과의 bbox y중심으로 **라인 그룹핑**(임계값 = 평균 글자높이 × 0.6) 후
각 라인 내에서 **x기준 정렬**.

#### 4.2.1 OCR 전처리 규격

작은 crop 에서는 **모델 교체보다 전처리가 인식률에 더 크게 기여한다.**
"한국어·영어·숫자 짱짱하게"의 실체는 여기다:

- 300dpi 렌더 (`OCR_DPI`) — 주민번호·계좌 같은 작은 숫자는 해상도가 곧 정확도다
- 그레이스케일 변환
- **흰색 패딩 8~10px** — 글자가 이미지 경계에 붙으면 검출·인식이 모두 나빠진다
- 짧은 변이 `OCR_MIN_SHORT_SIDE`(32px) 미만이면 2배 업스케일

#### 4.2.2 단일 라인 고속 경로

이 도구는 **사용자가 이미 영역을 손으로 지정했다.** 텍스트 위치 찾기(detection)가 거의 불필요하다.
한 줄짜리 좁은 영역이면 detection 을 건너뛰고 recognition 에만 넣는다.

```python
if crop_h / crop_w < config.SINGLE_LINE_RATIO:   # 기본 0.25
    lines = ocr.run(img, single_line=True)       # det 생략
else:
    lines = ocr.run(img)
```

`single_line=True` 경로는 폴리곤이 이미지 전체를 덮는 단일 결과를 돌려준다 —
4.2의 라인 그룹핑은 자연히 항등 연산이 된다.

> **효과: 클립보드 복사 체감 응답이 몇 배 빨라진다.** 이 도구의 성패는 정확도만큼 즉시성에 달렸다.
> 금액·번호 한 칸 집어 복사하는 주 사용 패턴이 정확히 이 경로를 탄다.

### 4.3 폴리곤 선택 처리

PyMuPDF 의 `clip` 파라미터는 **사각형만** 받는다. 따라서:

- 폴리곤의 bounding box 로 렌더
- Pillow 의 `ImageDraw.polygon` 으로 마스크 생성, 폴리곤 외부를 흰색으로 채움
- 마스킹된 이미지를 OCR 에 투입
- 텍스트 레이어 경로에서는 `page.get_text("words")` 로 단어 단위 bbox 를 받아
  각 단어 **중심점이 폴리곤 내부인지** point-in-polygon 판정 후 필터링

> ⚠ 중심점 판정은 **경계에 걸친 긴 단어를 통째로 떨어뜨린다.** Phase 6에서 오탈락이 보이면
> 판정 기준을 *단어 bbox ∩ 폴리곤 면적 ≥ 50%* 로 바꾼다. 처음부터 그럴 필요는 없다.

> 폴리곤 마스킹은 4.2.1의 흰색 패딩과 **같은 색으로** 채운다. 두 값이 다르면 마스크 경계가
> 대비선으로 잡혀 검출기가 그것을 글자로 오인한다.

### 4.4 이미지 추출

```
pix = page.get_pixmap(clip=rect_pdf, dpi=EXPORT_DPI)  # 기본 300
```
- 폴리곤이면 4.3의 마스킹 적용 (**배경 투명 옵션** 지원)
- 클립보드 복사: QImage 로 변환 후 `clipboard.setImage()`
- 파일 저장: PNG 기본, JPEG/WEBP 선택 가능

> ⚠ **클립보드로 갈 때는 투명 배경을 흰색으로 합성한다.** Windows 클립보드(CF_DIB)는 알파를
> 제대로 나르지 못해, 붙여넣는 앱에 따라 투명부가 검게 나온다. 투명 유지는 **파일 저장 경로에서만.**

### 4.5 리댁션 + 메타데이터 제거

```python
doc = fitz.open(src_path)
for page_no, rects in selections.items():
    page = doc[page_no]
    for r in rects:
        page.add_redact_annot(r, fill=(1, 1, 1))
    page.apply_redactions(
        images=fitz.PDF_REDACT_IMAGE_PIXELS,
        graphics=fitz.PDF_REDACT_LINE_ART_REMOVE_IF_TOUCHED,
        text=fitz.PDF_REDACT_TEXT_REMOVE,
    )
# 폴리곤은 사각형 스트립으로 분할하거나, 해당 페이지를 래스터화 후 교체

# 메타데이터 및 잔여 정보 제거
doc.set_metadata({})
doc.del_xml_metadata()          # XMP 제거
doc.scrub()                     # 첨부·JS·폼필드·주석 등 잔여 정보 일괄 정리
for page in doc:
    for annot in list(page.annots() or []):
        page.delete_annot(annot)   # 주석/링크 잔존 정보 제거
    page.delete_link_list()

doc.save(dst_path, garbage=4, clean=True, deflate=True,
         incremental=False, encryption=fitz.PDF_ENCRYPT_NONE)
```

**반드시 원본 파일을 덮어쓰지 말고 새 파일로 저장한다.**
저장 후 **검증 루틴**: 저장본을 다시 열어 리댁션 영역에 `get_text` 결과가 비었는지,
메타데이터·XMP 가 비었는지 확인하고 사용자에게 보여준다.

> ⚠ PyMuPDF 는 버전에 따라 상수·메서드 이름이 다르다 (`scrub` 의 인자,
> `page.delete_link_list()` 등). **설치본에서 확인하고 쓴다.**

> ⚠ **스캔 PDF 는 `text=` 옵션만으로는 아무것도 안 지워진다.** 스캔본엔 글자가 없고 이미지
> 한 장뿐이라, 위 코드의 `images=fitz.PDF_REDACT_IMAGE_PIXELS` 가 **실제 파괴를 담당하는
> 유일한 인자**다. 이 값을 낮추면 기능이 조용히 무력화된다.

### 4.6 OCR 엔진 계약

`ocr_engine.py` 는 처음부터 **추상 인터페이스**로 만든다. 지금 구현체는 RapidOCR 하나지만,
계약을 세워두면 §11의 Windows.Media.Ocr 실험이나 미래의 모델 교체가 다른 코드를 건드리지 않는다.

```python
from dataclasses import dataclass
from typing import Protocol
import numpy as np

@dataclass
class OCRLine:
    polygon: list[tuple[float, float]]   # 4점, crop 이미지 픽셀 좌표 (§4.1-4 참조)
    text: str
    score: float

class OCREngine(Protocol):
    def preload(self) -> None: ...
    def run(self, img: np.ndarray, single_line: bool = False) -> list[OCRLine]: ...
```

**반드시 텍스트·폴리곤·점수를 함께 반환한다.** 텍스트만 반환하면 4.2의 라인 그룹핑이 불가능하다
(§10의 기존 자산이 정확히 이 실수를 하고 있다).

#### 콜드스타트 제거

모델 초기화에 1~3초가 걸린다. **클립보드 복사는 즉시성이 생명이므로 이 비용을 사용자가 만나면 안 된다.**

- 앱 기동 직후 백그라운드 스레드에서 `preload()` 호출
- 엔진 인스턴스는 프로세스 수명 동안 **상주**시킨다 (요청마다 생성 금지)
- 프리로드 완료 전 OCR 요청이 오면 상태바에 진행 표시 후 대기

---

## 5. UI 요구사항

- 사이드바 **페이지 썸네일**, 페이지 이동 (PgUp/PgDn)
- **줌**: Ctrl+휠, Ctrl+0(맞춤), Ctrl++/-
- **팬**: 스페이스 드래그 또는 마우스 휠 드래그
- **도구 모드 토글**: 사각형 선택(R) / 폴리곤 선택(P) / 팬(H)
- 선택 후 컨텍스트 메뉴 및 단축키:

| 단축키 | 동작 |
|---|---|
| `Ctrl+C` | 텍스트 복사 |
| `Ctrl+Shift+C` | 이미지 복사 |
| `Ctrl+Shift+S` | 이미지 저장 |
| `Delete` | 선택 영역을 **리댁션 목록에 추가** |

- **리댁션 목록 패널**: 페이지별 대기 중인 영역 리스트, 개별 삭제, 일괄 적용
- **상태바**: 현재 페이지, 줌 배율, 선택 영역 크기(pt), OCR 진행 상태, **OCR 엔진 준비 상태**
- OCR 은 **QThread 또는 QThreadPool 에서 실행. UI 블로킹 금지.**
- 렌더 결과는 `(page_no, zoom)` 키로 **LRU 캐시** (기본 8페이지)

---

## 6. 설정 항목 (`config.py`)

```python
import sys, os
BASE = getattr(sys, "_MEIPASS", os.path.dirname(os.path.abspath(__file__)))
MODEL_DIR = os.path.join(BASE, "models")

RENDER_DPI_BASE = 96
EXPORT_DPI = 300
OCR_DPI = 300

# --- OCR 모델 경로 (세 개 모두 명시. 생략 시 런타임 다운로드 위험 §2.1) ---
# 언어 전환 = rec 모델 + 사전 교체. 별도 lang 문자열 설정은 두지 않는다 (§13-C).
OCR_DET_MODEL = os.path.join(MODEL_DIR, "det.onnx")
OCR_REC_MODEL = os.path.join(MODEL_DIR, "korean_rec.onnx")
OCR_REC_KEYS  = os.path.join(MODEL_DIR, "korean_dict.txt")

# --- OCR 실행 ---
OCR_THREADS = 4
OCR_PRELOAD_ON_START = True
SINGLE_LINE_RATIO = 0.25       # crop_h / crop_w 가 이 값 미만이면 det 생략
OCR_PAD_PX = 10
OCR_MIN_SHORT_SIDE = 32        # 미만이면 2배 업스케일

# --- 후처리 ---
MIN_CHARS_FOR_TEXT_LAYER = 2
JOIN_HYPHENATED_LINES = True

# --- 기타 ---
REDACT_FILL_COLOR = (1, 1, 1)
PAGE_CACHE_SIZE = 8
```

---

## 7. 개발 단계

| | 무엇 |
|---|---|
| **Phase 1** | PDF 열기 + 렌더 + 줌/팬 + 사각형 선택 + **좌표변환 검증** |
| **Phase 2** | 텍스트 레이어 추출 + 클립보드 복사 |
| **Phase 3** | OCR 통합 + 폴백 로직 + 백그라운드 스레드 + **모델 번들·오프라인 실검증** |
| **Phase 4** | 이미지 추출/저장 |
| **Phase 5** | 리댁션 + 메타데이터 제거 + 저장 후 검증 |
| **Phase 6** | 폴리곤 선택 지원 |
| **Phase 7** | PyInstaller 패키징 |

⚠ **Phase 7의 모델 동결 문제(§9)는 Phase 3에서 미리 확인한다.** 마지막에 발견하면 엔진 교체가
되어 Phase 3~6을 다시 건드린다.

---

## 8. 완료 기준

- [ ] 텍스트 PDF 에서 선택 영역 텍스트가 **OCR 없이** 정확히 복사된다
- [ ] 스캔 PDF 에서 **한국어/영어/숫자 혼용** 영역이 OCR 로 인식되어 복사된다
- [ ] **줌 배율을 바꿔도** 선택 영역이 동일한 PDF 좌표를 가리킨다
- [ ] 리댁션 결과 PDF 를 **텍스트 검색해도 가려진 문자열이 나오지 않는다**
- [ ] 결과 PDF 의 Document Properties 가 전부 비어 있고 **XMP 가 존재하지 않는다**
- [ ] **500페이지 PDF** 에서도 페이지 이동이 즉각 반응한다
- [ ] **랜선을 뽑은 PC** 에서 설치 직후 첫 실행에 한국어 OCR 이 동작한다
- [ ] 앱 기동 후 첫 OCR 요청에서 **모델 로딩 지연이 체감되지 않는다**

---

## 9. 알려진 함정

- **PyInstaller 빌드 시 onnxruntime DLL 과 모델 파일이 누락되기 쉽다.**
  `--add-data "models;models"` + `--collect-all onnxruntime` (§2.2). `hiddenimports` 확인.
- `apply_redactions` 는 **페이지 단위로 한 번만** 호출해야 한다. 반복 호출 시 이미 적용된
  콘텐츠에 재작업이 일어나 품질이 떨어진다.
- **암호화된 PDF** 는 `doc.authenticate()` 처리 후 진행. 권한 없는 문서는 명확히 거부.
- **회전된 페이지(`page.rotation != 0`)에서 좌표가 틀어지는 버그가 가장 흔하다.**
  Phase 1에서 **회전 페이지 테스트 케이스를 반드시 포함할 것.**

### ⚠ 오프라인 첫 실행

RapidOCR 패키지 동봉 모델은 **중국어/영어뿐**이라, "설치하면 그냥 된다"는 한국어에선 성립하지
않는다. 오프라인 한국어 OCR 은 **§2.1의 모델 3종 번들 + 경로 명시**로 성립한다.
Phase 3에서 **인터넷 차단 상태로 실제 확인**할 것. 가정하지 말 것.

(과거 판의 "PaddleOCR 첫 실행 다운로드" 경고는 엔진 삭제로 소멸 — §13-B.)

---

## 10. 기존 자산 재사용 (`ustax-ocr-local-fastapi`)

2026-08-04 확인. 가져올 것은 **엔진과 무관한 PyMuPDF 유틸 세 개뿐**이다:

| 가져올 것 | 어디 |
|---|---|
| PDF→PNG 렌더 (dpi 지정) | `ocr.py:174 render_pdf_page` |
| 페이지 수 | `ocr.py:164 pdf_page_count` |
| PDF 판별 | `ocr.py:133 is_pdf` |

**가져오지 않는 것과 이유:**
- `ocr.py:52 _paddle_reader` — Paddle 초기화. 가져오면 `paddlepaddle` 이 도로 필수 의존성이
  되어 §13-B 결정이 코드로 뒤집힌다. **재사용 금지.**
- `ocr.py:65 _paddleocr` — `rec_texts` 만 join 해 **좌표를 버린다.** §4.6 `OCRLine` 계약 위반.
- `available_engines` / `installed_engines` — 단일 엔진이라 불필요.

`web/`(Next 골격만 있는 것)은 **지운다** — 이 도구는 네이티브다.

---

## 11. 미결

1차 목표(§1)를 막는 건 없다. 아래는 **진행하면서** 정한다.

| | |
|---|---|
| **AGPL 결정** | 소스 비공개 배포인가? 그렇다면 PyMuPDF 상용 라이선스 vs 스택 교체 — **Phase 5 전까지** |
| **누가 설치·갱신하나** | 직원 PC 배포 주체. `.exe` 전달 경로 — **Phase 7 전까지** |
| **Windows.Media.Ocr 실험** | 의존성 0·즉답. 깨끗한 인쇄체 한글에서 실용 수준. Phase 3에서 실제 스캔본으로 RapidOCR 과 1:1 **측정 후** 폴백/승격 판단. 측정 전엔 명세에 넣지 않는다 |

---

## 12. 후순위 — searchable PDF

스캔 PDF 에 **글자층을 입혀** 뷰어에서 선택·복사·검색이 되게 하는 것.
없는 건 **OCR 결과를 원본 PDF 에 invisible text 로 되붙이기** (PyMuPDF `insert_textbox`
+ render mode 3) 하나뿐이다.

**지금은 안 한다.** §1의 본 기능이 "복사"를 이미 해결한다. 필요해지는 건 직원이 스캔 PDF
**안에서 검색**해야 할 때다. 그 요구가 확인되면 착수한다.

> 착수할 때 필요한 건 §4.6 `OCRLine.polygon` 과 §4.1-4 의 crop→PDF 역변환이 전부다.
> **그 둘을 지금 제대로 만들어두면 이 절은 나중에 거의 공짜가 된다.**

---

## 13. 결정 기록 (2026-08-04)

한때 §11-A 로 보류했던 다섯 건. **A~D 확정, E 는 측정 대기.**

| | 결정 | 근거 |
|---|---|---|
| **A** | 한국어 모델 3종 **직접 번들** 채택 (§2.1) | RapidOCR 동봉 모델은 중국어/영어뿐. "설치하면 된다"는 한국어에서 거짓이었다 |
| **B** | **PaddleOCR 분기 삭제**, RapidOCR 단일 엔진 | Paddle 최신 파이프라인(v6)은 한국어 미지원 → 한국어는 v5 폴백 = **RapidOCR 과 같은 모델**. "고정밀 모드"는 한국어에서 허상. 남는 우위는 server 급 detection 인데 이 도구는 사용자가 영역을 지정하므로 det 을 거의 안 쓴다(§4.2.2) |
| **C** | `OCR_LANG` 설정 **삭제**, 모델 경로 3종으로 대체 | RapidOCR 엔 lang 문자열 API 가 없다. 죽은 설정은 오진("korean 인데 왜 영어로 읽히지")을 부른다 |
| **D** | `_paddle_reader` **재사용 금지**, PyMuPDF 유틸 3개만 재사용 (§10) | 가져오는 순간 B 가 코드로 뒤집힌다 |
| **E** | Windows.Media.Ocr — **측정 전 미채택** (§11) | 이득(의존성 0)은 크지만 B 에서 엔진을 줄여놓고 다시 늘리는 모순. 실측이 근거를 만들면 그때 |

---

## 14. 유지보수 내구성 — 세상이 변해도 살아남게

**안 썩는 것:** PDF 규격(ISO) · 좌표 수학 · Qt · **번들된 .onnx 파일** · onnxruntime(MS 유지, 하위호환 강함).
**썩는 것은 세 군데다. 각각 대책을 구조에 미리 넣는다:**

| 썩는 곳 | 왜 | 대책 (필수) |
|---|---|---|
| **rapidocr 래퍼** | OCR 생태계는 API 파괴 전과가 있다 (Paddle 2→3, RapidOCR 패키지 재편) | §4.6 계약 뒤에 격리. **진짜 자산은 래퍼가 아니라 `.onnx 3종 + OCREngine 계약.`** 최악엔 onnxruntime 직접 호출 ~200줄로 래퍼 없이 동작 — 이 사실 자체가 보험이다 |
| **PyInstaller 동결** | 의존성 하나만 올려도 DLL 누락 재발 | **버전 전부 고정** (`requirements.lock` + Python 마이너버전 명시). 오프라인 앱이라 보안 패치 압박이 약하다 → "돌아가면 안 올린다"가 정당한 전략. 빌드 성공한 환경(파이썬 버전·명령어)을 저장소에 문서로 커밋 |
| **사람** | 몇 달 뒤 깨졌을 때 "고쳐졌는지" 판정 수단이 없으면 유지보수 불가 | **골든 샘플 회귀 테스트**를 저장소에 포함: 샘플 PDF(텍스트·스캔·회전·암호화) + 기대 텍스트 + 리댁션 후 검색 0건 검증. 의존성을 올리든 엔진을 갈든 `pytest` 한 방으로 생사 판정 |

추가 원칙:
- **모델 파일은 URL 이 아니라 저장소(또는 사내 스토리지)에 커밋한다.** "다운로드 링크가 살아있다"는 가정은 몇 년을 못 버틴다. §2.1 의 huggingface 취득은 1회용이다.
- 골든 샘플은 **Phase 2부터** 쌓는다 (완성 후 만들려면 안 만들게 된다). Phase 별 완료 기준 검증을 그대로 테스트로 남기면 된다.
- UI(PySide6)와 core 를 §3 구조대로 분리 유지 — core 는 헤드리스로 테스트 가능해야 골든 샘플이 CI 없이도 돈다.

---

## 참고

- 대체되는 계획 → [`ustax-staff/docs/llm-extract-plan.md`](../ustax-staff/docs/llm-extract-plan.md) §6-2
- 배경 → `ustax-staff/docs/document-intake-plan.md`
- 기존 자산 → `../ustax-ocr-local-fastapi/` (`ocr.py` · `main.py`)
