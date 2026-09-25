"""인터넷에 올려 쓰기 위한 WSGI 앱.

집이나 회사 PC 에서 돌리는 것(webui.serve)과 다른 점.

  - 비밀번호를 받는다. 설계 조건이 밖으로 나가는 곳이므로 필수로 둔다.
  - '종료' 버튼이 없다. 누구든 눌러 서버를 내릴 수 있으면 안 된다.
  - gunicorn 같은 표준 서버가 돌린다. http.server 는 여러 사람이 붙는
    환경에 맞지 않는다.

띄우는 법 (호스팅 업체에서)
    gunicorn turbochiller.wsgi:application

환경변수
    TURBOCHILLER_PASSWORD  (필수) 접속 비밀번호
    TURBOCHILLER_USER      (선택) 아이디. 기본값 turbo
"""

from __future__ import annotations

import base64
import binascii
import hmac
import os
import urllib.parse
from typing import Callable, Iterable, Optional

from .webui import render_page

#: 아이디를 따로 정하지 않았을 때
DEFAULT_USER = "turbo"

#: 비밀번호를 안 정해 두었을 때 보여줄 안내 (계산은 하지 않는다)
NO_PASSWORD_PAGE = """<!doctype html>
<html lang="ko"><head><meta charset="utf-8">
<meta name="viewport" content="width=device-width,initial-scale=1">
<title>설정이 필요합니다</title>
<style>
body{font-family:system-ui,'Malgun Gothic',sans-serif;background:#f6f6f4;color:#0b0b0b;
     margin:0;padding:24px;line-height:1.6}
.box{max-width:560px;margin:8vh auto;background:#fff;border:1px solid #e0dfd9;
     border-radius:12px;padding:24px}
h1{font-size:19px;margin:0 0 12px}
code{background:#f0efea;padding:2px 6px;border-radius:4px;font-size:13px}
p{color:#52514e;font-size:14px}
</style></head><body><div class="box">
<h1>접속 비밀번호가 설정되지 않았습니다</h1>
<p>설계 조건이 밖으로 나가는 곳이라, 비밀번호 없이는 계산을 하지 않습니다.</p>
<p>호스팅 설정에서 환경변수 <code>TURBOCHILLER_PASSWORD</code> 를
   정하고 다시 시작해 주세요.</p>
</div></body></html>"""


def _unauthorized(start_response: Callable) -> Iterable[bytes]:
    body = (
        "<!doctype html><meta charset='utf-8'>"
        "<body style=\"font-family:system-ui,'Malgun Gothic',sans-serif;padding:24px\">"
        "<h2>로그인이 필요합니다</h2>"
        "<p>아이디와 비밀번호를 입력해 주세요.</p></body>"
    ).encode("utf-8")
    start_response(
        "401 Unauthorized",
        [
            ("Content-Type", "text/html; charset=utf-8"),
            ("Content-Length", str(len(body))),
            ("WWW-Authenticate", 'Basic realm="turbochiller", charset="UTF-8"'),
        ],
    )
    return [body]


def _check_auth(header: Optional[str], user: str, password: str) -> bool:
    """Basic 인증 헤더를 확인한다.

    비교는 hmac.compare_digest 로 한다. 글자를 하나씩 비교하면
    걸리는 시간 차이로 비밀번호를 알아낼 수 있기 때문이다.
    """
    if not header or not header.lower().startswith("basic "):
        return False
    try:
        decoded = base64.b64decode(header[6:].strip()).decode("utf-8")
    except (binascii.Error, UnicodeDecodeError, ValueError):
        return False
    got_user, _, got_password = decoded.partition(":")
    # compare_digest 는 ASCII 밖 글자를 받지 못한다. 한글 비밀번호도 되도록
    # 양쪽을 UTF-8 바이트로 바꿔 비교한다.
    #
    # and 로 이으면 아이디가 틀렸을 때 비밀번호 비교를 건너뛴다. 그러면
    # 응답이 돌아오는 시간 차이로 '아이디는 맞았다' 는 것이 새어 나간다.
    # 둘 다 계산해 두고 마지막에 합친다.
    user_ok = hmac.compare_digest(
        got_user.encode("utf-8"), user.encode("utf-8")
    )
    password_ok = hmac.compare_digest(
        got_password.encode("utf-8"), password.encode("utf-8")
    )
    return user_ok & password_ok


def create_app(
    password: Optional[str] = None,
    user: Optional[str] = None,
) -> Callable:
    """WSGI 앱을 만든다. 값을 안 주면 환경변수에서 읽는다."""
    password = password if password is not None else os.environ.get(
        "TURBOCHILLER_PASSWORD", ""
    )
    user = user or os.environ.get("TURBOCHILLER_USER", DEFAULT_USER)

    def app(environ: dict, start_response: Callable) -> Iterable[bytes]:
        path = environ.get("PATH_INFO", "/")

        # 호스팅 업체가 살아있는지 확인하는 용도. 인증 없이 답한다.
        if path == "/health":
            body = b"ok"
            start_response(
                "200 OK",
                [("Content-Type", "text/plain"), ("Content-Length", str(len(body)))],
            )
            return [body]

        if not password:
            body = NO_PASSWORD_PAGE.encode("utf-8")
            start_response(
                "503 Service Unavailable",
                [
                    ("Content-Type", "text/html; charset=utf-8"),
                    ("Content-Length", str(len(body))),
                ],
            )
            return [body]

        if not _check_auth(environ.get("HTTP_AUTHORIZATION"), user, password):
            return _unauthorized(start_response)

        if environ.get("REQUEST_METHOD", "GET") not in ("GET", "HEAD"):
            body = "GET 요청만 받습니다".encode("utf-8")
            start_response(
                "405 Method Not Allowed",
                [
                    ("Content-Type", "text/plain; charset=utf-8"),
                    ("Content-Length", str(len(body))),
                    ("Allow", "GET, HEAD"),
                ],
            )
            return [body]

        if path == "/favicon.ico":
            start_response("204 No Content", [("Content-Length", "0")])
            return [b""]

        query = urllib.parse.parse_qs(
            environ.get("QUERY_STRING", ""), keep_blank_values=True
        )
        try:
            # hosted=True 면 '종료' 버튼을 빼고 그린다
            page = render_page(query, hosted=True)
        except Exception as exc:
            page = (
                "<!doctype html><meta charset='utf-8'>"
                "<body style=\"font-family:system-ui,sans-serif;padding:24px\">"
                f"<h2>오류가 났습니다</h2><pre>{type(exc).__name__}</pre></body>"
            )
        body = page.encode("utf-8")
        start_response(
            "200 OK",
            [
                ("Content-Type", "text/html; charset=utf-8"),
                ("Content-Length", str(len(body))),
                # 브라우저가 옛 결과를 보여주지 않게 한다
                ("Cache-Control", "no-store"),
                # 기본적인 보안 헤더
                ("X-Content-Type-Options", "nosniff"),
                ("Referrer-Policy", "no-referrer"),
            ],
        )
        return [body] if environ.get("REQUEST_METHOD") != "HEAD" else [b""]

    return app


#: gunicorn 이 찾는 이름
application = create_app()


def main() -> None:
    """gunicorn 없이 직접 띄울 때 (시험용).

        python -m turbochiller.wsgi
    """
    from wsgiref.simple_server import make_server

    port = int(os.environ.get("PORT", "8000"))
    host = os.environ.get("HOST", "0.0.0.0")
    print(f"http://{host}:{port}/ 에서 서비스합니다 (Ctrl+C 로 종료)")
    if not os.environ.get("TURBOCHILLER_PASSWORD"):
        print("주의: TURBOCHILLER_PASSWORD 가 없어 계산이 막혀 있습니다")
    with make_server(host, port, application) as httpd:
        httpd.serve_forever()


if __name__ == "__main__":
    main()
