#!/bin/zsh
# exe 빌드 원커맨드 세팅 — 돌아와서 이것만 실행하면 된다:
#   ./setup-exe-build.sh
# 하는 일: GitHub 로그인 → private 저장소 생성 → push → Actions 빌드 대기 → exe zip 다운로드
set -e
cd "$(dirname "$0")"

REPO_NAME="ustax-pdf-area-tool"

echo "== 1/4 GitHub 로그인 =="
if ! gh auth status >/dev/null 2>&1; then
  gh auth login --web --git-protocol https
fi
gh auth status

echo "== 2/4 private 저장소 생성 + push =="
if ! git remote get-url origin >/dev/null 2>&1; then
  gh repo create "$REPO_NAME" --private --source=. --remote=origin
fi
git push -u origin main

echo "== 3/4 Actions 빌드 대기 (약 5~8분) =="
sleep 10
RUN_ID=$(gh run list --workflow=build-windows-exe --limit 1 --json databaseId -q '.[0].databaseId')
gh run watch "$RUN_ID" --exit-status

echo "== 4/4 exe 다운로드 =="
rm -rf ./exe-download && mkdir -p ./exe-download
gh run download "$RUN_ID" -n pdf-area-tool-win64 -D ./exe-download

echo ""
echo "완료 → $(pwd)/exe-download/pdf-area-tool-win64.zip"
echo "윈도우 PC 에 복사해서 압축 풀고 pdf-area-tool.exe 실행 (설치 불필요, 오프라인 동작)"
