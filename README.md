# 따옴 (ddaom)

PDF·이미지에서 **원하는 글자만 집어서 복사**하는 윈도우 프로그램.
한국어·영어·숫자 혼용 서류용. **완전 오프라인** — 인터넷 없이 동작하고 내용이 밖으로 나가지 않는다.

- **글자 클릭 = 복사** — 문서를 열면 글자 영역을 자동 인식해 표시. 클릭하면 바로 클립보드로
- **영역 지정 후 3가지** — ① 텍스트 복사 ② 이미지로 저장 ③ 그 영역을 지우고 새 파일 저장
- **담은 텍스트** 패널에 모아서 고친 뒤 한 번에 복사
- 스캔 문서·사진도 OCR 로 읽는다 (RapidOCR + PP-OCRv5 한국어 모델 번들)

---

## 설치 (윈도우) — 이대로만 따라 하면 됩니다

프로그래밍 지식이 없어도 됩니다. 처음 한 번만 15~20분 걸리고, 그다음부터는 바로 실행됩니다.

### 1. 파일 내려받기

이 페이지 위쪽의 초록색 **`< > Code`** 버튼 → **`Download ZIP`** 을 누릅니다.
`ddaom-main.zip` 파일이 다운로드 폴더에 저장됩니다.

### 2. 압축 풀기

받은 zip 파일을 **우클릭 → "압축 풀기"** 합니다.
바탕화면처럼 찾기 쉬운 곳에 푸는 것을 권합니다.

### 3. `BUILD-EXE.bat` 더블클릭

압축을 푼 폴더 안에 있는 **`BUILD-EXE.bat`** 을 더블클릭합니다.
검은 창이 열리고 아래 순서로 알아서 진행됩니다. **창을 닫지 말고 기다리세요.**

```
[1/4] 파이썬 확인 중...      ← 없으면 자동으로 설치합니다
[2/4] 준비 중...
[3/4] 필요한 부품 내려받는 중...   ← 가장 오래 걸립니다 (5~15분)
[4/4] exe 만드는 중...
```

> 이 단계에서만 **인터넷이 필요합니다**. 완성된 프로그램은 인터넷 없이 동작합니다.
> 파란색 "Windows의 PC 보호" 경고가 뜨면 **추가 정보 → 실행**을 누르세요.

### 4. 완료

끝나면 탐색기가 자동으로 열리고 **`ddaom.exe`** 가 보입니다.
그 폴더(`dist\ddaom`)를 통째로 원하는 곳에 복사해서 쓰면 됩니다.

**PDF 연결 프로그램으로 지정하기** (선택):
PDF 파일 우클릭 → 연결 프로그램 → 다른 앱 선택 → `ddaom.exe` → "항상 이 앱 사용" 체크.
이제 PDF 를 더블클릭하면 따옴으로 열립니다.

---

## 사용법

문서를 열면 글자 영역이 자동 인식되어 상자로 표시됩니다.

| 조작 | 동작 |
|---|---|
| **글자 상자 클릭** | 그 줄을 바로 클립보드로 복사 |
| **드래그** | 영역 지정 — 아래 세 가지를 할 수 있습니다 |
| `Ctrl+C` | ① 선택 영역 텍스트 복사 |
| `Ctrl+S` | ② 선택 영역을 이미지 파일로 저장 |
| `Ctrl+D` | ③ 선택 영역을 **지운** 새 파일 저장 (되살릴 수 없게 파괴 + 문서 정보 제거) |
| **우클릭 드래그** | 문서를 잡고 이동 |
| `Ctrl+휠` / `Ctrl+0` | 확대·축소 / 화면에 맞추기 |
| `↑` `↓` | 이전·다음 페이지 |
| `T` | 글자 인식 표시 켜기/끄기 |
| `[` `]` | 미리보기 / 담은 텍스트 패널 접기·펴기 |

**저장 파일 이름 규칙** (원본과 같은 폴더, 덮어쓰지 않음)
- 이미지: `원본이름_p2_01.png`
- 지운 파일: `원본이름_redacted.pdf` (이미지 원본이면 `.png`)

지운 파일은 저장 직후 프로그램이 **다시 열어서 정말 지워졌는지 검사**하고 결과를 알려줍니다.

여는 형식: PDF, PNG, JPG, WEBP, BMP, TIFF

---

## 개발자용

### 실행 (macOS / Windows)

```bash
python3.11 -m venv .venv
.venv/bin/pip install -r requirements.lock
.venv/bin/python -m pytest tests/ -q     # 회귀 테스트 46개
.venv/bin/python run_app.py [파일경로]
```

### exe 빌드 다른 방법

- **수동** (윈도우) — `pip install -r requirements.lock && pyinstaller app.spec`
- **소스 묶음 만들기** (USB 전달용) — `./tools/make_source_zip.sh` → `ddaom-source.zip`
- **GitHub Actions** — 워크플로 파일(`.github/workflows/build-windows.yml`)은 로컬에만 두고
  저장소에는 올리지 않았다 (푸시 토큰에 `workflow` 스코프가 필요하기 때문).
  쓰려면 토큰에 그 권한을 준 뒤 `.gitignore` 의 `.github/` 줄을 지우고 커밋하면 된다.
  그러면 push 마다 윈도우 러너가 테스트 + 빌드해 `ddaom-win64.zip` 을 만들어준다.

> ⚠ `requirements.lock` 은 macOS 에서 생성했다. 윈도우 첫 빌드가 실질적 검증이다 —
> 실패하면 해당 패키지만 버전을 풀어 다시 고정한다.

### 구조

```
app/
  models/     번들 OCR 모델 (det + korean rec + dict) — 저장소에 커밋됨
  core/       coords(좌표변환) document extractor ocr_engine redactor clipboard
  ui/         main_window pdf_view selection widgets theme
tests/        골든 회귀 + UI 스모크. samples/ 는 결정적 생성물
tools/        make_samples.py(샘플 생성) · make_source_zip.sh
```

설계 근거와 함정은 [`staff-doc-tool-plan.md`](./staff-doc-tool-plan.md) 참고.

### 라이선스 주의

PyMuPDF 는 AGPL-3.0. 소스 비공개로 배포할 계획이 생기면 상용 라이선스를 사거나
`pypdfium2` + `pikepdf` 로 교체해야 한다 (단 후자는 진짜 파괴 기능이 없어 직접 구현 필요).
OCR 쪽(RapidOCR·PP-OCR 모델)은 Apache 2.0 이라 제약이 없다.
