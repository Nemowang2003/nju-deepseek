import tenacity

OCR = None


def encrypt(password, salt):
    cipher = AES.new(salt.encode("utf-8"), AES.MODE_CBC, iv=("a" * 16).encode("utf-8"))
    encrypted_password_bytes = cipher.encrypt(
        Padding.pad(("a" * 64 + password).encode("utf-8"), 16, "pkcs7")
    )
    return base64.b64encode(encrypted_password_bytes).decode("utf-8")


def validiate_cookies(session):
    response = session.post(
        "https://chat.nju.edu.cn/deepseek/ctx",
    ).json()
    return response["extend"]["roles"][0] == "LOGIN_USER_ROLE"


def get_auth(session, username, password):
    if validiate_cookies(session):
        return
    try:
        global base64, AES, Padding, lxml
        import base64
        from Cryptodome.Cipher import AES
        from Cryptodome.Util import Padding
        import lxml.etree

        get_auth_retry(session, username, password)
    except ImportError:
        raise ModuleNotFoundError(
            "run `pip install 'nju-deepseek[auth]'` to install missing dependencies"
        ) from None
    except tenacity.RetryError:
        raise ValueError("Authentication failed") from None


@tenacity.retry(
    stop=tenacity.stop_after_attempt(3),
    wait=tenacity.wait_fixed(2),
)
def get_auth_retry(session, username, password):
    global OCR
    session.cookies.clear()
    html_content = session.get(
        "https://authserver.nju.edu.cn/authserver/login?service=https%3A%2F%2Fchat.nju.edu.cn%2Fdeepseek%2F",
    ).text

    login_page = lxml.etree.HTML(html_content)
    lt = str(login_page.xpath('//*[@id="casLoginForm"]/input[@name="lt"]//@value')[0])
    dllt = "mobileLogin"
    execution = str(
        login_page.xpath('//*[@id="casLoginForm"]/input[@name="execution"]//@value')[0]
    )
    eventid = str(
        login_page.xpath('//*[@id="casLoginForm"]/input[@name="_eventId"]//@value')[0]
    )
    rmshown = str(
        login_page.xpath('//*[@id="casLoginForm"]/input[@name="rmShown"]//@value')[0]
    )
    salt = str(login_page.xpath('//*[@id="pwdDefaultEncryptSalt"]//@value')[0])

    session.get(
        f"https://authserver.nju.edu.cn/authserver/needCaptcha.html?username={username}&pwdEncrypt2=pwdEncryptSalt"
    )
    image = session.get(
        "https://authserver.nju.edu.cn/authserver/captcha.html",
    ).content

    if OCR is None:
        from . import ddddocr

        OCR = ddddocr.DdddOcr()
    captcha = OCR.classification(image)
    session.post(
        "https://authserver.nju.edu.cn/authserver/login?service=https%3A%2F%2Fchat.nju.edu.cn%2Fdeepseek%2F",
        data={
            "username": username,
            "password": encrypt(password, salt),
            "captchaResponse": captcha,
            "lt": lt,
            "dllt": dllt,
            "execution": execution,
            "_eventId": eventid,
            "rmShown": rmshown,
        },
    )
    if not validiate_cookies(session):
        raise ValueError
