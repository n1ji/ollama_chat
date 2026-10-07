# Ollama Chat

A small desktop chat window for talking to a local [Ollama](https://ollama.com) model. It runs fully offline and needs no Docker, no Open WebUI and no installation, just Python and Ollama.

> **Work in progress.** Expect bugs.

## Features

- Chat with a local model through a simple Tkinter window; replies stream in as they are generated
- Pick any model you have pulled from **File → Choose Model** (or type a custom name). The choice applies immediately and is remembered in `Documents/selected_model.txt`
- Conversation history is kept, so the model remembers earlier messages (the most recent 40 messages are sent to the model)
- **Redo** button to regenerate the last answer
- **Save Chat State** (button or File menu) saves the whole conversation as JSON, and **File → Load Chat** continues it later
- **File → Save Responses (Legacy)** exports the conversation as plain text
- Message text can be selected and copied, Enter sends, and the window is resizable

## Requirements

- Python 3 with Tkinter (included with the standard Python installers; on some Linux distributions install `python3-tk`)
- [Ollama](https://ollama.com/download) installed and running
- The `ollama` Python package:

  ```bash
  pip install ollama
  ```

- At least one model pulled, for example:

  ```bash
  ollama pull llama3.1
  ```

## Usage

```bash
python ollama_chat.py
```

Type a prompt, press **Send** (or Enter), and watch the answer stream in.

## Choosing a model

On first launch no model is selected. Open **File → Choose Model**, pick one of your installed models and press OK. If the list is empty, make sure Ollama is running, or pick `custom...` and type the model name.

## Web UI (experimental)

The `web/` folder has a browser version of the same chat, split into a backend and a frontend:

- `web/server.py` is the backend (Python standard library plus the `ollama` package)
- `web/frontend/` is the frontend (plain HTML, CSS and JS, no build step)

```bash
python web/server.py
```

It opens http://localhost:8765 in your browser. Same features as the desktop app (model picker, streaming, Redo, save/load chat, and saved chats use the same JSON), plus a Stop button. The look is a Liquid Glass style that follows light/dark mode, and the half-circle button in the toolbar has a Clear to Tinted slider for the glass.

Because the two sides only talk through three endpoints (written down in [`web/API.md`](web/API.md)), either one can be swapped:

- another frontend: `python web/server.py --frontend path/to/folder` (any folder with an `index.html`)
- another backend: serve the frontend files and implement the endpoints in `web/API.md`

Other options: `--port 9000` changes the port and `--no-browser` stops it from opening a tab.

It only listens on your own computer. `--host 0.0.0.0` makes it reachable from other devices, but there is no login, so anyone on your network could use your Ollama. This is early and can be buggy.

## Issues

Found a bug? Open an [issue](https://github.com/n1ji/ollama_chat/issues).

Made by n1ji (plaui).
