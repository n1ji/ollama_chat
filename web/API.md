# Frontend <-> backend contract

The frontend (`web/frontend/`) and the backend (`web/server.py`) only talk through the three
endpoints below. Keep to them and either side can be replaced:

- **New frontend:** put an `index.html` (plus whatever else it needs) in a folder and run
  `python web/server.py --frontend path/to/folder`.
- **New backend:** serve the frontend's files and implement these endpoints. Nothing else is needed.

The server keeps no chat state. The frontend sends the whole conversation every time.

## `GET /api/models`

```json
{ "models": ["llama3.1:latest", "qwen3:8b"], "selected": "qwen3:8b", "error": null }
```

`selected` is the remembered model (or `null`). If Ollama can't be reached, `models` is `[]` and
`error` holds a message.

## `POST /api/model`

Remember the chosen model.

```json
{ "model": "qwen3:8b" }
```

Returns `{"ok": true}`, or `{"error": "..."}` with a 4xx/5xx status.

## `POST /api/chat`

```json
{ "model": "qwen3:8b", "messages": [ { "role": "user", "content": "hi" } ] }
```

`role` is `user`, `assistant` or `system`. The same list is what the desktop app saves as JSON.

Bad requests get a normal JSON error (`{"error": "..."}`, status 400). Otherwise the response is
`application/x-ndjson`: one JSON object per line, flushed as it is produced.

| line | meaning |
| --- | --- |
| `{"thinking": true}` | the model is thinking before it answers (sent at most once) |
| `{"content": "..."}` | the next piece of the answer, append it |
| `{"done": true}` | finished |
| `{"error": "..."}` | something went wrong, the stream ends |

Closing the connection (the Stop button) makes the server stop generating.

## Security

Requests whose `Host` is not `localhost`/`127.0.0.1`, or whose `Origin` doesn't match the `Host`,
are refused with 403, so other websites can't drive the server through your browser. Any backend
that listens on a network address should do the same or add a login.
