"""인터넷에 올리는 WSGI 앱 검증 — 주로 '막아야 할 것을 막는지' 본다."""

from __future__ import annotations

import base64

import pytest
from wsgiref.util import setup_testing_defaults

from turbochiller.wsgi import DEFAULT_USER, create_app

PASSWORD = "비밀번호1234"      # 한글이 섞여도 되어야 한다
QUIT_LINK = 'href="/quit"'


def call(app, *, auth=None, path="/", query="", method="GET"):
    env: dict = {}
    setup_testing_defaults(env)
    env.update(PATH_INFO=path, QUERY_STRING=query, REQUEST_METHOD=method)
    if auth is not None:
        env["HTTP_AUTHORIZATION"] = auth
    captured: dict = {}

    def start_response(status, headers):
        captured["status"] = status
        captured["headers"] = dict(headers)

    body = b"".join(app(env, start_response))
    return captured["status"], captured["headers"], body


def basic(user: str, password: str) -> str:
    return "Basic " + base64.b64encode(f"{user}:{password}".encode()).decode()


@pytest.fixture
def app():
    return create_app(password=PASSWORD)


# --- 비밀번호를 안 정한 경우 ---------------------------------------------

def test_without_password_nothing_is_calculated() -> None:
    """비밀번호가 없으면 계산을 하지 않고 안내만 보여줘야 한다.

    설정을 빠뜨렸을 때 아무나 볼 수 있게 열리는 쪽이 제일 위험하다.
    """
    status, _, body = call(create_app(password=""))
    assert status.startswith("503")
    assert "비밀번호가 설정되지" in body.decode()
    assert "COP" not in body.decode()


def test_health_works_without_password() -> None:
    """호스팅 업체의 상태 확인은 비밀번호 없이도 답해야 한다."""
    status, _, body = call(create_app(password=""), path="/health")
    assert status.startswith("200")
    assert body == b"ok"


# --- 인증 -----------------------------------------------------------------

def test_no_auth_is_rejected(app) -> None:
    status, headers, _ = call(app)
    assert status.startswith("401")
    assert "WWW-Authenticate" in headers


@pytest.mark.parametrize(
    "user,password",
    [
        (DEFAULT_USER, "틀린비번"),
        ("다른아이디", PASSWORD),
        ("", ""),
        (DEFAULT_USER, PASSWORD[:-1]),   # 한 글자 모자란 경우
    ],
)
def test_wrong_credentials_are_rejected(app, user: str, password: str) -> None:
    status, _, _ = call(app, auth=basic(user, password))
    assert status.startswith("401")


def test_broken_auth_header_is_rejected(app) -> None:
    """깨진 헤더를 받아도 예외로 죽지 않고 401 이어야 한다."""
    for header in ("Basic !!!not-base64!!!", "Bearer abc", "Basic", "", "Basic " + "a"):
        status, _, _ = call(app, auth=header)
        assert status.startswith("401"), header


def test_correct_credentials_work_with_non_ascii_password(app) -> None:
    """한글 비밀번호도 되어야 한다 (compare_digest 가 ASCII 만 받는 함정)."""
    status, _, body = call(app, auth=basic(DEFAULT_USER, PASSWORD))
    assert status.startswith("200")
    assert "COP" in body.decode()


# --- 올려두었을 때 막아야 할 것 -------------------------------------------

def test_quit_button_is_not_shown(app) -> None:
    """인터넷에 올린 화면에는 '종료' 가 없어야 한다.

    있으면 접속한 누구든 서버를 내릴 수 있다.
    """
    _, _, body = call(app, auth=basic(DEFAULT_USER, PASSWORD))
    assert QUIT_LINK not in body.decode()
    assert "종료" not in body.decode()


def test_quit_path_does_not_shut_down(app) -> None:
    """/quit 으로 직접 들어와도 그냥 일반 페이지여야 한다."""
    status, _, body = call(app, auth=basic(DEFAULT_USER, PASSWORD), path="/quit")
    assert status.startswith("200")
    assert "종료했습니다" not in body.decode()


def test_post_is_rejected(app) -> None:
    status, headers, _ = call(app, auth=basic(DEFAULT_USER, PASSWORD), method="POST")
    assert status.startswith("405")
    assert "Allow" in headers


def test_security_headers(app) -> None:
    _, headers, _ = call(app, auth=basic(DEFAULT_USER, PASSWORD))
    assert headers.get("Cache-Control") == "no-store"
    assert headers.get("X-Content-Type-Options") == "nosniff"
    assert headers.get("Referrer-Policy") == "no-referrer"


# --- 계산이 실제로 되는지 -------------------------------------------------

def test_query_values_are_used(app) -> None:
    _, _, body = call(
        app, auth=basic(DEFAULT_USER, PASSWORD),
        query="refrigerant=R134a&capacity_rt=200&stages=1",
    )
    text = body.decode()
    assert "R134a" in text
    assert "200" in text


def test_bad_input_shows_message_not_crash(app) -> None:
    status, _, body = call(
        app, auth=basic(DEFAULT_USER, PASSWORD),
        query="cooling_medium_in=-50&cond_approach=0.5&chilled_water_out=25",
    )
    assert status.startswith("200")
    assert "계산할 수 없는 조건" in body.decode()


def test_password_from_environment(monkeypatch) -> None:
    monkeypatch.setenv("TURBOCHILLER_PASSWORD", "환경변수비번")
    monkeypatch.setenv("TURBOCHILLER_USER", "myid")
    env_app = create_app()
    assert call(env_app, auth=basic("myid", "환경변수비번"))[0].startswith("200")
    assert call(env_app, auth=basic(DEFAULT_USER, "환경변수비번"))[0].startswith("401")
