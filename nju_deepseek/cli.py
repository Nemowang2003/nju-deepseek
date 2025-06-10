try:
    import platformdirs
    from prompt_toolkit import PromptSession
    from prompt_toolkit.completion import Completer, Completion
    from prompt_toolkit.history import InMemoryHistory
    from prompt_toolkit.key_binding import KeyBindings, KeyPressEvent
except ImportError:
    raise ModuleNotFoundError(
        "run `pip install 'nju-deepseek[cli]'` to install missing dependencies"
    ) from None

from . import Chat

import collections
import json
import logging
import os
import subprocess
import tempfile
from typing import Callable, NamedTuple


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
    PASSWORD = getpass.getpass("Password: ")
    CONFIG_DIR.mkdir(exist_ok=True)
    with CONFIG_FILE.open(mode="w", encoding="utf-8") as fp:
        json.dump({"username": USERNAME, "password": PASSWORD}, fp)
else:
    with CONFIG_FILE.open(mode="r", encoding="utf-8") as fp:
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


file_handler = logging.FileHandler(filename=LOG_FILE, mode="a", encoding="utf-8")
file_handler.setLevel(logging.DEBUG)
file_handler.setFormatter(
    logging.Formatter(
        fmt="[%(asctime)s] %(message)s",
        datefmt="%Y-%m-%d %H:%M:%S",
    )
)
recent_handler = RecentHandler(file_handler)
LOGGER.addHandler(recent_handler)

key_bindings = KeyBindings()


@key_bindings.add("c-o")
def invoke_editor(event: KeyPressEvent):
    buffer = event.current_buffer

    editor = os.environ.get("EDITOR", "vim")
    with tempfile.NamedTemporaryFile(mode="w", encoding="utf-8", delete=False) as file:
        path = file.name
        file.write(buffer.text)
    try:
        subprocess.run([editor, path])
        with open(file=path, mode="r", encoding="utf-8") as f:
            content = f.read().strip()
        buffer.text = content
        buffer.cursor_position = len(buffer.text)
    except Exception as e:
        print(f"[An error occured when invoking editor: {e}]")
    finally:
        os.unlink(path)


class CommandEntry(NamedTuple):
    func: Callable[["Console", list[str]], None]
    args: str
    description: str


class DotCommandCompleter(Completer):
    def __init__(self, commands: dict[str, CommandEntry]):
        self.commands = commands

    def get_completions(self, document, complete_event):
        text = document.text_before_cursor.strip()
        if not text.startswith("."):
            return
        for command, entry in self.commands.items():
            if command.startswith(text):
                yield Completion(
                    command + " ",
                    start_position=-len(text),
                    display_meta=entry.description,
                )


class Console:
    def __init__(self) -> None:
        self.running = True
        self.chat: Chat = Chat(USERNAME, PASSWORD, COOKIE_FILE, LOGGER)
        self.commands: dict[str, CommandEntry] = dict()
        self.session = PromptSession(
            completer=DotCommandCompleter(self.commands),
            complete_in_thread=True,
            history=InMemoryHistory(),
            key_bindings=key_bindings,
        )

    def register_command(self, name: str, *, args: str = "", description: str = ""):
        def inner(func):
            self.commands["." + name] = CommandEntry(func, args, description)
            return func

        return inner

    def interactive(self, initial_agent: str = "DeepSeek-R1-32B"):
        self.chat.connect_to_agent(initial_agent)
        self.chat.new_dialogue()
        print("Type '.help' for help information.")
        while self.running:
            try:
                user_msg: str = self.session.prompt(">>> ").strip()
                if user_msg.startswith("."):
                    split = user_msg.split()
                    command, args = split[0], split[1:]
                    entry = self.commands.get(command)
                    if entry is None:
                        print("[Unknown command]")
                    else:
                        entry.func(self, args)
                elif user_msg:  # not send user_msg when it's empty
                    self.chat.send_msg(user_msg)
                    for token in self.chat.iter_response():
                        print(token, end="", flush=True)
            except KeyboardInterrupt:
                pass
            except EOFError:
                break
            print()

    def __enter__(self):
        return self

    def __exit__(self, *args):
        self.chat.__exit__(*args)


console = Console()


@console.register_command("help", description="show help message")
def help_command(console: Console, args: list[str]):
    for command, entry in sorted(console.commands.items()):
        print(f"{' '.join([command, entry.args]): <30}{entry.description}")
    print(
        "",
        "Press Ctrl+O to open an editor ($EDITOR, default to vim) to edit the input buffer.",
        "Send SIGINT (Ctrl+C) to interrupt the response or abort current input buffer.",
        "Send EOF (Ctrl+D) to exit the repl.",
        sep="\n",
    )


@console.register_command(
    "export",
    args="[filename]",
    description="export dialogue to file",
)
def export_command(console: Console, args: list[str]):
    filename = args[0] if args else console.chat.memory_id
    with (DIALOGUE_DIR / f"{filename}.md").open(mode="w", encoding="utf-8") as fp:
        fp.write("## " + console.chat.memory_id + "\n\n")
        for msg in console.chat.dialogue_content:
            fp.write("**" + msg["timestamp"] + "**\n\n")
            if msg["role"] == "user":
                fp.write("> ")
            fp.write(msg["content"])
            fp.write("\n\n")
    print(f"[Successfully saved to {DIALOGUE_DIR}/{filename}.md]")


@console.register_command("exit", description="exit the repl")
def exit_command(console: Console, args: list[str]):
    console.running = False


def main():
    console.interactive()
