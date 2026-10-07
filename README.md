# Ollama Chat

A small desktop chat window for talking to a local [Ollama](https://ollama.com) model. It runs fully offline and needs no Docker, no Open WebUI and no installation, just Python and Ollama.

> **Work in progress.** Expect bugs.

## Features

- Chat with a local model through a simple Tkinter window
- Conversation history is kept, so the model remembers earlier messages
- **Redo** button to regenerate the last answer
- **Save Chat State** button to save the whole conversation as JSON, and **File → Load Chat** to continue it later
- **File → Save Responses (Legacy)** to export the conversation as plain text

## Requirements

- Python 3 with Tkinter (included with the standard Python installers; on some Linux distributions install `python3-tk`)
- [Ollama](https://ollama.com/download) installed and running
- The `ollama` Python package:

  ```bash
  pip install ollama
  ```

- The model the app uses (`llama3.1` by default):

  ```bash
  ollama pull llama3.1
  ```

## Usage

```bash
python ollama_chat.py
```

Type a prompt, press **Send**, and wait for the answer.

## Using a different model

The model name is set in `run_ollama_chat` in `ollama_chat.py` (`model='llama3.1'`). Change it to any model you have pulled with Ollama.

## Issues

Found a bug? Open an [issue](https://github.com/n1ji/ollama_chat/issues).

Made by n1ji (plaui).
