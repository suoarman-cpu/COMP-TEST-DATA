@echo off
chcp 65001 > nul
title 터보 냉동기 사이클 해석

echo ============================================
echo   터보 냉동기 사이클 해석 프로그램
echo ============================================
echo.

python --version > nul 2>&1
if errorlevel 1 (
    echo [오류] 파이썬이 설치되어 있지 않습니다.
    echo.
    echo   https://www.python.org/downloads/ 에서 받아 설치한 뒤
    echo   다시 실행해 주세요.
    echo   설치할 때 "Add Python to PATH" 를 꼭 체크하세요.
    echo.
    pause
    exit /b 1
)

if not exist ".설치완료" (
    echo 필요한 라이브러리를 설치합니다. 몇 분 걸립니다...
    echo.
    python -m pip install --upgrade pip
    python -m pip install -r requirements.txt
    if errorlevel 1 (
        echo.
        echo [오류] 설치에 실패했습니다. 인터넷 연결을 확인해 주세요.
        pause
        exit /b 1
    )
    echo 설치 완료 > .설치완료
    echo.
)

echo 브라우저가 열립니다. 이 창은 닫지 마세요.
echo 프로그램을 끝내려면 이 창에서 Ctrl+C 를 누르세요.
echo.
python -m streamlit run app.py

pause
