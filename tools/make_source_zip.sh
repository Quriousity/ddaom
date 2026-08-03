#!/bin/zsh
# 윈도우 PC 로 들고 갈 소스 묶음을 만든다 (USB·구글드라이브용).
# 사용: ./tools/make_source_zip.sh   →  ddaom-source.zip
set -e
cd "$(dirname "$0")/.."

OUT="ddaom-source.zip"
rm -f "$OUT"

# 빌드 산출물·가상환경·캐시는 제외 (모델은 반드시 포함 — 오프라인 동작의 핵심)
zip -r -q "$OUT" . \
  -x '.venv/*' -x 'dist/*' -x 'build/*' -x 'exe-download/*' \
  -x '*/__pycache__/*' -x '__pycache__/*' -x '*.pyc' \
  -x '.git/*' -x '.pytest_cache/*' -x '.DS_Store' -x '*/.DS_Store'

echo "완료 → $(pwd)/$OUT  ($(du -h "$OUT" | cut -f1))"
echo "윈도우 PC 에 복사해 압축을 풀고 'BUILD-EXE.bat' 를 더블클릭하세요."
