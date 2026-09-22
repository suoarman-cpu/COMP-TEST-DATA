@echo off
chcp 65001 > nul
title 터보 냉동기 사이클 해석
setlocal

rem 이 배치 파일이 있는 폴더로 이동한다.
cd /d "%~dp0"

set "APP=터보냉동기_사이클해석.py"

echo ============================================
echo   터보 냉동기 사이클 해석 프로그램
echo ============================================
echo.

if not exist "%APP%" goto :no_app

rem 파이썬 확인 (py 런처를 먼저 쓰고, 없으면 python 을 쓴다)
set "PY="
py -3 --version > nul 2>&1 && set "PY=py -3"
if not defined PY (
    python --version > nul 2>&1 && set "PY=python"
)
if not defined PY goto :no_python

echo 사용할 파이썬:
%PY% -c "import platform,sys; print('  ', sys.version.split()[0], platform.machine(), platform.architecture()[0])"
echo.

rem CoolProp 이 이미 있으면 설치 단계를 건너뛴다.
%PY% -c "import CoolProp" > nul 2>&1
if not errorlevel 1 goto :run

echo 냉매 물성 라이브러리(CoolProp)를 설치합니다. 처음 한 번만 몇 분 걸립니다...
echo.
%PY% -m pip install --upgrade pip
%PY% -m pip install CoolProp
if errorlevel 1 goto :install_failed
echo.

:run
echo 브라우저가 열립니다. 이 창은 닫지 마세요.
echo 프로그램을 끝내려면 이 창에서 Ctrl+C 를 누르세요.
echo.
%PY% "%APP%"
echo.
pause
exit /b 0


:no_app
echo [오류] %APP% 파일을 찾을 수 없습니다.
echo.
echo   지금 위치: %CD%
echo.
echo   이 배치 파일과 %APP% 이
echo   "같은 폴더" 에 있어야 합니다.
echo   두 파일을 같은 폴더에 넣고 다시 실행해 주세요.
echo.
pause
exit /b 1


:no_python
echo [오류] 파이썬이 설치되어 있지 않거나 PATH 에 등록되지 않았습니다.
echo.
echo   https://www.python.org/downloads/ 에서 받아 설치한 뒤 다시 실행해 주세요.
echo   설치 화면 맨 아래 "Add Python to PATH" 를 꼭 체크하세요.
echo.
pause
exit /b 1


:install_failed
echo.
echo [오류] CoolProp 설치에 실패했습니다.
echo.
echo   위에 나온 빨간 글씨를 그대로 알려주시면 도와드리겠습니다.
echo   (회사 네트워크의 방화벽/프록시 때문일 수도 있습니다)
echo.
pause
exit /b 1
