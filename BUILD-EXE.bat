@echo off
chcp 65001 >nul
setlocal
cd /d "%~dp0"

echo.
echo  ============================================
echo    따옴 (ddaom) - 윈도우 exe 만들기
echo  ============================================
echo.
echo   이 창을 닫지 마세요. 10~20분 걸립니다.
echo   (인터넷 연결이 필요합니다)
echo.

REM ============ 1. 파이썬 찾기 ============
echo  [1/4] 파이썬 확인 중...
set "PYCMD="

py -3.11 -V >nul 2>&1
if not errorlevel 1 (
    set "PYCMD=py -3.11"
    goto :got_python
)

py -3.12 -V >nul 2>&1
if not errorlevel 1 (
    set "PYCMD=py -3.12"
    goto :got_python
)

REM Microsoft Store 앱 별칭(0바이트 스텁)은 출력이 없으므로 걸러진다
REM 기본값 0 — 비어 있으면 %PYVER% 전개가 구문 오류를 낸다
set "PYVER=0"
for /f "delims=" %%v in ('python -c "import sys; print(sys.version_info[0]*100+sys.version_info[1])" 2^>nul') do set "PYVER=%%v"
if %PYVER% GEQ 311 (
    set "PYCMD=python"
    goto :got_python
)

REM ============ 파이썬 자동 설치 ============
echo        파이썬이 없습니다. 자동으로 설치합니다 (약 3분)...
set "PYURL=https://www.python.org/ftp/python/3.11.9/python-3.11.9-amd64.exe"
set "PYINST=%TEMP%\python-3.11.9-amd64.exe"

curl -L -# -o "%PYINST%" "%PYURL%"
if errorlevel 1 (
    echo        curl 실패 - 다른 방법으로 내려받습니다...
    powershell -NoProfile -Command "[Net.ServicePointManager]::SecurityProtocol='Tls12'; Invoke-WebRequest -Uri '%PYURL%' -OutFile '%PYINST%'"
)
if not exist "%PYINST%" (
    echo.
    echo  [실패] 파이썬을 내려받지 못했습니다.
    echo         인터넷 연결 또는 회사 방화벽을 확인하세요.
    goto :fail
)

echo        설치 중... (창이 없어도 진행 중입니다)
"%PYINST%" /quiet InstallAllUsers=0 PrependPath=1 Include_launcher=1 Include_test=0
del "%PYINST%" >nul 2>&1

REM 설치 직후에는 PATH 가 갱신되지 않으므로 설치 경로를 직접 쓴다
if exist "%LOCALAPPDATA%\Programs\Python\Python311\python.exe" (
    set PYCMD="%LOCALAPPDATA%\Programs\Python\Python311\python.exe"
    goto :got_python
)
py -3.11 -V >nul 2>&1
if not errorlevel 1 (
    set "PYCMD=py -3.11"
    goto :got_python
)

echo.
echo  [실패] 파이썬 설치를 확인하지 못했습니다.
echo         이 PC 를 다시 시작한 뒤 이 파일을 한 번 더 실행해 보세요.
goto :fail

:got_python
echo        OK
echo.

REM ============ 2. 준비 (가상환경) ============
echo  [2/4] 준비 중...
if exist ".venv\Scripts\python.exe" goto :venv_ready
%PYCMD% -m venv .venv
if errorlevel 1 (
    echo.
    echo  [실패] 가상환경을 만들지 못했습니다.
    goto :fail
)
:venv_ready
set "VPY=.venv\Scripts\python.exe"
echo        OK
echo.

REM ============ 3. 필요한 프로그램 내려받기 ============
echo  [3/4] 필요한 부품 내려받는 중... (가장 오래 걸립니다, 5~15분)
"%VPY%" -m pip install --upgrade pip --quiet
"%VPY%" -m pip install -r requirements.lock --quiet
if errorlevel 1 (
    echo.
    echo  [실패] 부품 설치에 실패했습니다. 인터넷 연결을 확인하세요.
    goto :fail
)
echo        OK
echo.

REM ============ 4. exe 만들기 ============
REM 바탕화면 경로 — OneDrive 로 옮겨진 경우까지 잡으려면 셸에 물어봐야 한다
set "DESKDIR=%USERPROFILE%\Desktop"
for /f "delims=" %%d in ('powershell -NoProfile -Command "[Environment]::GetFolderPath('Desktop')" 2^>nul') do set "DESKDIR=%%d"
if not exist "%DESKDIR%" set "DESKDIR=%CD%\dist"

echo  [4/4] exe 만드는 중... (3~5분)
"%VPY%" -m PyInstaller app-onefile.spec --noconfirm --log-level WARN --distpath "%DESKDIR%"
if errorlevel 1 (
    echo.
    echo  [실패] exe 빌드에 실패했습니다.
    goto :fail
)

if not exist "%DESKDIR%\ddaom.exe" (
    echo.
    echo  [실패] exe 파일이 만들어지지 않았습니다.
    goto :fail
)

echo.
echo  ============================================
echo    완성됐습니다!
echo  ============================================
echo.
echo    %DESKDIR%\ddaom.exe
echo.
echo    파일 하나로 끝입니다. 원하는 곳에 복사해서 쓰세요.
echo    ddaom.exe 를 더블클릭하면 실행됩니다.
echo    (첫 화면이 뜨기까지 10~30초 걸립니다 - 정상입니다)
echo.
echo    (탐색기를 열어 드립니다)
echo.
start "" explorer /select,"%DESKDIR%\ddaom.exe"
echo  아무 키나 누르면 창이 닫힙니다.
pause >nul
exit /b 0

:fail
echo.
echo  ------------------------------------------
echo   위의 오류 메시지를 그대로 캡처해서 문의하세요.
echo  ------------------------------------------
echo.
pause
exit /b 1
