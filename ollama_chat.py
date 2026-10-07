import tkinter as tk
import tkinter.font as tkFont
from tkinter import scrolledtext, filedialog, ttk
import threading
import time
import json
from ollama import chat

last_prompt = None
conversation_history = []

def run_ollama_chat(user_input, output_frame, responses, dots_label):
    global last_prompt, conversation_history
    last_prompt = user_input
    conversation_history.append({"role": "user", "content": user_input})

    try:
        stream = chat(
            model='llama3.1',
            messages=conversation_history,
            stream=True,
        )

        full_response = ""
        for chunk in stream:
            content = chunk['message']['content']
            full_response += content

        dots_label.config(text="")
        
        def update_gui():
            add_message(output_frame, "Ollama", full_response, "lightgreen", anchor="w")
        root.after(0, update_gui)

        conversation_history.append({"role": "assistant", "content": full_response})
        responses.append(f"User: {user_input}\nOllama: {full_response}\n\n")

    except Exception as e:
        dots_label.config(text="")
        
        def update_gui_error():
            add_message(output_frame, "Ollama", f"Error: {e}", "lightcoral", anchor="w")
        root.after(0, update_gui_error)

        conversation_history.append({"role": "assistant", "content": f"Error: {e}"})
        responses.append(f"User: {user_input}\nOllama: Error: {e}\n\n")

def send_prompt():
    try:
        raw_input = input_entry.get()
        user_input = raw_input.strip()
        if not user_input:
            return
        input_entry.delete(0, tk.END)
        add_message(output_frame, "User", user_input, "lightblue", anchor="e")
        dots_label.config(text=".")
        threading.Thread(target=run_ollama_chat, args=(user_input, output_frame, responses, dots_label)).start()
        animate_dots()
    except Exception as e:
        print(f"Error in send_prompt: {e}")

def redo_response():
    global last_prompt, conversation_history
    if last_prompt:
        if conversation_history and conversation_history[-1]["role"] == "assistant":
            conversation_history.pop()
        if conversation_history and conversation_history[-1]["role"] == "user" and conversation_history[-1]["content"] == last_prompt:
            conversation_history.pop()
        clear_chat_display()
        for msg in conversation_history:
            role = msg["role"]
            color = "lightblue" if role == "user" else "lightgreen" if role == "assistant" else "lightcoral"
            anchor = "e" if role == "user" else "w"
            add_message(output_frame, role.capitalize(), msg["content"], color, anchor)

        add_message(output_frame, "User", last_prompt, "lightblue", anchor="e")
        conversation_history.append({"role": "user", "content": last_prompt})
        dots_label.config(text=".")
        threading.Thread(target=run_ollama_chat, args=(last_prompt, output_frame, responses, dots_label)).start()
        animate_dots()

def save_chat():
    filepath = filedialog.asksaveasfilename(defaultextension=".json", filetypes=[("JSON files", "*.json"), ("All files", "*.*")])
    if filepath:
        with open(filepath, "w") as f:
            json.dump(conversation_history, f)

def load_chat():
    global last_prompt, conversation_history
    filepath = filedialog.askopenfilename(defaultextension=".json", filetypes=[("JSON files", "*.json"), ("All files", "*.*")])
    if filepath:
        try:
            with open(filepath, "r") as f:
                conversation_history = json.load(f)
            clear_chat_display()
            for msg in conversation_history:
                role = msg["role"]
                color = "lightblue" if role == "user" else "lightgreen" if role == "assistant" else "lightcoral"
                anchor = "e" if role == "user" else "w"
                add_message(output_frame, role.capitalize(), msg["content"], color, anchor)
            if conversation_history and conversation_history[-1]["role"] == "user":
                last_prompt = conversation_history[-1]["content"]
            else:
                last_prompt = None
        except FileNotFoundError:
            messagebox.showerror("Error", "Chat file not found.")
        except json.JSONDecodeError:
            messagebox.showerror("Error", "Invalid JSON file.")

def save_responses():
    filepath = filedialog.asksaveasfilename(defaultextension=".txt", filetypes=[("Text files", "*.txt"), ("All files", "*.*")])
    if filepath:
        full_text = ""
        for item in conversation_history:
            full_text += f"{item['role'].capitalize()}: {item['content']}\n\n"
        with open(filepath, "w") as f:
            f.write(full_text)

def clear_chat_display():
    for widget in output_frame.winfo_children():
        if widget != dots_label:
            widget.destroy()
    dots_label.config(text="")

def add_message(frame, sender, message, bg_color, anchor="w"):
    message_frame = tk.Frame(frame, padx=5, pady=5)
    canvas_width = 450

    temp_canvas = tk.Canvas()
    font = tkFont.Font(family="TkDefaultFont", size=10)
    text_id = temp_canvas.create_text(
        0, 0,
        text=message,
        font=font,
        anchor="nw",
        width=canvas_width - 30
    )
    bbox = temp_canvas.bbox(text_id)
    text_height = bbox[3] - bbox[1]
    canvas_height = text_height + 60

    message_canvas = tk.Canvas(message_frame, width=canvas_width, height=canvas_height, bg=frame.cget("bg"), highlightthickness=0)
    
    create_round_rectangle(message_canvas, 0, 0, canvas_width, canvas_height, 15, fill=bg_color)
    
    message_canvas.create_text(
        15, 10,
        text=f"{sender}:",
        fill="black", 
        font=("TkDefaultFont", 10, "bold"),
        anchor="nw"
    )
    
    message_canvas.create_text(
        15, 30,
        text=message,
        fill="black",
        font=("TkDefaultFont", 10),
        anchor="nw",
        width=canvas_width - 30
    )
    message_canvas.pack()

    message_frame.pack(anchor=anchor, pady=5, fill="x")
    root.update_idletasks()
    output_canvas.yview_moveto(1)

def create_round_button(parent, text, command, radius=15, width=80, height=30, bg="lightblue", fg="black", font=("TkDefaultFont", 10)):
    button_frame = tk.Frame(parent, width=width, height=height, bg=parent.cget("bg"))
    button_frame.pack_propagate(False)

    button_canvas = tk.Canvas(button_frame, width=width, height=height, bg=parent.cget("bg"), highlightthickness=0)
    create_round_rectangle(button_canvas, 0, 0, width, height, radius, fill=bg)
    button_canvas.pack(fill="both", expand=True)

    button_label = tk.Label(button_canvas, text=text, font=font, bg=bg, fg=fg)
    button_label.place(relx=0.5, rely=0.5, anchor="center")

    button_canvas.bind("<Button-1>", lambda event: command())
    button_label.bind("<Button-1>", lambda event: command())

    return button_frame, button_canvas

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

def animate_dots():
    def update_dots(count=0):
        if dots_label.cget("text"):
            dots = "." * (count % 3 + 1)
            dots_label.config(text=dots)
            dots_label.tkraise()
            root.after(500, update_dots, count + 1)
    update_dots()

root = tk.Tk()
root.title("O.C.GUI")

menubar = tk.Menu(root)
file_menu = tk.Menu(menubar, tearoff=0)
file_menu.add_command(label="Load Chat", command=load_chat)
file_menu.add_separator()
file_menu.add_command(label="Save Responses (Legacy)", command=save_responses)
file_menu.add_separator()
file_menu.add_command(label="Exit", command=root.quit)
menubar.add_cascade(label="File", menu=file_menu)
root.config(menu=menubar)

input_label = tk.Label(root, text="Enter your prompt:")
input_label.pack(pady=5)

input_entry = tk.Entry(root, width=80)
input_entry.pack(pady=5)

button_frame = tk.Frame(root)
button_frame.pack(pady=5)

send_button_rounded, send_button_canvas = create_round_button(button_frame, "Send", send_prompt)
send_button_rounded.pack(side=tk.LEFT, padx=5)

send_button_canvas.bind("<Button-1>", lambda event: send_prompt())

redo_button_rounded, redo_button_canvas = create_round_button(button_frame, "Redo", redo_response, bg="lightgreen")
redo_button_rounded.pack(side=tk.LEFT, padx=5)

output_scroll = tk.Scrollbar(root)
output_scroll.pack(side=tk.RIGHT, fill=tk.Y)

output_canvas = tk.Canvas(root, yscrollcommand=output_scroll.set)
output_canvas.pack(side=tk.LEFT, fill=tk.BOTH, expand=True)

output_scroll.config(command=output_canvas.yview)

output_frame = tk.Frame(output_canvas)
output_canvas.create_window((0, 0), window=output_frame, anchor=tk.NW)

output_frame.bind("<Configure>", lambda event, canvas=output_canvas, frame=output_frame: canvas.configure(scrollregion=canvas.bbox("all")))

dots_label = tk.Label(button_frame, text="", font=("TkDefaultFont", 12, "bold"))
dots_label.place(relx=0.5, rely=0.5, anchor="center")
dots_label.tkraise()

save_button_rounded, save_button_canvas = create_round_button(root, "Save Chat State", save_chat, bg="lightblue", width=150, height=40)
save_button_rounded.pack(pady=5)

responses = []
last_prompt = None
conversation_history = []

root.mainloop()
root.update_idletasks()