"""Web UI for Ollama: this file is the backend, index.html is the frontend.

    python web/server.py

The server keeps no conversation state. The browser sends the whole chat with every
request, so saved chats are the same JSON the desktop app uses.
"""
import argparse
import json
import mimetypes
import sys
import threading
import webbrowser
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from urllib.parse import unquote, urlparse

from ollama import chat, list as list_models

HERE = Path(__file__).parent
FRONTEND_DIR = HERE / "frontend"  # any folder with an index.html works, see --frontend
MODEL_FILE = Path.home() / "Documents" / "selected_model.txt"  # shared with the desktop app
MAX_CONTEXT_MESSAGES = 40
MAX_BODY_BYTES = 20 * 1024 * 1024
LOCAL_HOSTS = {"localhost", "127.0.0.1", "[::1]"}

restrict_to_local = True  # turned off by --host so a LAN address still works


def load_saved_model():
    try:
        return MODEL_FILE.read_text(encoding="utf-8").strip() or None
    except OSError:
        return None


def save_model(name):
    MODEL_FILE.parent.mkdir(parents=True, exist_ok=True)
    MODEL_FILE.write_text(name, encoding="utf-8")


def installed_models():
    """Names of the models pulled in Ollama. Raises if Ollama can't be reached."""
    response = list_models()
    items = response["models"] if isinstance(response, dict) else response.models
    names = []
    for item in items:
        if isinstance(item, dict):
            names.append(item.get("model") or item.get("name"))
        else:
            names.append(item.model)
    return sorted(n for n in names if n)


def recent_context(history):
    """The last MAX_CONTEXT_MESSAGES messages, starting on a user message."""
    recent = history[-MAX_CONTEXT_MESSAGES:]
    while len(recent) > 1 and recent[0]["role"] != "user":
        recent = recent[1:]
    return recent


def valid_messages(messages):
    return (
        isinstance(messages, list)
        and len(messages) > 0
        and all(
            isinstance(m, dict)
            and m.get("role") in ("user", "assistant", "system")
            and isinstance(m.get("content"), str)
            for m in messages
        )
    )


class Handler(BaseHTTPRequestHandler):
    server_version = "OllamaWeb"

    def log_message(self, fmt, *args):
        pass  # keep the terminal quiet

    # --- helpers -------------------------------------------------------------

    def send_json(self, status, payload):
        body = json.dumps(payload).encode("utf-8")
        self.send_response(status)
        self.send_header("Content-Type", "application/json; charset=utf-8")
        self.send_header("Content-Length", str(len(body)))
        self.send_header("Cache-Control", "no-store")
        self.end_headers()
        self.wfile.write(body)

    def request_allowed(self):
        """Block other websites from driving the local server (DNS rebinding / cross-site posts)."""
        host = self.headers.get("Host", "")
        if restrict_to_local and host.rsplit(":", 1)[0] not in LOCAL_HOSTS:
            return False
        origin = self.headers.get("Origin")
        if origin and urlparse(origin).netloc != host:
            return False
        return True

    def read_json(self):
        try:
            length = int(self.headers.get("Content-Length", "0"))
        except ValueError:
            return None
        if length <= 0 or length > MAX_BODY_BYTES:
            return None
        try:
            return json.loads(self.rfile.read(length).decode("utf-8"))
        except (ValueError, UnicodeDecodeError):
            return None

    # --- routes --------------------------------------------------------------

    def do_GET(self):
        if not self.request_allowed():
            return self.send_json(403, {"error": "Forbidden"})
        path = urlparse(self.path).path
        if path == "/api/models":
            try:
                models = installed_models()
                error = None
            except Exception as e:
                models, error = [], f"Couldn't reach Ollama: {e}"
            self.send_json(200, {"models": models, "selected": load_saved_model(), "error": error})
        elif path.startswith("/api/"):
            self.send_json(404, {"error": "Not found"})
        else:
            self.serve_static(path)

    def serve_static(self, path):
        """Serve the frontend folder. Anything outside it is a 404."""
        rel = "index.html" if path == "/" else unquote(path).lstrip("/")
        root = FRONTEND_DIR.resolve()
        try:
            target = (root / rel).resolve()
        except (ValueError, OSError):
            return self.send_json(404, {"error": "Not found"})
        if root not in target.parents or not target.is_file():
            return self.send_json(404, {"error": "Not found"})
        content_type = mimetypes.guess_type(target.name)[0] or "application/octet-stream"
        if content_type.startswith("text/") or content_type in ("application/javascript", "application/json"):
            content_type += "; charset=utf-8"
        body = target.read_bytes()
        self.send_response(200)
        self.send_header("Content-Type", content_type)
        self.send_header("Content-Length", str(len(body)))
        self.send_header("Cache-Control", "no-store")
        self.end_headers()
        self.wfile.write(body)

    def do_POST(self):
        if not self.request_allowed():
            return self.send_json(403, {"error": "Forbidden"})
        path = urlparse(self.path).path
        data = self.read_json()
        if not isinstance(data, dict):
            return self.send_json(400, {"error": "Expected a JSON object"})

        if path == "/api/model":
            name = data.get("model")
            if not isinstance(name, str) or not name.strip():
                return self.send_json(400, {"error": "Missing model name"})
            try:
                save_model(name.strip())
            except OSError as e:
                return self.send_json(500, {"error": f"Couldn't remember the model: {e}"})
            return self.send_json(200, {"ok": True})

        if path == "/api/chat":
            return self.stream_chat(data)

        self.send_json(404, {"error": "Not found"})

    def stream_chat(self, data):
        model = data.get("model")
        messages = data.get("messages")
        if not isinstance(model, str) or not model.strip():
            return self.send_json(400, {"error": "No model selected"})
        if not valid_messages(messages):
            return self.send_json(400, {"error": "Expected a list of messages with 'role' and 'content'"})

        # One JSON object per line, flushed as it is produced (the connection closes at the end).
        self.send_response(200)
        self.send_header("Content-Type", "application/x-ndjson; charset=utf-8")
        self.send_header("Cache-Control", "no-store")
        self.end_headers()

        def emit(obj):
            self.wfile.write(json.dumps(obj).encode("utf-8") + b"\n")
            self.wfile.flush()

        stream = None
        said_thinking = False
        try:
            stream = chat(model=model.strip(), messages=recent_context(messages), stream=True)
            for chunk in stream:
                message = chunk["message"]
                thinking = message.get("thinking") if hasattr(message, "get") else None
                if message["content"]:
                    emit({"content": message["content"]})
                elif thinking and not said_thinking:
                    said_thinking = True  # once is enough; the page just shows "thinking..."
                    emit({"thinking": True})
            emit({"done": True})
        except (BrokenPipeError, ConnectionResetError):
            pass  # the browser pressed Stop or closed the tab
        except Exception as e:
            try:
                emit({"error": str(e)})
            except OSError:
                pass
        finally:
            if stream is not None and hasattr(stream, "close"):
                stream.close()  # stop generating if the client went away


def main():
    global restrict_to_local, FRONTEND_DIR
    parser = argparse.ArgumentParser(description="Web UI for Ollama")
    parser.add_argument("--host", default="127.0.0.1",
                        help="address to listen on (default: 127.0.0.1, this computer only)")
    parser.add_argument("--port", type=int, default=8765)
    parser.add_argument("--frontend", type=Path, default=FRONTEND_DIR,
                        help="folder with the frontend to serve (default: web/frontend)")
    parser.add_argument("--no-browser", action="store_true", help="don't open the browser automatically")
    args = parser.parse_args()

    FRONTEND_DIR = args.frontend
    if not (FRONTEND_DIR / "index.html").is_file():
        sys.exit(f"No index.html in {FRONTEND_DIR}")

    if args.host not in ("127.0.0.1", "localhost", "::1"):
        restrict_to_local = False
        print("Warning: anyone who can reach this address can use your Ollama. There is no login.")

    server = ThreadingHTTPServer((args.host, args.port), Handler)
    server.daemon_threads = True
    url = f"http://{'localhost' if args.host == '127.0.0.1' else args.host}:{args.port}"
    print(f"Ollama web UI running at {url}  (Ctrl+C to stop)")
    if not args.no_browser:
        threading.Timer(0.5, webbrowser.open, args=(url,)).start()
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        print("\nStopped.")


if __name__ == "__main__":
    main()
