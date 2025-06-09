from . import utils

import http.cookiejar
import logging
import requests
import socketio
import time
import urllib.parse


class NoExpirePolicy(http.cookiejar.DefaultCookiePolicy):
    def __init__(self):
        super().__init__()

    def return_ok_expires(self, cookie, request):
        return True


class Chat:
    def __init__(
        self,
        username: str,
        password: str,
        cookie_file=None,
        logger: logging.Logger = logging.getLogger(),
    ):
        self.session = requests.Session()
        if cookie_file is not None:
            self.session.cookies = http.cookiejar.MozillaCookieJar(
                policy=NoExpirePolicy(),
            )
            try:
                self.session.cookies.load(
                    cookie_file,
                    ignore_discard=True,
                    ignore_expires=True,
                )
            except Exception:
                logger.info("Cookie file corrupted")

        utils.get_auth(self.session, username, password)
        if cookie_file is not None:
            self.session.cookies.save(
                filename=cookie_file,
                ignore_discard=True,
                ignore_expires=True,
            )
        self.sio = socketio.SimpleClient(
            handle_sigint=False,
            logger=logger,
            engineio_logger=logger,
        )

    def __enter__(self):
        return self

    def __exit__(self, *args):
        self.sio.disconnect()
        self.session.__exit__(*args)

    def available_agents(self):
        response = self.session.post(
            "https://chat.nju.edu.cn/deepseek/ai/aiObjList",
        ).json()

        return [
            agent["name"]
            for agent in response["data"]
            if agent["urlGenerator"] == "gendialUrlGenerator"
        ]

    def connect_to_agent(self, name):
        response = self.session.post(
            "https://chat.nju.edu.cn/deepseek/ai/aiObjList",
        ).json()

        agent = None
        for candidate_agent in response["data"]:
            if candidate_agent["name"] == name:
                if candidate_agent["urlGenerator"] != "gendialUrlGenerator":
                    raise ValueError(f"Agent '{name}' is unsupported")
                agent = candidate_agent
                break
        if agent is None:
            raise ValueError(f"Agent '{name}' not found")

        self.agent_id = agent["id"]
        url = self.session.post(
            "https://chat.nju.edu.cn/deepseek/ai/aiObjUrl",
            data={"id": self.agent_id, "urlGenerator": agent["urlGenerator"]},
        ).json()["data"]

        query = urllib.parse.urlsplit(urllib.parse.urlsplit(url).fragment).query
        auth = {
            "debugMode": False,
            "agentId": self.agent_id,
            "debug": False,
        } | {k: v[0] for k, v in urllib.parse.parse_qs(query).items()}

        self.sio.connect(
            "https://ds.nju.edu.cn/socket.io",
            auth=auth,
        )

    def new_dialogue(self):
        self.sio.emit(
            "chat",
            data={
                "agentId": self.agent_id,
                "memoryId": "",
                # "history": ...,
            },
        )
        response = self.sio.receive()  # first response always have only 1 token
        self.memory_id = response[-1]["memoryId"]
        self.dialogue_content = list()

    def send_msg(self, msg):
        self.dialogue_content.append(
            {
                "timestamp": time.strftime("%Y-%m-%d %H:%M:%S"),
                "role": "user",
                "content": msg,
            }
        )
        self.sio.emit(
            "chat",
            data={
                "agentId": self.agent_id,
                "msg": msg,
                "memoryId": self.memory_id,
            },
        )

    def iter_response(self):
        agent_msg = ""
        response_end = False
        interrupted = False
        while not response_end:
            try:
                response = self.sio.receive()[-1]
                response_end = response.get("streamingEnd", False)
                for msg in response["msgs"]:
                    agent_msg += msg["msg"]
                    yield msg["msg"]

            except KeyboardInterrupt:
                self.sio.emit("stop-gen")
                interrupted = True

        if interrupted:
            agent_msg += "^C"

        self.dialogue_content.append(
            {
                "timestamp": time.strftime("%Y-%m-%d %H:%M:%S"),
                "role": "agent",
                "content": agent_msg,
            }
        )
