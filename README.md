# nju-deepseek

A Python package for accessing agents listed on https://chat.nju.edu.cn/deepseek via command-line interface.


## Table of Contents
- [Installation](#installation)
- [Usage](#usage)
- [Features](#features)
- [Todo](#todo)
- [Dependencies](#dependencies)
- [Home Page](#home-page)
- [License](#license)


## Installation
```bash
pip install nju-deepseek
# For available cli (optional)
pip install 'nju-deepseek[cli]'
```


## Usage

### Command-Line Interface
The package provides a CLI tool named `chat` for interactive conversations:

```bash
chat
```

Or access by running module directly:

```bash
python3 -m nju_deepseek
```


### Programmatic Usage
Import the `Chat` class from `nju_deepseek` for custom applications:

```python
from nju_deepseek import Chat

with Chat('username', 'password', 'cookiefile') as chat:
    for agent in chat.available_agents():
        print(agent)
    chat.connect_to_agent('QwQ-32B')
    chat.new_dialogue()
    chat.send_msg('hello!')
    for token in chat.iter_response():
        print(token, end='', flush=True)
```


## Features
- Fully Automated Authentication
   - [nju-login](https://github.com/SuperKenVery/nju-login) is copied to this project for authentication.
   - [ddddocr 1.0.6](https://github.com/sml2h3/ddddocr) is copied to this project for captcha recognization.
- Cookie Persistence
- Markdown Export

## Todo

- Support recovering from dialogues.
- Handle reconnection better.
- Support more agents.


## Dependencies
- **Authentication**
  - lxml
  - onnxruntime
  - pillow
  - pycryptodomex
  - requests
  - tenacity

- **Chat Session**
  - python-socketio[client]
  - websocket-client
  
- **Config and Cache File Placement**:
  - platformdirs

- **REPL**
  - prompt-toolkit


## Home Page
Project URL: [https://github.com/Nemowang2003/nju-deepseek](https://github.com/Nemowang2003/nju-deepseek)

Contributions are welcome, as I will be leaving NJU soon.


## License
This project is licensed under the MIT License.
