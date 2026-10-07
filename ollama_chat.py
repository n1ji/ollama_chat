import sys
import json
import threading
import tkinter as tk
from pathlib import Path
from tkinter import filedialog, messagebox, ttk
from ollama import chat, list as list_models

ROLE_COLORS = {"user": "lightblue", "assistant": "lightgreen"}
NO_MODEL_MESSAGE = "No model selected. Choose one from File → Choose Model."

model_file = Path.home() / "Documents" / "selected_model.txt"


def load_saved_model():
    try:
        return model_file.read_text(encoding="utf-8").strip() or None
    except OSError:
        return None


model = load_saved_model()
last_prompt = None
turn_start = 0  # index in conversation_history where the last prompt's turn begins
conversation_history = []
busy = False
dots_job = None
reply_bubble = None
reply_text = None
chooser_window = None


def post(func, *args):
    """Schedule func on the Tk main thread; safe to call from worker threads."""
    try:
        root.after(0, func, *args)
    except (RuntimeError, tk.TclError):
        pass  # window was closed while a request was running


def stream_reply(model_name, messages):
    """Runs in a worker thread. Never touches widgets or shared state directly."""
    try:
        full_response = ""
        for chunk in chat(model=model_name, messages=messages, stream=True):
            piece = chunk['message']['content']
            full_response += piece
            post(on_chunk, piece)
        post(on_done, full_response)
    except Exception as e:
        post(on_error, e)


def on_chunk(piece):
    at_bottom = output_canvas.yview()[1] >= 0.99
    reply_text.config(state="normal")
    reply_text.insert("end", piece)
    reply_text.config(state="disabled")
    fit_height(reply_text)
    if at_bottom:
        scroll_to_bottom()


def on_done(full_response):
    conversation_history.append({"role": "assistant", "content": full_response})
    set_busy(False)


def on_error(error):
    # Errors are shown but never stored, so they don't pollute the context or saved chats.
    del conversation_history[turn_start:]
    reply_bubble.destroy()
    add_message("Ollama", f"Error: {error}", "lightcoral", anchor="w")
    set_busy(False)


def start_request(prompt):
    global last_prompt, turn_start, reply_bubble, reply_text
    last_prompt = prompt
    turn_start = len(conversation_history)
    conversation_history.append({"role": "user", "content": prompt})
    add_message("User", prompt, "lightblue", anchor="e")
    reply_bubble, reply_text = add_message("Ollama", "", "lightgreen", anchor="w")
    set_busy(True)
    threading.Thread(target=stream_reply, args=(model, list(conversation_history)), daemon=True).start()


def set_busy(flag):
    global busy, dots_job
    busy = flag
    send_button.set_enabled(not flag)
    redo_button.set_enabled(not flag)
    if flag:
        animate_dots()
    else:
        if dots_job is not None:
            root.after_cancel(dots_job)
            dots_job = None
        status_label.config(text="")


def animate_dots(count=0):
    global dots_job
    status_label.config(text="Generating" + "." * (count % 3 + 1))
    dots_job = root.after(500, animate_dots, count + 1)


def send_prompt(event=None):
    if busy:
        return
    user_input = input_entry.get().strip()
    if not user_input:
        return
    if not model:
        add_message("Ollama", NO_MODEL_MESSAGE, "lightcoral", anchor="w")  # prompt stays in the box
        return
    input_entry.delete(0, tk.END)
    start_request(user_input)


def redo_response():
    if busy or not last_prompt:
        return
    if not model:
        add_message("Ollama", NO_MODEL_MESSAGE, "lightcoral", anchor="w")
        return
    del conversation_history[turn_start:]
    render_history()
    start_request(last_prompt)


def render_history():
    clear_chat_display()
    for msg in conversation_history:
        add_message(msg["role"].capitalize(), msg["content"],
                    ROLE_COLORS.get(msg["role"], "lightcoral"),
                    anchor="e" if msg["role"] == "user" else "w")


def valid_history(data):
    return isinstance(data, list) and all(
        isinstance(m, dict) and isinstance(m.get("role"), str) and isinstance(m.get("content"), str)
        for m in data
    )


def save_chat():
    filepath = filedialog.asksaveasfilename(defaultextension=".json", filetypes=[("JSON files", "*.json"), ("All files", "*.*")])
    if filepath:
        with open(filepath, "w", encoding="utf-8") as f:
            json.dump(conversation_history, f, ensure_ascii=False, indent=2)


def load_chat():
    global last_prompt, turn_start, conversation_history
    if busy:
        messagebox.showinfo("Busy", "Wait for the current response to finish.")
        return
    filepath = filedialog.askopenfilename(defaultextension=".json", filetypes=[("JSON files", "*.json"), ("All files", "*.*")])
    if not filepath:
        return
    try:
        with open(filepath, "r", encoding="utf-8") as f:
            data = json.load(f)
    except FileNotFoundError:
        messagebox.showerror("Error", "Chat file not found.")
        return
    except (json.JSONDecodeError, UnicodeDecodeError):
        messagebox.showerror("Error", "Invalid JSON file.")
        return
    if not valid_history(data):
        messagebox.showerror("Error", "Not a chat file: expected a list of messages with 'role' and 'content'.")
        return

    conversation_history = data
    render_history()
    # Redo regenerates the last exchange, even if the chat ends with an assistant message.
    last_prompt, turn_start = None, 0
    for i in range(len(conversation_history) - 1, -1, -1):
        if conversation_history[i]["role"] == "user":
            last_prompt, turn_start = conversation_history[i]["content"], i
            break


def update_title():
    root.title(f"O.C.GUI - {model}" if model else "O.C.GUI")


def apply_model(name):
    """Use this model right away and remember it for the next launch."""
    global model
    model = name
    update_title()
    try:
        model_file.write_text(name, encoding="utf-8")
    except OSError as e:
        messagebox.showerror("Error", f"Model changed, but it couldn't be remembered: {e}")


def installed_models():
    """Names of the models pulled in Ollama, or [] if Ollama can't be reached."""
    try:
        response = list_models()
        items = response["models"] if isinstance(response, dict) else response.models
        names = []
        for item in items:
            if isinstance(item, dict):
                names.append(item.get("model") or item.get("name"))
            else:
                names.append(item.model)
        return sorted(n for n in names if n)
    except Exception:
        return []


def model_chooser():
    global chooser_window
    if busy:
        messagebox.showinfo("Busy", "Wait for the current response to finish.")
        return
    if chooser_window is not None and chooser_window.winfo_exists():
        chooser_window.lift()
        chooser_window.focus_force()
        return

    custom_label = "custom..."
    models = installed_models()
    if model and model not in models:
        models.insert(0, model)
    models.append(custom_label)

    chooser = chooser_window = tk.Toplevel(root)
    chooser.title("Choose Model")
    chooser.resizable(False, False)
    body = tk.Frame(chooser, padx=16, pady=12)
    body.pack()

    if len(models) == 1:
        tk.Label(body, text="Couldn't list models. Is Ollama running?\nYou can still type a model name below.",
                 fg="gray30", justify="left").pack(anchor="w", pady=(0, 8))
    tk.Label(body, text="Select a model:").pack(anchor="w")
    selected = tk.StringVar(value=model if model else models[0])
    combo = ttk.Combobox(body, textvariable=selected, values=models, state="readonly", width=32)
    combo.pack(pady=(2, 8))

    custom_frame = tk.Frame(body)
    tk.Label(custom_frame, text="Custom model name:").pack(anchor="w")
    custom_entry = tk.Entry(custom_frame, width=34)
    custom_entry.pack(pady=(2, 8))

    def on_select(event=None):
        if selected.get() == custom_label:
            custom_frame.pack(before=button_row)
            custom_entry.focus_set()
        else:
            custom_frame.pack_forget()

    def confirm():
        name = custom_entry.get().strip() if selected.get() == custom_label else selected.get()
        if not name or name == custom_label:
            return
        apply_model(name)
        chooser.destroy()

    button_row = tk.Frame(body)
    button_row.pack()
    tk.Button(button_row, text="OK", command=confirm, width=10).pack(side=tk.LEFT, padx=4)
    tk.Button(button_row, text="Cancel", command=chooser.destroy, width=10).pack(side=tk.LEFT, padx=4)

    combo.bind("<<ComboboxSelected>>", on_select)
    chooser.bind("<Return>", lambda e: confirm())
    chooser.bind("<Escape>", lambda e: chooser.destroy())
    if selected.get() == custom_label:
        on_select()

    # Deliberately not modal (no grab_set/wait_window): a nested event loop started from a
    # menu callback can freeze Tk on macOS.
    chooser.transient(root)
    chooser.focus_force()


def save_responses():
    filepath = filedialog.asksaveasfilename(defaultextension=".txt", filetypes=[("Text files", "*.txt"), ("All files", "*.*")])
    if filepath:
        full_text = ""
        for item in conversation_history:
            full_text += f"{item['role'].capitalize()}: {item['content']}\n\n"
        with open(filepath, "w", encoding="utf-8") as f:
            f.write(full_text)


def clear_chat_display():
    for widget in output_frame.winfo_children():
        widget.destroy()


def scroll_to_bottom():
    root.update_idletasks()
    output_canvas.yview_moveto(1)


def fit_height(text):
    """Resize a read-only Text to exactly fit its wrapped content."""
    if text.winfo_width() <= 1:
        return
    count = text.count("1.0", "end", "displaylines")
    lines = max(count[0] if count else 1, 1)
    if int(text.cget("height")) != lines:
        text.config(height=lines)


def add_message(sender, message, bg_color, anchor="w"):
    """Add a chat bubble. Its width follows the window and its text is selectable."""
    bubble = tk.Frame(output_frame, bg=bg_color, padx=10, pady=6)
    bubble.pack(fill="x", padx=(80, 8) if anchor == "e" else (8, 80), pady=4)

    tk.Label(bubble, text=f"{sender}:", bg=bg_color, fg="black",
             font=("TkDefaultFont", 10, "bold")).pack(anchor="w")

    text = tk.Text(bubble, wrap="word", width=1, height=1, bg=bg_color, fg="black",
                   relief="flat", borderwidth=0, highlightthickness=0, padx=0, pady=0,
                   font=("TkDefaultFont", 10), cursor="xterm")
    text.insert("1.0", message)
    text.config(state="disabled")
    text.pack(fill="x")
    text.bind("<Configure>", lambda e: fit_height(text))
    text.bind("<Button-1>", lambda e: text.focus_set())

    scroll_to_bottom()
    return bubble, text


def on_mousewheel(event):
    if event.num == 4:
        units = -3
    elif event.num == 5:
        units = 3
    elif sys.platform == "darwin":
        units = -event.delta
    else:
        units = -int(event.delta / 120) * 3
    output_canvas.yview_scroll(units, "units")


def create_round_rectangle(canvas, x1, y1, x2, y2, radius, **kwargs):
    """Create a rounded rectangle on a Tkinter canvas."""
    points = [
        (x1 + radius, y1), (x2 - radius, y1),
        (x2, y1), (x2, y1 + radius),
        (x2, y2 - radius), (x2, y2),
        (x2 - radius, y2), (x1 + radius, y2),
        (x1, y2), (x1, y2 - radius),
        (x1, y1 + radius), (x1, y1),
    ]
    return canvas.create_polygon(points, smooth=True, **kwargs)


class RoundButton(tk.Frame):
    def __init__(self, parent, text, command, radius=15, width=80, height=30, bg="lightblue", fg="black",
                 font=("TkDefaultFont", 10)):
        super().__init__(parent, width=width, height=height)
        self.pack_propagate(False)
        self._command = command
        self._bg = bg
        self._fg = fg
        self._enabled = True

        self._canvas = tk.Canvas(self, width=width, height=height, bg=parent.cget("bg"), highlightthickness=0)
        self._shape = create_round_rectangle(self._canvas, 0, 0, width, height, radius, fill=bg)
        self._canvas.pack(fill="both", expand=True)

        self._label = tk.Label(self._canvas, text=text, font=font, bg=bg, fg=fg)
        self._label.place(relx=0.5, rely=0.5, anchor="center")

        self._canvas.bind("<Button-1>", self._click)
        self._label.bind("<Button-1>", self._click)

    def _click(self, event):
        if self._enabled:
            self._command()

    def set_enabled(self, enabled):
        self._enabled = enabled
        bg = self._bg if enabled else "lightgray"
        self._canvas.itemconfigure(self._shape, fill=bg)
        self._label.config(bg=bg, fg=self._fg if enabled else "gray")


root = tk.Tk()
update_title()
root.geometry("640x720")
root.minsize(360, 300)

menubar = tk.Menu(root)
file_menu = tk.Menu(menubar, tearoff=0)
file_menu.add_command(label="Load Chat", command=load_chat)
file_menu.add_command(label="Save Chat State", command=save_chat)
file_menu.add_command(label="Choose Model", command=lambda: root.after(10, model_chooser))
file_menu.add_separator()
file_menu.add_command(label="Save Responses (Legacy)", command=save_responses)
file_menu.add_separator()
file_menu.add_command(label="Exit", command=root.destroy)
menubar.add_cascade(label="File", menu=file_menu)
root.config(menu=menubar)

# Bottom controls are packed first so they are never squeezed out by the chat area.
bottom_frame = tk.Frame(root)
bottom_frame.pack(side=tk.BOTTOM, fill=tk.X, padx=8, pady=6)

status_label = tk.Label(bottom_frame, text="", font=("TkDefaultFont", 10, "bold"), anchor="w")
status_label.pack(fill=tk.X)

input_row = tk.Frame(bottom_frame)
input_row.pack(fill=tk.X, pady=(4, 0))

input_entry = tk.Entry(input_row)
input_entry.pack(side=tk.LEFT, fill=tk.X, expand=True, padx=(0, 8), ipady=4)
input_entry.bind("<Return>", send_prompt)
input_entry.focus_set()

send_button = RoundButton(input_row, "Send", send_prompt)
send_button.pack(side=tk.LEFT, padx=2)

redo_button = RoundButton(input_row, "Redo", redo_response, bg="lightgreen")
redo_button.pack(side=tk.LEFT, padx=2)

save_button = RoundButton(input_row, "Save Chat", save_chat, width=90)
save_button.pack(side=tk.LEFT, padx=2)

chat_area = tk.Frame(root)
chat_area.pack(side=tk.TOP, fill=tk.BOTH, expand=True)

output_scroll = tk.Scrollbar(chat_area)
output_scroll.pack(side=tk.RIGHT, fill=tk.Y)

output_canvas = tk.Canvas(chat_area, yscrollcommand=output_scroll.set, highlightthickness=0)
output_canvas.pack(side=tk.LEFT, fill=tk.BOTH, expand=True)
output_scroll.config(command=output_canvas.yview)

output_frame = tk.Frame(output_canvas)
output_window = output_canvas.create_window((0, 0), window=output_frame, anchor=tk.NW)

# Keep the message column as wide as the canvas so bubbles resize with the window.
output_canvas.bind("<Configure>", lambda e: output_canvas.itemconfigure(output_window, width=e.width))
output_frame.bind("<Configure>", lambda e: output_canvas.configure(scrollregion=output_canvas.bbox("all")))

root.bind_all("<MouseWheel>", on_mousewheel)
root.bind_all("<Button-4>", on_mousewheel)
root.bind_all("<Button-5>", on_mousewheel)

root.mainloop()
