import html.parser
import pkgutil
import tenacity
import time

OCR = None


class HTMLParser(html.parser.HTMLParser):
    def __init__(self):
        super().__init__()
        self.data = {}
        self.salt = ""

    def handle_starttag(self, tag, attrs):
        if tag == "input":
            mapping = {k: v for k, v in attrs}
            if "name" in mapping.keys():
                k = mapping["name"]
                v = mapping.get("value", "")
                self.data.setdefault(k, v)
            elif mapping["id"] == "pwdDefaultEncryptSalt":
                self.salt = mapping["value"]


class AuthFailureException(Exception):
    pass


def encrypted_password(password, key):
    import execjs

    js_code = pkgutil.get_data(__package__, "js/encrypt.js").decode()

    js = execjs.compile(js_code)
    return js.call("encryptAES", password, key)


def validiate_cookies(session):
    response = session.post(
        "https://chat.nju.edu.cn/deepseek/ctx",
    ).json()
    return response["extend"]["roles"][0] == "LOGIN_USER_ROLE"


def get_auth(session, username, password):
    if not validiate_cookies(session):
        try:
            get_auth_retry(session, username, password)
        except tenacity.RetryError:
            raise AuthFailureException(
                "Authentication failed with 3 attempts"
            ) from None


@tenacity.retry(
    stop=tenacity.stop_after_attempt(3),
    wait=tenacity.wait_fixed(2),
    retry=tenacity.retry_if_exception_type(AuthFailureException),
)
def get_auth_retry(session, username, password):
    global OCR
    html_content = session.get(
        "https://authserver.nju.edu.cn/authserver/login?service=https%3A%2F%2Fchat.nju.edu.cn%2Fdeepseek%2F",
    ).text
    html_parser = HTMLParser()
    html_parser.feed(html_content)

    mili = int(time.time() * 1000) % 1000
    image = session.get(
        f"https://authserver.nju.edu.cn/authserver/captcha.html?ts={mili}",
    ).content

    if OCR is None:
        from . import ddddocr

        OCR = ddddocr.DdddOcr()
    captcha = OCR.classification(image)
    session.post(
        "https://authserver.nju.edu.cn/authserver/login?service=https%3A%2F%2Fchat.nju.edu.cn%2Fdeepseek%2F",
        data={
            "username": username,
            "password": encrypted_password(password, html_parser.salt),
            "captchaResponse": captcha,
            "lt": html_parser.data["lt"],
            "dllt": "userNamePasswordLogin",
            "execution": html_parser.data["execution"],
            "_eventId": "submit",
            "rmShown": 1,
        },
    )

    if not validiate_cookies(session):
        raise AuthFailureException
