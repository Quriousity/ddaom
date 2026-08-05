# 따옴 (ddaom)

PDF·이미지에서 **원하는 글자만 집어서 복사**하는 윈도우 프로그램.
한국어·영어·숫자 혼용 서류용. **완전 오프라인** — 인터넷 없이 동작하고 내용이 밖으로 나가지 않는다.

[![License: AGPL v3](https://img.shields.io/badge/License-AGPL_v3-blue.svg)](./LICENSE)

- **글자 클릭 = 복사 + 담기** — 문서를 열면 글자 영역을 자동 인식해 표시. 클릭하면 바로 클립보드로 가고, 오른쪽 **담은 목록**에도 쌓입니다
- **담은 것을 한 번에 파괴** — 여러 페이지를 오가며 담은 뒤 `담은 목록 파괴하고 원본형식으로 저장` 한 번으로 전부 지워 새 파일로 저장. 모드 전환은 없습니다
- **영역 드래그 = 담기** — 글자로 인식되지 않은 도장·사진·표도 드래그 한 번으로 담깁니다
- **현재 페이지를 통째로 이미지 저장** — 드래그 없이 `Ctrl+S`
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

끝나면 탐색기가 자동으로 열리고 바탕화면의 **`ddaom.exe`** 가 선택된 채로 보입니다.
파일 하나로 끝이라 그대로 원하는 곳에 복사해서 쓰면 됩니다.
(단일 파일이라 실행할 때마다 내부를 임시폴더에 푸는데, 첫 화면까지 10~30초 걸리는 게 정상입니다.)

**PDF 연결 프로그램으로 지정하기** (선택):
PDF 파일 우클릭 → 연결 프로그램 → 다른 앱 선택 → `ddaom.exe` → "항상 이 앱 사용" 체크.
이제 PDF 를 더블클릭하면 따옴으로 열립니다.

### 실행이 막힐 때 — Smart App Control

윈도우 11 에서 **"Smart App Control 이 이 앱을 차단했습니다"** 가 뜰 수 있습니다.

Smart App Control 은 마이크로소프트가 서명과 평판을 확인하지 못한 프로그램을 아예 실행하지 못하게
막는 기능입니다. 따옴은 각자 PC 에서 직접 빌드하는 프로그램이라 코드 서명이 없고, 그래서 차단 대상이
됩니다. **바이러스로 판정된 것이 아닙니다.**

> ⚠ **끄기 전에 반드시 읽으세요 — 한 번 끄면 다시 켤 수 없습니다.**
> 설정 화면에서 "켜기" 선택지 자체가 사라집니다. 되살리려면 **윈도우를 초기화하거나 재설치**해야
> 합니다. 마이크로소프트가 의도적으로 그렇게 설계했습니다.

**끄는 방법**

설정 → 개인 정보 및 보안 → Windows 보안 → 앱 및 브라우저 컨트롤 → **스마트 앱 컨트롤** → `끄기`

**회사 PC 라면 직접 끄지 마세요.** 회사가 관리하는 기기(Intune 등록 · 도메인 조인)에서는 Smart App
Control 이 48시간 안에 자동으로 꺼지게 되어 있습니다. 그런데도 차단된다면 IT 담당자에게 문의하세요.
개인이 보안 기능을 영구히 해제하는 것보다, IT 가 App Control 정책으로 이 앱만 허용해 주는 편이
안전하고 되돌릴 수도 있습니다.

---

## 사용법

문서를 열면 글자 영역이 자동 인식되어 상자로 표시됩니다.

| 조작 | 동작 |
|---|---|
| **글자 상자 클릭** | 그 줄을 클립보드로 복사 + **담은 목록**에 담기 |
| **드래그** | 그 영역을 담은 목록에 넣기 (놓는 즉시. 인식 안 된 자리를 지울 때) |
| `Ctrl+S` | **현재 페이지 이미지로 저장** — 드래그와 무관하게 페이지 통째로 |
| **`담은 목록 파괴하고 원본형식으로 저장`** | 담은 목록을 **전부 지운** 새 파일 저장 (되살릴 수 없게 파괴 + 문서 정보 제거). 되돌릴 수 없어 단축키가 없습니다 |
| **행의 `✕`** | 그 항목을 담은 목록에서 빼기 |
| **우클릭 드래그** | 문서를 잡고 이동 |
| `Ctrl+휠` / `Ctrl+0` | 확대·축소 / 화면에 맞추기 |
| `↑` `↓` | 이전·다음 페이지 |
| `T` | 글자 인식 표시 켜기/끄기 |
| `[` `]` | 미리보기 / 담은 목록 패널 접기·펴기 |

**담은 목록에 있는 것이 곧 지워집니다.** 글자는 행에서 바로 고칠 수 있고(복사용),
고쳐도 지워지는 위치는 담을 때 잡아둔 좌표 그대로입니다.

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
.venv/bin/python -m pytest tests/ -q     # 회귀 테스트
.venv/bin/python run_app.py [파일경로]
```

### exe 빌드 다른 방법

- **수동** (윈도우) — `pip install -r requirements.lock && pyinstaller app.spec`
- **소스 묶음 만들기** (USB 전달용) — `./tools/make_source_zip.sh` → `ddaom-source.zip`

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

---

## 라이선스

이 프로젝트는 **GNU Affero General Public License v3.0 (AGPL-3.0)** 을 따릅니다.
전문은 [LICENSE](./LICENSE) 파일에 있으며, 아래 요약과 충돌하는 경우 **전문이 우선합니다.**

### 권한 · 조건 · 제한

| ✅ 허용 | ⚠ 조건 | ❌ 제한 |
|---|---|---|
| 상업적 이용 | 소스 코드 공개 | 무보증 |
| 수정 | 라이선스 및 저작권 고지 | 책임 제한 |
| 배포 | 동일 라이선스로 배포 | |
| 특허 이용 | 변경 사항 명시 | |
| 사적 이용 | 네트워크 이용 시 소스 공개 | |

- **혼자 쓰거나 사내에서만 쓰는 것은 배포가 아니므로** 소스 공개 의무가 없습니다.
- **배포하거나 네트워크 서비스로 제공하면** 수정한 소스 전체를 AGPL-3.0 으로 공개해야 합니다.

### 보증 및 책임의 부인

본 소프트웨어는 **"있는 그대로(AS IS)"** 제공되며, 상품성이나 특정 목적 적합성을 포함한
어떠한 명시적·묵시적 보증도 하지 않습니다. 저작권자는 본 소프트웨어의 사용 또는 사용 불능으로
발생하는 어떠한 손해에 대해서도 책임을 지지 않습니다. (AGPL-3.0 §15 · §16)

> ⚠ **데이터 파괴 기능 주의** — 본 프로그램은 문서 내용을 복구 불가능하게 파괴하는 기능(`담은 목록 파괴하고 원본형식으로 저장`)을
> 포함합니다. 원본을 덮어쓰지 않도록 설계했으나, 중요한 문서는 **반드시 원본을 별도 보관한 뒤**
> 사용하십시오. 파괴 결과에 대한 책임은 전적으로 사용자에게 있습니다.

### 제3자 구성요소

| 구성요소 | 용도 | 라이선스 |
|---|---|---|
| **PyMuPDF** | PDF 처리 · 리댁션 | **AGPL-3.0** — 이 프로젝트가 AGPL-3.0 인 이유 |
| **PySide6 / Qt** | 화면 | LGPL-3.0 — 배포 시 라이브러리 교체 가능성 보장 필요 |
| RapidOCR · PP-OCRv5 모델 | OCR | Apache-2.0 |
| onnxruntime | OCR 추론 | MIT |
| Pillow | 이미지 처리 | MIT-CMU |
| numpy | 수치 연산 | BSD-3-Clause |
| PyInstaller | exe 빌드 | GPL + bootloader 예외 (exe 배포 제약 없음) |

소스를 비공개로 배포해야 할 경우, PyMuPDF 상용 라이선스를 구매하거나
`pypdfium2`(렌더 · 텍스트) + `pikepdf`(구조 · 메타데이터)로 교체해야 합니다.
단 후자에는 리댁션 기능이 없어 직접 구현해야 합니다.

---

## License

This project is licensed under the **GNU Affero General Public License v3.0 (AGPL-3.0)**.
The full text is in the [LICENSE](./LICENSE) file and **prevails over this summary**
in case of any conflict.

### Permissions · Conditions · Limitations

| ✅ Permissions | ⚠ Conditions | ❌ Limitations |
|---|---|---|
| Commercial use | Disclose source | No warranty |
| Modification | License and copyright notice | Limitation of liability |
| Distribution | Same license | |
| Patent use | State changes | |
| Private use | Network use is distribution | |

- **Personal or internal-only use is not distribution**, and carries no obligation to disclose source.
- **If you distribute the software or provide it as a network service**, you must release your
  complete modified source under the AGPL-3.0.

### Disclaimer of Warranty and Liability

This software is provided **"AS IS"**, without warranty of any kind, express or implied,
including but not limited to the warranties of merchantability and fitness for a particular
purpose. In no event shall the copyright holder be liable for any claim, damages or other
liability arising from, out of or in connection with the software or the use or other dealings
in the software. (AGPL-3.0 §15 and §16)

> ⚠ **Destructive feature notice** — This program includes a function (destructive save) that
> irreversibly destroys document content. It never overwrites the original file by design,
> but you should **always keep a separate backup** of important documents before use.
> The user bears full responsibility for the results of redaction.

### Third-Party Components

| Component | Purpose | License |
|---|---|---|
| **PyMuPDF** | PDF processing · redaction | **AGPL-3.0** — the reason this project is AGPL-3.0 |
| **PySide6 / Qt** | GUI | LGPL-3.0 — relinking must remain possible when distributed |
| RapidOCR · PP-OCRv5 models | OCR | Apache-2.0 |
| onnxruntime | OCR inference | MIT |
| Pillow | Image processing | MIT-CMU |
| numpy | Numerics | BSD-3-Clause |
| PyInstaller | exe build | GPL with bootloader exception (no restriction on the built exe) |

To distribute this software without disclosing source, you would need a commercial PyMuPDF
license, or replace it with `pypdfium2` (rendering · text) + `pikepdf` (structure · metadata) —
though the latter has no true redaction and would require implementing it yourself.

### License Notice

```
ddaom (따옴) — extract, copy and redact text regions from PDFs and images.
Copyright (C) 2026  Quriousity

This program is free software: you can redistribute it and/or modify
it under the terms of the GNU Affero General Public License as published by
the Free Software Foundation, either version 3 of the License, or
(at your option) any later version.

This program is distributed in the hope that it will be useful,
but WITHOUT ANY WARRANTY; without even the implied warranty of
MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE.  See the
GNU Affero General Public License for more details.

You should have received a copy of the GNU Affero General Public License
along with this program.  If not, see <https://www.gnu.org/licenses/>.
```
