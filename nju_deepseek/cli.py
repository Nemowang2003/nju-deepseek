from nju_deepseek import Chat

import collections
import json
import logging
import os
import platformdirs
import subprocess
import sys
import tempfile

try:
    import readline  # noqa
except Exception:
    pass

if not sys.stdin.isatty():
    print(
        "Error: This module is designed to be used in an interactive console, aborting...",
        file=sys.stderr,
    )
    exit(1)

CACHE_DIR = platformdirs.user_cache_path("nju-deepseek")
CACHE_DIR.mkdir(exist_ok=True)

DIALOGUE_DIR = CACHE_DIR / "dialogues"
DIALOGUE_DIR.mkdir(exist_ok=True)

COOKIE_FILE = CACHE_DIR / "cookies.txt"

LOG_FILE = CACHE_DIR / "nju-deepseek.log"

CONFIG_DIR = platformdirs.user_config_path("nju-deepseek")

CONFIG_FILE = CONFIG_DIR / "config.json"

if not CONFIG_FILE.exists():
    import getpass

    USERNAME = input("Username: ")
    PASSWORD = getpass.getpass()
    CONFIG_DIR.mkdir(exist_ok=True)
    with CONFIG_FILE.open("w") as fp:
        json.dump({"username": USERNAME, "password": PASSWORD}, fp)
else:
    with CONFIG_FILE.open() as fp:
        data = json.load(fp)
    USERNAME = data["username"]
    PASSWORD = data["password"]


LOGGER = logging.getLogger()
LOGGER.setLevel(logging.DEBUG)

stderr_handler = logging.StreamHandler()
stderr_handler.setLevel(logging.WARNING)
stderr_handler.setFormatter(logging.Formatter("%(levelname)s: %(message)s"))
LOGGER.addHandler(stderr_handler)


class RecentHandler(logging.Handler):
    def __init__(self, file_handler, buffer_size=20):
        super().__init__()
        self.buffer = collections.deque(maxlen=buffer_size)
        self.file_handler = file_handler

    def emit(self, record: logging.LogRecord):
        self.buffer.append(record)
        if record.levelno >= logging.WARNING:
            self.flush()

    def flush(self):
        while self.buffer:
            record = self.buffer.popleft()
            self.file_handler.handle(record)


file_handler = logging.FileHandler(LOG_FILE, mode="w", encoding="utf-8")
file_handler.setLevel(logging.DEBUG)
file_handler.setFormatter(
    logging.Formatter(
        fmt="[%(asctime)s] %(message)s",
        datefmt="%Y-%m-%d %H:%M:%S",
    )
)
recent_handler = RecentHandler(file_handler)
LOGGER.addHandler(recent_handler)


def editor(user_msg: str, chat: Chat):
    if user_msg != ".editor":
        return False
    editor = os.environ.get("EDITOR", "vim")
    with tempfile.NamedTemporaryFile(delete=False) as file:
        path = file.name
    try:
        subprocess.run([editor, path])
        with open(path) as f:
            user_msg = f.read().strip()
            if user_msg:
                print(">>> " + user_msg)
                chat.send_msg(user_msg)
                for token in chat.iter_response():
                    print(token, end="", flush=True)
            else:
                print("[Editor exited without content]", file=sys.stderr)
    except Exception:
        print("[Error when trying to open $EDITOR]", file=sys.stderr)
    finally:
        os.unlink(path)
    return True


def _exit(user_msg: str, _: Chat):
    if user_msg != ".exit":
        return False
    exit(0)


def export(user_msg: str, chat: Chat):
    if user_msg == ".export":
        path = chat.memory_id
    elif user_msg.startswith(".export "):
        path = user_msg[len(".export ") :]
    else:
        return False
    with (DIALOGUE_DIR / f"{path}.md").open("w") as fp:
        fp.write("## " + chat.memory_id + "\n\n")
        for msg in chat.dialogue_content:
            fp.write("**" + msg["timestamp"] + "**\n\n")
            if msg["role"] == "user":
                fp.write("> ")
            fp.write(msg["content"])
            fp.write("\n\n")
    print(f"[Successfully saved to {DIALOGUE_DIR}/{path}.md]")
    return True


def _help(user_msg: str, _: Chat):
    if user_msg == ".help":
        for name, __, description in COMMANDS:
            print(f"  {name:<10} - {description}", file=sys.stderr)
        return True
    return False


COMMANDS = {
    (
        ".editor",
        editor,
        "open $EDITOR as external editor",
    ),
    (
        ".exit",
        _exit,
        "exit interactive console",
    ),
    (
        ".export",
        export,
        "export dialogue as .md file",
    ),
    (
        ".help",
        _help,
        "show help for commands",
    ),
}

try:
    from prompt_toolkit import PromptSession
    from prompt_toolkit.completion import Completer, Completion
    from prompt_toolkit.history import InMemoryHistory

    class DotCommandCompleter(Completer):
        def get_completions(self, document, complete_event):
            text = document.text_before_cursor.strip()
            if text.startswith("."):
                for name, _, description in COMMANDS:
                    if name.startswith(text):
                        yield Completion(
                            name + " ",
                            start_position=-len(text),
                            display_meta=description,
                        )

    session = PromptSession(
        completer=DotCommandCompleter(),
        history=InMemoryHistory(),
        complete_in_thread=True,
    )

    get_input = session.prompt

except ImportError:
    print(
        "Warning: Completion is not enabled as 'prompt-toolkit' is not installed.",
        file=sys.stderr,
    )
    get_input = input


def main():
    with Chat(USERNAME, PASSWORD, COOKIE_FILE, LOGGER) as chat:
        chat.connect_to_agent("DeepSeek-R1-32B")
        chat.new_dialogue()
        print("Note: type '.help' to get help for commands.")
        while True:
            try:
                user_msg = get_input(">>> ").strip()
                for _, func, _ in COMMANDS:
                    if func(user_msg, chat):
                        break
                else:
                    if user_msg.startswith("."):
                        print("[Error: Unknown command]", file=sys.stderr)
                    else:
                        chat.send_msg(user_msg)
                        for token in chat.iter_response():
                            print(token, end="", flush=True)
            except KeyboardInterrupt:
                print(file=sys.stderr)
                continue
            except EOFError:
                break
