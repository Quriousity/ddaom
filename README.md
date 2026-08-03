# 따옴 (ddaom)

PDF 를 열어 마우스로 영역(사각형/폴리곤)을 지정하면 그 영역의 **텍스트를 클립보드에 복사**하는
Windows 데스크톱 앱. 한국어·영어·숫자 혼용 문서 대상. **완전 오프라인** (모델 번들).

- 텍스트 복사: 글자층 우선, 없으면 OCR (RapidOCR + PP-OCRv5 한국어)
- 선택 영역 이미지 추출 (클립보드 + PNG/JPEG/WEBP 저장, 폴리곤은 투명 배경 지원)
- 선택 영역 파괴적 리댁션 + 메타데이터 제거 → 새 PDF (저장 후 자동 검증)

상세 명세: [`staff-doc-tool-plan.md`](./staff-doc-tool-plan.md)

## 사용법

페이지를 열면 글자 영역이 자동 스캔되어 초록 박스로 깔린다 (글자층 즉시 / 스캔본은 OCR).

| 조작 | |
|---|---|
| **텍스트 박스 클릭** | 그 줄 텍스트 즉시 클립보드 복사 (호버로 하이라이트) |
| **드래그** | 영역 지정 — 지정 후 아래 세 가지 |
| `Ctrl+C` | ① 클립보드에 복사 (영역 텍스트) |
| `Ctrl+S` | ② 이미지로 저장 (+클립보드) |
| `Ctrl+D` | ③ 영역 파괴 → 새 PDF 저장 (메타데이터 제거 + 자동 검증) |
| `T` | 텍스트 박스 표시 켜기/끄기 |
| `Ctrl+휠` / `Ctrl+0` / `Ctrl++/-` | 줌 / 맞춤 |
| `PgUp` / `PgDn`, 스페이스+드래그, `Esc` | 페이지 이동, 팬, 선택 해제 |

## 개발 (macOS/Windows 공통)

```bash
python3.11 -m venv .venv
.venv/bin/pip install -r requirements.lock
.venv/bin/python -m pytest tests/ -q     # 골든 회귀 테스트 30개
.venv/bin/python run_app.py [pdf경로]     # 앱 실행
```

## Windows exe 빌드

### 방법 A — 윈도우 PC 에서 더블클릭 (지식 불필요)

1. Mac 에서 `./tools/make_source_zip.sh` → `ddaom-source.zip` (12MB)
2. USB·구글드라이브로 윈도우 PC 에 옮겨 압축 풀기
3. **`BUILD-EXE.bat` 더블클릭** → 파이썬 자동 설치 + 부품 내려받기 + exe 빌드까지 한 번에 (10~20분)
4. 끝나면 탐색기가 열리고 `dist\ddaom\ddaom.exe` 가 있다. 그 폴더째 원하는 곳에 복사해 쓰면 된다

빌드하는 PC 에만 인터넷이 필요하다. 완성된 exe 는 오프라인에서 동작한다.

### 방법 B — GitHub Actions (자동)

push 마다 자동 빌드한다 (`.github/workflows/build-windows.yml`).
아티팩트 `ddaom-win64.zip` 을 받아 풀고 `ddaom.exe` 실행 — 빌드용 PC 도 필요 없다.
`./setup-exe-build.sh` 가 저장소 생성 → push → 빌드 대기 → 다운로드까지 해준다.

수동 빌드 (Windows): `pip install -r requirements.lock && pyinstaller app.spec`

> ⚠ `requirements.lock` 은 macOS 에서 생성했다. 윈도우 첫 빌드가 실질적 검증이다 —
> 실패하면 해당 패키지만 버전을 풀어 다시 고정한다.

## 구조

```
app/
  models/     번들 OCR 모델 (det + korean rec + dict) — 저장소에 커밋됨 (§14)
  core/       coords(좌표변환) document extractor ocr_engine redactor clipboard
  ui/         main_window pdf_view selection
tests/        골든 회귀 + UI 스모크. samples/ 는 결정적 생성물(커밋됨)
tools/        make_samples.py — 샘플 PDF 재생성
```
