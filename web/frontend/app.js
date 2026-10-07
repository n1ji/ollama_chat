"use strict";
// Talks to the backend through three endpoints (see ../API.md), so either side can be swapped.
const $ = (id) => document.getElementById(id);
const els = {
  chat: $("chat"), messages: $("messages"), model: $("model"), refresh: $("refresh"),
  save: $("save"), load: $("load"), clear: $("clear"), file: $("file"),
  input: $("input"), send: $("send"), stop: $("stop"), redo: $("redo"), status: $("status"),
  toolbar: $("toolbar"), dock: $("dock"), glassBtn: $("glass-btn"), glassPop: $("glass-pop"), glass: $("glass"),
};
const CUSTOM = "__custom__";
const STORAGE_KEY = "ollama_web_chat";

let messages = [];      // [{role, content}] -- the same format the desktop app saves
let model = null;
let busy = false;
let controller = null;  // AbortController for the request in flight
let lastPrompt = null;  // what Redo resends, and where that turn starts in `messages`
let lastTurnStart = 0;

function syncLast() {   // after loading a chat: Redo regenerates its last exchange
  lastPrompt = null;
  for (let i = messages.length - 1; i >= 0; i--) {
    if (messages[i].role === "user") { lastPrompt = messages[i].content; lastTurnStart = i; break; }
  }
}

// ---------- storage (never required for the page to work) ----------
function persist() {
  try { localStorage.setItem(STORAGE_KEY, JSON.stringify(messages)); } catch (e) {}
}
function restore() {
  try {
    const saved = JSON.parse(localStorage.getItem(STORAGE_KEY) || "[]");
    if (validMessages(saved)) messages = saved;
  } catch (e) {}
}
function validMessages(list) {
  return Array.isArray(list) && list.every((m) =>
    m && typeof m === "object" && typeof m.role === "string" && typeof m.content === "string");
}

// ---------- rendering ----------
function drawMarkdown(body, text) {
  body.replaceChildren(window.renderMarkdown ? window.renderMarkdown(text) : document.createTextNode(text));
}
function makeBubble(role, text) {
  const div = document.createElement("div");
  div.className = "msg " + (role === "user" ? "user" : role === "assistant" ? "assistant" : "error");
  const who = document.createElement("div");
  who.className = "who";
  who.textContent = role === "user" ? "User" : role === "assistant" ? "Ollama" : role[0].toUpperCase() + role.slice(1);
  const body = document.createElement("div");
  body.className = "body";
  if (role === "assistant") {
    body.classList.add("md");
    drawMarkdown(body, text);   // built from DOM nodes, never innerHTML
  } else {
    body.textContent = text;    // your own messages stay plain text
  }
  div.append(who, body);
  els.messages.append(div);
  return div;
}
function renderAll() {
  els.messages.textContent = "";
  if (!messages.length) {
    const hint = document.createElement("div");
    hint.className = "empty";
    hint.textContent = model ? "Say something to " + model : "Pick a model at the top to get started";
    els.messages.append(hint);
  }
  messages.forEach((m) => makeBubble(m.role, m.content));
  scrollToBottom(true);
}
function nearBottom() {
  return els.chat.scrollHeight - els.chat.scrollTop - els.chat.clientHeight < 80;
}
function scrollToBottom(force) {
  if (force || nearBottom()) els.chat.scrollTop = els.chat.scrollHeight;
}
function setStatus(text) { els.status.textContent = text || ""; }

function setBusy(flag) {
  busy = flag;
  els.send.hidden = flag;
  els.stop.hidden = !flag;
  els.redo.disabled = flag;
  els.load.disabled = flag;
  els.clear.disabled = flag;
  els.model.disabled = flag;
  els.refresh.disabled = flag;
}

// ---------- models ----------
async function loadModels() {
  let info;
  try {
    info = await (await fetch("/api/models")).json();
  } catch (e) {
    info = { models: [], selected: null, error: "Couldn't reach the server: " + e.message };
  }
  const names = info.models.slice();
  const current = model || info.selected;
  if (current && !names.includes(current)) names.unshift(current);

  els.model.textContent = "";
  if (!names.length) els.model.append(new Option("(no models found)", ""));
  names.forEach((n) => els.model.append(new Option(n, n)));
  els.model.append(new Option("Custom...", CUSTOM));

  model = current && names.includes(current) ? current : (names[0] || null);
  els.model.value = model || "";
  setStatus(info.error || "");
  if (!messages.length) renderAll();
}
async function chooseModel(name) {
  model = name;
  setStatus("");
  if (!messages.length) renderAll();
  try {
    const res = await fetch("/api/model", {
      method: "POST", headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ model: name }),
    });
    if (!res.ok) setStatus((await res.json()).error || "Couldn't remember the model");
  } catch (e) { setStatus("Couldn't remember the model: " + e.message); }
}
els.model.addEventListener("change", async () => {
  if (els.model.value === CUSTOM) {
    const typed = (prompt("Model name (as in `ollama list`):") || "").trim();
    if (typed) {
      if (![...els.model.options].some((o) => o.value === typed)) {
        els.model.insertBefore(new Option(typed, typed), els.model.lastElementChild);
      }
      els.model.value = typed;
      await chooseModel(typed);
    } else {
      els.model.value = model || "";
    }
    return;
  }
  if (els.model.value) await chooseModel(els.model.value);
});
els.refresh.addEventListener("click", loadModels);

// ---------- chatting ----------
async function ask(prompt) {
  if (busy) return;
  if (!model) { setStatus("No model selected. Pick one at the top."); return; }

  const turnStart = messages.length;   // errors roll the chat back to here
  lastPrompt = prompt;
  lastTurnStart = turnStart;
  messages.push({ role: "user", content: prompt });
  if (turnStart === 0) els.messages.textContent = "";
  makeBubble("user", prompt);
  const bubble = makeBubble("assistant", "");
  bubble.classList.add("thinking");
  const body = bubble.querySelector(".body");
  scrollToBottom(true);

  let reply = "";
  let frame = 0;   // streaming repaints are batched to one per animation frame
  let failure = null;
  let stopped = false;
  controller = new AbortController();
  setBusy(true);
  setStatus("Generating...");

  try {
    const res = await fetch("/api/chat", {
      method: "POST", headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ model, messages }), signal: controller.signal,
    });
    if (!res.ok) {
      let msg = "HTTP " + res.status;
      try { msg = (await res.json()).error || msg; } catch (e) {}
      throw new Error(msg);
    }
    const reader = res.body.getReader();
    const decoder = new TextDecoder();
    let buffer = "";
    for (;;) {
      const { value, done } = await reader.read();
      if (done) break;
      buffer += decoder.decode(value, { stream: true });
      let nl;
      while ((nl = buffer.indexOf("\n")) >= 0) {
        const line = buffer.slice(0, nl).trim();
        buffer = buffer.slice(nl + 1);
        if (!line) continue;
        const event = JSON.parse(line);
        if (event.error) throw new Error(event.error);
        if (event.content) {
          reply += event.content;
          bubble.classList.remove("thinking");
          if (!frame) {
            frame = requestAnimationFrame(() => {
              frame = 0;
              const stick = nearBottom();
              drawMarkdown(body, reply);
              if (stick) scrollToBottom(true);
            });
          }
        }
      }
    }
  } catch (e) {
    if (e.name === "AbortError") stopped = true; else failure = e;
  }
  if (!failure && !stopped && !reply) {
    // Thinking models can use their whole turn thinking and send no text.
    failure = new Error("The model sent back an empty reply. Try Redo, or pick another model.");
  }

  if (frame) cancelAnimationFrame(frame);
  if (reply) drawMarkdown(body, reply);   // final paint with the complete text
  controller = null;
  setBusy(false);
  setStatus("");

  if (failure) {
    // Same as the desktop app: show the error, but keep it out of the saved chat.
    messages.length = turnStart;
    bubble.remove();
    makeBubble("error", failure.message);
  } else if (reply) {
    messages.push({ role: "assistant", content: reply });   // a stopped reply keeps what arrived
  } else {
    messages.length = turnStart;                            // stopped before any text: drop the turn
    renderAll();
  }
  persist();
  scrollToBottom(true);
  els.input.focus();
}

function submit() {
  const text = els.input.value.trim();
  if (!text || busy) return;
  els.input.value = "";
  autosize();
  ask(text);
}
function redo() {
  if (busy || lastPrompt === null) return;
  const prompt = lastPrompt;
  messages.length = lastTurnStart;
  renderAll();
  ask(prompt);
}

els.send.addEventListener("click", submit);
els.stop.addEventListener("click", () => controller && controller.abort());
els.redo.addEventListener("click", redo);
els.input.addEventListener("keydown", (e) => {
  if (e.key === "Enter" && !e.shiftKey && !e.isComposing) { e.preventDefault(); submit(); }
});
function autosize() {
  els.input.style.height = "auto";
  els.input.style.height = Math.min(els.input.scrollHeight, 200) + "px";
}
els.input.addEventListener("input", autosize);

// ---------- save / load / new ----------
els.save.addEventListener("click", () => {
  const blob = new Blob([JSON.stringify(messages, null, 2)], { type: "application/json" });
  const a = document.createElement("a");
  a.href = URL.createObjectURL(blob);
  a.download = "chat.json";
  a.click();
  URL.revokeObjectURL(a.href);
});
els.load.addEventListener("click", () => els.file.click());
els.file.addEventListener("change", async () => {
  const file = els.file.files[0];
  els.file.value = "";
  if (!file) return;
  try {
    const data = JSON.parse(await file.text());
    if (!validMessages(data)) throw new Error("expected a list of messages with 'role' and 'content'");
    messages = data;
    syncLast();
    persist();
    renderAll();
    setStatus("");
  } catch (e) {
    setStatus("Couldn't load that file: " + e.message);
  }
});
els.clear.addEventListener("click", () => {
  if (busy) return;
  messages = [];
  lastPrompt = null;
  persist();
  renderAll();
  els.input.focus();
});

// ---------- glass appearance (Clear <-> Tinted, like the macOS 27 setting) ----------
const GLASS_KEY = "ollama_web_glass";
function applyTint(percent) {
  document.documentElement.style.setProperty("--tint", String(percent / 100));
}
function initGlass() {
  let percent = 60;
  try {
    const saved = parseInt(localStorage.getItem(GLASS_KEY), 10);
    if (saved >= 0 && saved <= 100) percent = saved;
  } catch (e) {}
  els.glass.value = percent;
  applyTint(percent);
}
els.glass.addEventListener("input", () => {
  applyTint(+els.glass.value);
  try { localStorage.setItem(GLASS_KEY, els.glass.value); } catch (e) {}
});
function setPopover(open) {
  els.glassPop.hidden = !open;
  els.glassBtn.setAttribute("aria-expanded", String(open));
}
els.glassBtn.addEventListener("click", (e) => { e.stopPropagation(); setPopover(els.glassPop.hidden); });
document.addEventListener("click", (e) => {
  if (!els.glassPop.hidden && !els.glassPop.contains(e.target)) setPopover(false);
});
document.addEventListener("keydown", (e) => { if (e.key === "Escape") setPopover(false); });

// The chat scrolls underneath the glass, so it needs to know how tall the toolbar and composer are.
function syncLayout() {
  const root = document.documentElement.style;
  root.setProperty("--toolbar-h", els.toolbar.offsetHeight + "px");
  root.setProperty("--dock-h", els.dock.offsetHeight + "px");
}
if (window.ResizeObserver) {
  const observer = new ResizeObserver(syncLayout);
  observer.observe(els.toolbar);
  observer.observe(els.dock);
}

// ---------- start ----------
initGlass();
syncLayout();
restore();
syncLast();
renderAll();
loadModels().then(() => { if (messages.length) renderAll(); });
els.input.focus();
