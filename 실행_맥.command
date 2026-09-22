#!/bin/bash
# 맥에서 두 번 눌러 실행합니다.
# 처음 한 번은 "보안 때문에 열 수 없음" 이 뜰 수 있습니다.
#   -> 시스템 설정 > 개인정보 보호 및 보안 > "확인 없이 열기" 를 누르세요.

cd "$(dirname "$0")" || exit 1

echo "============================================"
echo "  터보 냉동기 사이클 해석 프로그램"
echo "============================================"
echo

if ! command -v python3 > /dev/null 2>&1; then
    echo "[오류] 파이썬이 설치되어 있지 않습니다."
    echo "  https://www.python.org/downloads/ 에서 받아 설치한 뒤 다시 실행해 주세요."
    read -r -p "엔터를 누르면 닫힙니다..."
    exit 1
fi

if [ ! -f ".설치완료" ]; then
    echo "필요한 라이브러리를 설치합니다. 몇 분 걸립니다..."
    echo
    python3 -m pip install --upgrade pip
    if ! python3 -m pip install -r requirements.txt; then
        echo
        echo "[오류] 설치에 실패했습니다. 인터넷 연결을 확인해 주세요."
        read -r -p "엔터를 누르면 닫힙니다..."
        exit 1
    fi
    echo "설치 완료" > .설치완료
    echo
fi

echo "브라우저가 열립니다. 이 창은 닫지 마세요."
echo "프로그램을 끝내려면 이 창에서 Control+C 를 누르세요."
echo
python3 -m streamlit run app.py
