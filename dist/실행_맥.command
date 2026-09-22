#!/bin/bash
# 맥에서 두 번 눌러 실행합니다.
# 이 파일과 터보냉동기_사이클해석.py 가 같은 폴더에 있어야 합니다.

cd "$(dirname "$0")" || exit 1

APP="터보냉동기_사이클해석.py"

echo "============================================"
echo "  터보 냉동기 사이클 해석 프로그램"
echo "============================================"
echo

pause_and_exit() {
    echo
    read -r -p "엔터를 누르면 창이 닫힙니다..."
    exit "$1"
}

if [ ! -f "$APP" ]; then
    echo "[오류] $APP 파일을 찾을 수 없습니다."
    echo
    echo "  지금 위치: $(pwd)"
    echo
    echo "  이 파일과 $APP 이 같은 폴더에 있어야 합니다."
    pause_and_exit 1
fi

if command -v python3 > /dev/null 2>&1; then
    PY=python3
else
    echo "[오류] 파이썬이 설치되어 있지 않습니다."
    echo "  https://www.python.org/downloads/ 에서 받아 설치한 뒤 다시 실행해 주세요."
    pause_and_exit 1
fi

echo "사용할 파이썬: $($PY --version)"
echo

if [ ! -f ".installed" ]; then
    echo "필요한 라이브러리를 설치합니다. 처음 한 번만 몇 분 걸립니다..."
    echo
    $PY -m pip install --upgrade pip
    if ! $PY -m pip install CoolProp streamlit pandas matplotlib; then
        echo
        echo "[오류] 라이브러리 설치에 실패했습니다."
        echo "  - 인터넷 연결을 확인해 주세요."
        echo "  - 회사 네트워크라면 방화벽/프록시 때문일 수 있습니다."
        pause_and_exit 1
    fi
    echo "설치 완료" > .installed
    echo
fi

echo "브라우저가 열립니다. 이 창은 닫지 마세요."
echo "프로그램을 끝내려면 이 창에서 Control+C 를 누르세요."
echo
$PY -m streamlit run "$APP"
