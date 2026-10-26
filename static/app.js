const $ = (id) => document.getElementById(id);

const els = {
  ingestForm: $("ingest-form"),
  url: $("url"),
  ingestBtn: $("ingest-btn"),
  status: $("status"),
  error: $("error"),
  result: $("result"),
  docTitle: $("doc-title"),
  docLink: $("doc-link"),
  docMode: $("doc-mode"),
  summary: $("panel-summary"),
  source: $("panel-source"),
  sourceText: $("source-text"),
  sourceSize: $("source-size"),
  tabSummary: $("tab-summary"),
  tabSource: $("tab-source"),
  messages: $("messages"),
  chatForm: $("chat-form"),
  chatInput: $("chat-input"),
  chatBtn: $("chat-btn"),
  modelNote: $("model-note"),
};

let sessionId = null;
let ingesting = false;
let chatting = false;

const escapeHtml = (value) =>
  value.replace(/[&<>"']/g, (ch) => ({
    "&": "&amp;",
    "<": "&lt;",
    ">": "&gt;",
    '"': "&quot;",
    "'": "&#39;",
  }[ch]));

function inline(text) {
  const parts = text.split(/(`[^`]+`)/g);
  return parts
    .map((part) => {
      if (part.length > 2 && part.startsWith("`") && part.endsWith("`")) {
        return `<code>${escapeHtml(part.slice(1, -1))}</code>`;
      }
      let out = escapeHtml(part);
      out = out.replace(/\*\*([^*]+)\*\*/g, "<strong>$1</strong>");
      out = out.replace(/(^|[^*])\*([^*]+)\*/g, "$1<em>$2</em>");
      out = out.replace(
        /\[([^\]]+)\]\((https?:\/\/[^\s)]+)\)/g,
        '<a href="$2" target="_blank" rel="noreferrer noopener">$1</a>'
      );
      return out;
    })
    .join("");
}

function renderMarkdown(source) {
  const lines = String(source || "").replace(/\r\n/g, "\n").split("\n");
  let html = "";
  let list = null;
  let inCode = false;
  let code = [];
  let para = [];

  const flushPara = () => {
    if (para.length) {
      html += `<p>${inline(para.join(" "))}</p>`;
      para = [];
    }
  };
  const closeList = () => {
    if (list) {
      html += `</${list}>`;
      list = null;
    }
  };

  for (const raw of lines) {
    const line = raw.trimEnd();
    const trimmed = line.trim();

    if (trimmed.startsWith("```")) {
      if (inCode) {
        html += `<pre><code>${escapeHtml(code.join("\n"))}</code></pre>`;
        code = [];
        inCode = false;
      } else {
        flushPara();
        closeList();
        inCode = true;
      }
      continue;
    }
    if (inCode) {
      code.push(raw);
      continue;
    }
    if (!trimmed) {
      flushPara();
      closeList();
      continue;
    }

    let match;
    if ((match = trimmed.match(/^#{1,6}\s+(.*)$/))) {
      flushPara();
      closeList();
      html += `<h3>${inline(match[1])}</h3>`;
      continue;
    }
    if (/^(-{3,}|\*{3,})$/.test(trimmed)) {
      flushPara();
      closeList();
      html += "<hr />";
      continue;
    }
    if ((match = line.match(/^\s*[-*+]\s+(.*)$/))) {
      flushPara();
      if (list !== "ul") {
        closeList();
        html += "<ul>";
        list = "ul";
      }
      html += `<li>${inline(match[1])}</li>`;
      continue;
    }
    if ((match = line.match(/^\s*\d+[.)]\s+(.*)$/))) {
      flushPara();
      if (list !== "ol") {
        closeList();
        html += "<ol>";
        list = "ol";
      }
      html += `<li>${inline(match[1])}</li>`;
      continue;
    }
    if ((match = line.match(/^>\s?(.*)$/))) {
      flushPara();
      closeList();
      html += `<blockquote>${inline(match[1])}</blockquote>`;
      continue;
    }
    para.push(trimmed);
  }

  if (inCode && code.length) {
    html += `<pre><code>${escapeHtml(code.join("\n"))}</code></pre>`;
  }
  flushPara();
  closeList();
  return html;
}

function showError(message) {
  els.error.textContent = message;
  els.error.hidden = false;
}

function clearError() {
  els.error.hidden = true;
  els.error.textContent = "";
}

function setStatus(text, busy = false) {
  els.status.textContent = text || "";
  els.status.classList.toggle("is-busy", Boolean(busy));
}

function selectTab(name) {
  const summary = name === "summary";
  els.tabSummary.classList.toggle("is-active", summary);
  els.tabSource.classList.toggle("is-active", !summary);
  els.tabSummary.setAttribute("aria-selected", String(summary));
  els.tabSource.setAttribute("aria-selected", String(!summary));
  els.summary.hidden = !summary;
  els.source.hidden = summary;
}

async function api(path, options = {}) {
  const response = await fetch(path, {
    headers: { "Content-Type": "application/json" },
    ...options,
  });
  let body = null;
  try {
    body = await response.json();
  } catch {
    body = null;
  }
  if (!response.ok) {
    const detail = body && body.detail ? body.detail : `Request failed (${response.status})`;
    throw new Error(detail);
  }
  return body;
}

async function ingest(url) {
  if (ingesting) return;
  ingesting = true;
  clearError();
  els.ingestBtn.disabled = true;
  els.ingestBtn.textContent = "Working…";
  setStatus("Scraping the page with Firecrawl…", true);

  const timers = [
    setTimeout(() => setStatus("Cleaning the article and writing the summary…", true), 3500),
    setTimeout(() => setStatus("Still working — long pages take a little longer…", true), 15000),
  ];

  try {
    const data = await api("/api/ingest", {
      method: "POST",
      body: JSON.stringify({ url }),
    });
    sessionId = data.session_id;

    els.docTitle.textContent = data.title || "Untitled";
    els.docLink.textContent = data.url;
    els.docLink.href = data.url;
    els.docMode.textContent = data.mode === "crew" ? "crewAI crew" : "ScaleDown direct";
    els.summary.innerHTML = renderMarkdown(data.summary);
    els.sourceText.textContent = data.markdown;
    els.sourceSize.textContent = `${data.source_chars.toLocaleString()} chars of markdown`;
    selectTab("summary");

    els.messages.innerHTML = "";
    els.result.hidden = false;
    setStatus(
      `Ready · ${data.source_chars.toLocaleString()} characters scraped`,
      false
    );
    els.result.scrollIntoView({ behavior: "smooth", block: "start" });
    els.chatInput.focus({ preventScroll: true });
  } catch (error) {
    showError(error.message);
    setStatus("");
  } finally {
    timers.forEach(clearTimeout);
    ingesting = false;
    els.ingestBtn.disabled = false;
    els.ingestBtn.textContent = "Summarise";
  }
}

function addMessage(role, content) {
  const wrapper = document.createElement("div");
  wrapper.className = `msg ${role}`;
  const bubble = document.createElement("div");
  bubble.className = "bubble";
  if (role === "assistant") {
    bubble.innerHTML = renderMarkdown(content);
  } else {
    bubble.textContent = content;
  }
  wrapper.appendChild(bubble);
  els.messages.appendChild(wrapper);
  els.messages.scrollTop = els.messages.scrollHeight;
  return wrapper;
}

function addTyping() {
  const wrapper = document.createElement("div");
  wrapper.className = "msg assistant";
  wrapper.dataset.typing = "true";
  wrapper.innerHTML =
    '<div class="bubble"><span class="typing"><i></i><i></i><i></i></span></div>';
  els.messages.appendChild(wrapper);
  els.messages.scrollTop = els.messages.scrollHeight;
  return wrapper;
}

function addMeta(wrapper, model, grounded) {
  if (!model && !grounded) return;
  const meta = document.createElement("div");
  meta.className = "msg-meta";

  if (model) {
    const via = document.createElement("span");
    via.className = "via";
    via.textContent = `via ${model}`;
    meta.appendChild(via);
  }

  if (grounded) {
    const level =
      grounded.confidence >= 0.8 ? "high" : grounded.confidence >= 0.55 ? "medium" : "low";
    const badge = document.createElement("span");
    badge.className = `grounded ${level === "high" ? "" : level}`;
    badge.title = `${grounded.label} · ${Math.round(
      grounded.confidence * 100
    )}% (${grounded.model})`;
    badge.innerHTML = `<span class="dot"></span>${grounded.label} · ${Math.round(
      grounded.confidence * 100
    )}%`;
    meta.appendChild(badge);
  }

  wrapper.appendChild(meta);
}

async function sendMessage(message) {
  if (!sessionId) {
    showError("Summarise a URL first.");
    return;
  }
  if (chatting) return;
  chatting = true;
  clearError();
  els.chatBtn.disabled = true;

  const empty = els.messages.querySelector(".empty-chat");
  if (empty) empty.remove();

  addMessage("user", message);
  const typing = addTyping();
  els.chatInput.value = "";
  autoGrow();

  try {
    const data = await api("/api/chat", {
      method: "POST",
      body: JSON.stringify({ session_id: sessionId, message }),
    });
    typing.remove();
    const wrapper = addMessage("assistant", data.answer);
    addMeta(wrapper, data.model, data.grounded);
  } catch (error) {
    typing.remove();
    showError(error.message);
  } finally {
    chatting = false;
    els.chatBtn.disabled = false;
    els.chatInput.focus();
  }
}

function autoGrow() {
  els.chatInput.style.height = "auto";
  els.chatInput.style.height = `${Math.min(els.chatInput.scrollHeight, 140)}px`;
}

els.ingestForm.addEventListener("submit", (event) => {
  event.preventDefault();
  const url = els.url.value.trim();
  if (url) ingest(url);
});

els.tabSummary.addEventListener("click", () => selectTab("summary"));
els.tabSource.addEventListener("click", () => selectTab("source"));

els.chatForm.addEventListener("submit", (event) => {
  event.preventDefault();
  const message = els.chatInput.value.trim();
  if (message) sendMessage(message);
});

els.chatInput.addEventListener("input", autoGrow);
els.chatInput.addEventListener("keydown", (event) => {
  if (event.key === "Enter" && !event.shiftKey) {
    event.preventDefault();
    els.chatForm.requestSubmit();
  }
});

(async function init() {
  autoGrow();
  try {
    const health = await api("/api/health");
    const models = health.models;
    els.modelNote.textContent = `${models.summariser} · ${models.chat}`;
    if (!health.keys.openrouter || !health.keys.firecrawl) {
      showError(
        "Add OPENROUTER_API_KEY and FIRECRAWL_API_KEY to .env, then restart the server."
      );
    }
  } catch {
    showError("Server is not responding.");
  }
})();
