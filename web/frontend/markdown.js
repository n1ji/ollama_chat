"use strict";
// A small Markdown renderer. It builds DOM nodes directly (never innerHTML), so model output
// can't inject markup: raw HTML in a reply is shown as text, only http(s) and mailto links are
// made clickable, and images are shown as links so a reply can't make the browser fetch anything.
//
// Supports: headings, bold, italic, ~~strikethrough~~, `code`, fenced code blocks (with a Copy
// button), bullet/numbered/nested/task lists, > quotes, tables, links, autolinks and ---.
// renderMarkdown(text) returns a DocumentFragment.

(function () {
  const SAFE_URL = /^(https?:|mailto:)/i;

  const RE = {
    fence: /^ {0,3}(`{3,}|~{3,})[ \t]*([^\s`]*)[^`]*$/,
    fenceEnd: /^ {0,3}(`{3,}|~{3,})[ \t]*$/,
    heading: /^ {0,3}(#{1,6})(?:[ \t]+(.*?))?(?:[ \t]+#+)?[ \t]*$/,
    hr: /^ {0,3}([-*_])(?:[ \t]*\1){2,}[ \t]*$/,
    quote: /^ {0,3}>/,
    item: /^( {0,3})([-*+]|\d{1,9}[.)])([ \t]+(.*))?$/,
    tableDelim: /^ {0,3}\|?[ \t]*:?-+:?[ \t]*(\|[ \t]*:?-+:?[ \t]*)*\|?[ \t]*$/,
    blank: /^\s*$/,
  };

  function h(tag, className) {
    const node = document.createElement(tag);
    if (className) node.className = className;
    return node;
  }

  // ---------- inline ----------

  function isWordChar(ch) { return ch !== undefined && /[\p{L}\p{N}]/u.test(ch); }
  function isSpace(ch) { return ch === undefined || /\s/.test(ch); }

  function makeLink(url) {
    const a = h("a");
    a.href = url;
    a.target = "_blank";
    a.rel = "noopener noreferrer";
    return a;
  }

  // Index just past the code span starting at i, or -1 if it never closes.
  function skipCodeSpan(text, i) {
    let n = 0;
    while (text[i + n] === "`") n++;
    const run = "`".repeat(n);
    let j = i + n;
    while ((j = text.indexOf(run, j)) !== -1) {
      if (text[j + n] !== "`" && text[j - 1] !== "`") return j + n;
      j++;
    }
    return -1;
  }

  function findClosingBracket(text, start) {
    let depth = 0;
    for (let i = start; i < text.length; i++) {
      const c = text[i];
      if (c === "\\") { i++; continue; }
      if (c === "`") {
        const end = skipCodeSpan(text, i);
        if (end !== -1) { i = end - 1; continue; }
        while (text[i + 1] === "`") i++;
        continue;
      }
      if (c === "[") depth++;
      else if (c === "]" && --depth === 0) return i;
    }
    return -1;
  }

  // [label](url "title") starting at text[i] === "["
  function parseLinkAt(text, i) {
    const close = findClosingBracket(text, i);
    if (close < 0 || text[close + 1] !== "(") return null;
    let p = close + 2;
    while (text[p] === " ") p++;
    let url = "";
    if (text[p] === "<") {
      const end = text.indexOf(">", p);
      if (end < 0) return null;
      url = text.slice(p + 1, end);
      p = end + 1;
    } else {
      let depth = 0;
      for (; p < text.length; p++) {
        const c = text[p];
        if (c === " " || c === "\n") break;
        if (c === "(") depth++;
        else if (c === ")") { if (depth === 0) break; depth--; }
        url += c;
      }
    }
    while (text[p] === " " || text[p] === "\n") p++;
    if (text[p] === '"' || text[p] === "'") {
      const end = text.indexOf(text[p], p + 1);
      if (end < 0) return null;
      p = end + 1;
      while (text[p] === " ") p++;
    }
    if (text[p] !== ")") return null;
    return { label: text.slice(i + 1, close), url, next: p + 1 };
  }

  // Where the emphasis opened at `from` closes, or -1. `delim` is e.g. "*", "**", "~~", "***".
  function findEmphasisClose(text, from, delim) {
    const c = delim[0];
    const n = delim.length;
    for (let j = from; j < text.length; j++) {
      const ch = text[j];
      if (ch === "\\") { j++; continue; }
      if (ch === "`") {
        const end = skipCodeSpan(text, j);
        if (end !== -1) j = end - 1; else while (text[j + 1] === "`") j++;
        continue;
      }
      if (ch !== c) continue;
      let run = 1;
      while (text[j + run] === c) run++;
      const usable = !isSpace(text[j - 1]) && (c !== "_" || !isWordChar(text[j + run]));
      if (n === 1) {
        if (run === 1 && usable) return j;      // longer runs belong to bold inside the italics
      } else if (run >= n && usable) {
        return j;
      }
      j += run - 1;
    }
    return -1;
  }

  function trimUrl(url) {
    for (;;) {
      const last = url[url.length - 1];
      if (/[.,;:!?'"*_~]/.test(last)) url = url.slice(0, -1);
      else if (last === ")" && (url.match(/\(/g) || []).length < (url.match(/\)/g) || []).length) url = url.slice(0, -1);
      else return url;
    }
  }

  function parseInline(text, parent, noLinks) {
    let buf = "";
    const flush = () => { if (buf) { parent.append(buf); buf = ""; } };
    let i = 0;
    while (i < text.length) {
      const c = text[i];

      if (c === "\n") { flush(); parent.append(h("br")); i++; continue; }

      if (c === "\\" && i + 1 < text.length && /[\\`*_{}[\]()#+\-.!|~<>]/.test(text[i + 1])) {
        buf += text[i + 1];
        i += 2;
        continue;
      }

      if (c === "`") {
        let n = 0;
        while (text[i + n] === "`") n++;
        const end = skipCodeSpan(text, i);
        if (end === -1) { buf += "`".repeat(n); i += n; continue; }
        let inner = text.slice(i + n, end - n).replace(/\n/g, " ");
        if (inner.length > 2 && inner.startsWith(" ") && inner.endsWith(" ")) inner = inner.slice(1, -1);
        flush();
        const code = h("code");
        code.textContent = inner;
        parent.append(code);
        i = end;
        continue;
      }

      if (c === "!" && text[i + 1] === "[") {
        const link = parseLinkAt(text, i + 1);
        if (link) {
          flush();
          const label = link.label || link.url;
          if (!noLinks && SAFE_URL.test(link.url.trim())) {
            const a = makeLink(link.url.trim());
            a.textContent = "\u{1F5BC} " + label;   // shown as a link, never fetched
            parent.append(a);
          } else {
            parent.append("\u{1F5BC} " + label);
          }
          i = link.next;
          continue;
        }
      }

      if (c === "[") {
        const link = parseLinkAt(text, i);
        if (link) {
          flush();
          const url = link.url.trim();
          if (!noLinks && SAFE_URL.test(url)) {
            const a = makeLink(url);
            parseInline(link.label, a, true);
            parent.append(a);
          } else {
            parseInline(link.label, parent, noLinks);   // unsafe or nested link: keep the text only
          }
          i = link.next;
          continue;
        }
      }

      if (c === "<" && !noLinks) {
        const m = /^<((?:https?:\/\/|mailto:)[^\s<>]+)>/i.exec(text.slice(i));
        if (m) {
          flush();
          const a = makeLink(m[1]);
          a.textContent = m[1];
          parent.append(a);
          i += m[0].length;
          continue;
        }
      }

      if (c === "h" && !noLinks && !isWordChar(text[i - 1]) && /^https?:\/\//i.test(text.slice(i, i + 8))) {
        const m = /^https?:\/\/[^\s<]+/i.exec(text.slice(i));
        const url = m && trimUrl(m[0]);
        if (url && url.length > 8) {
          flush();
          const a = makeLink(url);
          a.textContent = url;
          parent.append(a);
          i += url.length;
          continue;
        }
      }

      if (c === "*" || c === "_" || c === "~") {
        let run = 1;
        while (text[i + run] === c) run++;
        const next = text[i + run];
        const opens = !isSpace(next) && (c !== "_" || !isWordChar(text[i - 1]));
        const okRun = c === "~" ? run === 2 : run <= 3;
        if (opens && okRun) {
          const delim = c.repeat(run);
          const end = findEmphasisClose(text, i + run, delim);
          if (end !== -1 && end > i + run) {
            flush();
            const inner = text.slice(i + run, end);
            if (c === "~") {
              const del = h("del");
              parseInline(inner, del, noLinks);
              parent.append(del);
            } else if (run === 1) {
              const em = h("em");
              parseInline(inner, em, noLinks);
              parent.append(em);
            } else {
              const strong = h("strong");
              if (run === 3) {
                const em = h("em");
                parseInline(inner, em, noLinks);
                strong.append(em);
              } else {
                parseInline(inner, strong, noLinks);
              }
              parent.append(strong);
            }
            i = end + run;
            continue;
          }
        }
        buf += c.repeat(run);
        i += run;
        continue;
      }

      buf += c;
      i++;
    }
    flush();
  }

  // ---------- blocks ----------

  function indentOf(line) {
    let n = 0;
    while (line[n] === " ") n++;
    return n;
  }

  function splitRow(line) {
    let s = line.trim();
    if (s.startsWith("|")) s = s.slice(1);
    if (s.endsWith("|") && !s.endsWith("\\|")) s = s.slice(0, -1);
    const cells = [];
    let cur = "";
    for (let k = 0; k < s.length; k++) {
      if (s[k] === "\\" && s[k + 1] === "|") { cur += "|"; k++; }
      else if (s[k] === "|") { cells.push(cur.trim()); cur = ""; }
      else cur += s[k];
    }
    cells.push(cur.trim());
    return cells;
  }

  function isTableStart(lines, i) {
    if (i + 1 >= lines.length || !lines[i].includes("|")) return false;
    const delim = lines[i + 1];
    if (!delim.includes("-") || !RE.tableDelim.test(delim)) return false;
    return splitRow(lines[i]).length === splitRow(delim).length;
  }

  function startsBlock(lines, i) {
    const line = lines[i];
    return RE.fence.test(line) || RE.heading.test(line) || RE.hr.test(line) ||
      RE.quote.test(line) || isTableStart(lines, i);
  }

  async function copyText(text) {
    try { await navigator.clipboard.writeText(text); return true; } catch (e) { /* fall through */ }
    const area = document.createElement("textarea");
    area.value = text;
    area.style.cssText = "position:fixed;opacity:0";
    document.body.append(area);
    area.select();
    let ok = false;
    try { ok = document.execCommand("copy"); } catch (e) { /* ignore */ }
    area.remove();
    return ok;
  }

  function codeBlock(code, lang) {
    const box = h("div", "codeblock");
    const head = h("div", "codehead");
    const label = h("span");
    label.textContent = lang || "code";
    const button = h("button", "copy");
    button.type = "button";
    button.textContent = "Copy";
    button.addEventListener("click", async () => {
      button.textContent = (await copyText(code)) ? "Copied" : "Couldn't copy";
      setTimeout(() => { button.textContent = "Copy"; }, 1500);
    });
    const pre = h("pre");
    const inner = h("code");
    inner.textContent = code;
    pre.append(inner);
    head.append(label, button);
    box.append(head, pre);
    return box;
  }

  function parseFence(lines, i, m, parent) {
    const fence = m[1];
    const code = [];
    i++;
    while (i < lines.length) {
      const end = RE.fenceEnd.exec(lines[i]);
      if (end && end[1][0] === fence[0] && end[1].length >= fence.length) { i++; break; }
      code.push(lines[i]);
      i++;
    }
    parent.append(codeBlock(code.join("\n"), m[2]));   // an unclosed fence runs to the end (streaming)
    return i;
  }

  function parseTable(lines, i, parent) {
    const head = splitRow(lines[i]);
    const aligns = splitRow(lines[i + 1]).map((cell) =>
      cell.startsWith(":") && cell.endsWith(":") ? "center" : cell.endsWith(":") ? "right" : cell.startsWith(":") ? "left" : "");
    const wrap = h("div", "table-wrap");
    const table = h("table");
    const thead = h("thead");
    const headRow = h("tr");
    head.forEach((text, k) => {
      const th = h("th");
      if (aligns[k]) th.style.textAlign = aligns[k];
      parseInline(text, th);
      headRow.append(th);
    });
    thead.append(headRow);
    const tbody = h("tbody");
    i += 2;
    while (i < lines.length && !RE.blank.test(lines[i]) && lines[i].includes("|")) {
      const cells = splitRow(lines[i]);
      const row = h("tr");
      head.forEach((_, k) => {
        const td = h("td");
        if (aligns[k]) td.style.textAlign = aligns[k];
        parseInline(cells[k] || "", td);
        row.append(td);
      });
      tbody.append(row);
      i++;
    }
    table.append(thead);
    if (tbody.children.length) table.append(tbody);
    wrap.append(table);
    parent.append(wrap);
    return i;
  }

  function parseParagraph(lines, i, parent) {
    const para = [];
    while (i < lines.length && !RE.blank.test(lines[i])) {
      if (para.length) {
        const m = RE.item.exec(lines[i]);
        if (startsBlock(lines, i) || (m && (!/\d/.test(m[2][0]) || parseInt(m[2], 10) === 1))) break;
      }
      para.push(lines[i].trim());
      i++;
    }
    const p = h("p");
    parseInline(para.join("\n"), p);
    parent.append(p);
    return i;
  }

  function parseList(lines, i, parent) {
    const first = RE.item.exec(lines[i]);
    const ordered = /\d/.test(first[2][0]);
    const delimOf = (m) => (/\d/.test(m[2][0]) ? m[2].slice(-1) : m[2]);
    const delim = delimOf(first);
    const base = first[1].length;
    const list = h(ordered ? "ol" : "ul");
    if (ordered && parseInt(first[2], 10) !== 1) list.start = parseInt(first[2], 10);
    const sameKind = (m) => m && m[1].length < base + 2 && /\d/.test(m[2][0]) === ordered && delimOf(m) === delim;

    let loose = false;
    const items = [];
    while (i < lines.length) {
      const m = RE.item.exec(lines[i]);
      if (!sameKind(m)) break;
      const text = m[4] || "";
      const spaces = m[3] ? Math.min(m[3].length - text.length, 4) : 1;
      const contentIndent = m[1].length + m[2].length + spaces;
      const itemLines = [text];
      i++;
      while (i < lines.length) {
        const line = lines[i];
        if (RE.blank.test(line)) {
          let k = i + 1;
          while (k < lines.length && RE.blank.test(lines[k])) k++;
          if (k >= lines.length) { i = k; break; }
          if (indentOf(lines[k]) >= base + 2) {            // more of this item after a blank line
            for (let t = i; t < k; t++) itemLines.push("");
            i = k;
            loose = true;
            continue;
          }
          if (sameKind(RE.item.exec(lines[k]))) loose = true;  // blank line between items
          i = k;
          break;
        }
        const indent = indentOf(line);
        if (indent >= base + 2) {
          itemLines.push(line.slice(Math.min(indent, contentIndent)));
          i++;
          continue;
        }
        if (RE.item.exec(line) || startsBlock(lines, i)) break;
        itemLines.push(line.trim());                          // lazy continuation of the text
        i++;
      }
      items.push(itemLines);
    }

    for (const itemLines of items) {
      const li = h("li");
      let task = null;
      const t = /^\[( |x|X)\][ \t]+/.exec(itemLines[0]);
      if (t) { task = t[1] !== " "; itemLines[0] = itemLines[0].slice(t[0].length); }
      parseBlocks(itemLines, li);
      if (!loose) {                                           // tight list: no paragraph gaps
        for (const child of [...li.children]) if (child.tagName === "P") child.replaceWith(...child.childNodes);
      }
      if (task !== null) {
        const box = h("input");
        box.type = "checkbox";
        box.disabled = true;
        box.checked = task;
        li.prepend(box, " ");
        li.classList.add("task");
      }
      list.append(li);
    }
    parent.append(list);
    return i;
  }

  function parseBlocks(lines, parent) {
    let i = 0;
    while (i < lines.length) {
      const line = lines[i];
      if (RE.blank.test(line)) { i++; continue; }

      let m = RE.fence.exec(line);
      if (m) { i = parseFence(lines, i, m, parent); continue; }

      m = RE.heading.exec(line);
      if (m) {
        const heading = h("h" + m[1].length);
        parseInline(m[2] || "", heading);
        parent.append(heading);
        i++;
        continue;
      }

      if (RE.hr.test(line)) { parent.append(h("hr")); i++; continue; }

      if (RE.quote.test(line)) {
        const inner = [];
        while (i < lines.length && RE.quote.test(lines[i])) { inner.push(lines[i].replace(/^ {0,3}> ?/, "")); i++; }
        const quote = h("blockquote");
        parseBlocks(inner, quote);
        parent.append(quote);
        continue;
      }

      if (isTableStart(lines, i)) { i = parseTable(lines, i, parent); continue; }

      if (RE.item.test(line)) { i = parseList(lines, i, parent); continue; }

      i = parseParagraph(lines, i, parent);
    }
  }

  function renderMarkdown(text) {
    const fragment = document.createDocumentFragment();
    const lines = String(text).replace(/\r\n?/g, "\n").split("\n")
      .map((line) => line.replace(/^\t+/, (tabs) => "    ".repeat(tabs.length)));
    parseBlocks(lines, fragment);
    return fragment;
  }

  window.renderMarkdown = renderMarkdown;
})();
