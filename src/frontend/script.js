const API_URL = "/ask";
const STORAGE_KEY = "legal_rag_chats";

// DOM elements
const chatArea = document.getElementById("chatArea");
const welcome = document.getElementById("welcome");
const inputForm = document.getElementById("inputForm");
const questionInput = document.getElementById("questionInput");
const sendBtn = document.getElementById("sendBtn");
const versionFilter = document.getElementById("versionFilter");
const lawTypeFilter = document.getElementById("lawTypeFilter");
const sidebar = document.getElementById("sidebar");
const sidebarOverlay = document.getElementById("sidebarOverlay");
const sidebarToggle = document.getElementById("sidebarToggle");
const sidebarList = document.getElementById("sidebarList");
const newChatBtn = document.getElementById("newChatBtn");
const clearAllBtn = document.getElementById("clearAllBtn");

let isLoading = false;
let currentChatId = null;
let chats = {}; // { id: { id, title, messages: [{role, content, citations?}], createdAt } }

// ───────── LocalStorage ─────────

function saveChats() {
    localStorage.setItem(STORAGE_KEY, JSON.stringify(chats));
}

function loadChats() {
    try {
        const raw = localStorage.getItem(STORAGE_KEY);
        if (raw) {
            chats = JSON.parse(raw);
        }
    } catch (e) {
        chats = {};
    }
}

// ───────── Chat Management ─────────

function generateId() {
    return Date.now().toString(36) + Math.random().toString(36).substr(2, 5);
}

function createNewChat() {
    const id = generateId();
    chats[id] = {
        id: id,
        title: "Cuộc trò chuyện mới",
        messages: [],
        createdAt: Date.now(),
    };
    saveChats();
    switchToChat(id);
    renderSidebar();
}

function switchToChat(chatId) {
    currentChatId = chatId;
    renderChatArea();
    renderSidebar();
    closeSidebarMobile();
}

function deleteChat(chatId, event) {
    event.stopPropagation();
    delete chats[chatId];
    saveChats();

    if (currentChatId === chatId) {
        const ids = getSortedChatIds();
        if (ids.length > 0) {
            switchToChat(ids[0]);
        } else {
            createNewChat();
        }
    } else {
        renderSidebar();
    }
}

function clearAllChats() {
    if (!confirm("Bạn có chắc muốn xóa tất cả cuộc trò chuyện?")) return;
    chats = {};
    saveChats();
    createNewChat();
}

function getSortedChatIds() {
    return Object.keys(chats).sort((a, b) => (chats[b].createdAt || 0) - (chats[a].createdAt || 0));
}

function generateTitle(question) {
    // Take first ~50 chars of the question as the chat title
    const clean = question.trim().replace(/\s+/g, " ");
    return clean.length > 50 ? clean.substring(0, 50) + "…" : clean;
}

// ───────── Sidebar Rendering ─────────

function renderSidebar() {
    const ids = getSortedChatIds();
    sidebarList.innerHTML = "";

    if (ids.length === 0) {
        sidebarList.innerHTML = `<div style="padding:20px 12px;text-align:center;color:var(--text-muted);font-size:13px;">Chưa có cuộc trò chuyện nào</div>`;
        return;
    }

    ids.forEach((id) => {
        const chat = chats[id];
        const isActive = id === currentChatId;

        const item = document.createElement("button");
        item.className = `chat-item${isActive ? " active" : ""}`;
        item.onclick = () => switchToChat(id);

        item.innerHTML = `
            <svg class="chat-item-icon" viewBox="0 0 24 24" fill="none" stroke="currentColor"
                stroke-width="2" stroke-linecap="round" stroke-linejoin="round">
                <path d="M21 15a2 2 0 0 1-2 2H7l-4 4V5a2 2 0 0 1 2-2h14a2 2 0 0 1 2 2z"></path>
            </svg>
            <span class="chat-item-text">${escapeHtml(chat.title)}</span>
            <button class="chat-item-delete" title="Xóa" onclick="deleteChat('${id}', event)">
                <svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor"
                    stroke-width="2" stroke-linecap="round" stroke-linejoin="round">
                    <line x1="18" y1="6" x2="6" y2="18"></line>
                    <line x1="6" y1="6" x2="18" y2="18"></line>
                </svg>
            </button>
        `;

        sidebarList.appendChild(item);
    });
}

// ───────── Chat Area Rendering ─────────

function renderChatArea() {
    // Clear
    chatArea.innerHTML = "";

    const chat = chats[currentChatId];
    if (!chat || chat.messages.length === 0) {
        // Show welcome
        chatArea.innerHTML = `
            <div class="welcome" id="welcome">
                <div class="welcome-icon"></div>
                <h2>Xin chào! Tôi là Trợ lý Pháp lý AI</h2>
                <p>Hãy đặt câu hỏi về Luật Lao động, Việc làm, Bảo hiểm xã hội, Bảo hiểm y tế - tôi sẽ trả lời dựa trên
                    các văn bản pháp luật có trích dẫn cụ thể.</p>
                <div class="suggestions">
                    <button class="suggestion-chip" onclick="useSuggestion(this)">Điều kiện hưởng trợ cấp thất nghiệp theo Luật Việc làm 2013?</button>
                    <button class="suggestion-chip" onclick="useSuggestion(this)">Người lao động có quyền đơn phương chấm dứt hợp đồng lao động khi nào?</button>
                    <button class="suggestion-chip" onclick="useSuggestion(this)">Mức đóng bảo hiểm y tế hàng tháng là bao nhiêu?</button>
                    <button class="suggestion-chip" onclick="useSuggestion(this)">Chế độ thai sản theo Luật Bảo hiểm xã hội quy định như thế nào?</button>
                </div>
            </div>
        `;
        return;
    }

    // Render messages
    chat.messages.forEach((msg) => {
        if (msg.role === "user") {
            appendUserMessageDOM(msg.content);
        } else if (msg.role === "assistant") {
            appendAssistantMessageDOM(msg.content, msg.citations);
        }
    });

    scrollToBottom();
}

// ───────── DOM Message Helpers (no save, just render) ─────────

function appendUserMessageDOM(text) {
    const div = document.createElement("div");
    div.className = "message message-user";
    div.innerHTML = `<div class="message-bubble">${escapeHtml(text)}</div>`;
    chatArea.appendChild(div);
}

function appendAssistantMessageDOM(answer, citations) {
    const div = document.createElement("div");
    div.className = "message message-assistant";

    const formattedAnswer = formatAnswer(answer);

    let html = `
        <div class="message-label">Trợ lý Pháp lý AI</div>
        <div class="message-bubble">${formattedAnswer}</div>
    `;

    if (citations && citations.length > 0) {
        html += `
            <div class="citations">
                <div class="citations-header" onclick="toggleCitations(this)">
                    <span class="arrow open">&rsaquo;</span>
                    Nguồn trích dẫn (${citations.length})
                </div>
                <div class="citations-list">
                    ${citations.map(renderCitation).join("")}
                </div>
            </div>
        `;
    }

    div.innerHTML = html;
    chatArea.appendChild(div);
}

// ───────── Event Listeners ─────────

inputForm.addEventListener("submit", (e) => {
    e.preventDefault();
    handleSend();
});

questionInput.addEventListener("input", () => {
    questionInput.style.height = "auto";
    questionInput.style.height = Math.min(questionInput.scrollHeight, 120) + "px";
});

questionInput.addEventListener("keydown", (e) => {
    if (e.key === "Enter" && !e.shiftKey) {
        e.preventDefault();
        handleSend();
    }
});

newChatBtn.addEventListener("click", createNewChat);
clearAllBtn.addEventListener("click", clearAllChats);

sidebarToggle.addEventListener("click", () => {
    sidebar.classList.toggle("open");
    sidebarOverlay.classList.toggle("visible");
});

sidebarOverlay.addEventListener("click", closeSidebarMobile);

function closeSidebarMobile() {
    sidebar.classList.remove("open");
    sidebarOverlay.classList.remove("visible");
}

// ───────── Suggestion Chips ─────────

function useSuggestion(chip) {
    questionInput.value = chip.textContent;
    questionInput.focus();
    handleSend();
}

// ───────── Main Send Handler ─────────

async function handleSend() {
    const question = questionInput.value.trim();
    if (!question || isLoading) return;

    // Ensure we have a current chat
    if (!currentChatId || !chats[currentChatId]) {
        createNewChat();
    }

    const chat = chats[currentChatId];

    // Hide welcome if present
    const welcomeEl = chatArea.querySelector(".welcome");
    if (welcomeEl) welcomeEl.style.display = "none";

    // Update title on first message
    if (chat.messages.length === 0) {
        chat.title = generateTitle(question);
        renderSidebar();
    }

    // Save user message
    chat.messages.push({ role: "user", content: question });
    saveChats();

    // Render user message
    appendUserMessageDOM(question);

    // Clear input
    questionInput.value = "";
    questionInput.style.height = "auto";

    // Show loading
    const loadingEl = appendLoading();
    setLoading(true);

    try {
        const body = { question };

        const version = versionFilter.value;
        const lawType = lawTypeFilter.value;
        if (version) body.version = version;
        if (lawType) body.law_type = lawType;

        const response = await fetch(API_URL, {
            method: "POST",
            headers: { "Content-Type": "application/json" },
            body: JSON.stringify(body),
        });

        if (!response.ok) {
            throw new Error(`Server error: ${response.status}`);
        }

        const data = await response.json();

        // Remove loading
        loadingEl.remove();

        // Save assistant message
        chat.messages.push({
            role: "assistant",
            content: data.answer,
            citations: data.citations,
        });
        saveChats();

        // Render assistant message
        appendAssistantMessageDOM(data.answer, data.citations);
    } catch (error) {
        loadingEl.remove();
        const errorMsg = error.message || "Đã xảy ra lỗi khi kết nối tới server.";

        chat.messages.push({ role: "assistant", content: `[Lỗi] ${errorMsg}`, citations: [] });
        saveChats();

        appendErrorMessage(errorMsg);
    } finally {
        setLoading(false);
        scrollToBottom();
    }
}

// ───────── Error & Loading ─────────

function appendErrorMessage(text) {
    const div = document.createElement("div");
    div.className = "message message-assistant";
    div.innerHTML = `
        <div class="message-label">Lỗi</div>
        <div class="message-bubble error-bubble">[Lỗi] ${escapeHtml(text)}</div>
    `;
    chatArea.appendChild(div);
    scrollToBottom();
}

function appendLoading() {
    const div = document.createElement("div");
    div.className = "message message-assistant";
    div.innerHTML = `
        <div class="message-label">Trợ lý Pháp lý AI</div>
        <div class="loading-dots">
            <span></span><span></span><span></span>
        </div>
    `;
    chatArea.appendChild(div);
    scrollToBottom();
    return div;
}

// ───────── Citation Rendering ─────────

function renderCitation(c) {
    const lawTitle = c.law_title || "N/A";
    const article = c.article || "N/A";
    const lawType = c.law_type || "";
    const year = c.issued_year || "";
    const version = c.version === "update_law" ? "Sửa đổi" : c.version === "origin_law" ? "Gốc" : c.version || "";

    return `
        <div class="citation-card">
            <div class="citation-law">${escapeHtml(lawTitle)}</div>
            <div class="citation-article">${escapeHtml(article)}</div>
            <div class="citation-meta">
                ${lawType ? `<span>Loại: ${escapeHtml(lawType)}</span>` : ""}
                ${year ? `<span>Năm: ${year}</span>` : ""}
                ${version ? `<span>Phiên bản: ${escapeHtml(version)}</span>` : ""}
            </div>
        </div>
    `;
}

function toggleCitations(header) {
    const arrow = header.querySelector(".arrow");
    const list = header.nextElementSibling;

    if (list.style.display === "none") {
        list.style.display = "flex";
        arrow.classList.add("open");
    } else {
        list.style.display = "none";
        arrow.classList.remove("open");
    }
}

// ───────── Utilities ─────────

function formatAnswer(text) {
    if (!text) return "";

    return text
        .replace(/\*\*(.*?)\*\*/g, "<strong>$1</strong>")
        .split("\n\n")
        .map(p => `<p>${p.replace(/\n/g, "<br>")}</p>`)
        .join("");
}

function escapeHtml(text) {
    const div = document.createElement("div");
    div.textContent = text;
    return div.innerHTML;
}

function scrollToBottom() {
    requestAnimationFrame(() => {
        chatArea.scrollTop = chatArea.scrollHeight;
    });
}

function setLoading(loading) {
    isLoading = loading;
    sendBtn.disabled = loading;
    questionInput.disabled = loading;
}

// ───────── Init on page load ─────────

(function init() {
    loadChats();

    const ids = getSortedChatIds();
    if (ids.length > 0) {
        currentChatId = ids[0];
    } else {
        createNewChat();
        return; // createNewChat already calls renderSidebar + renderChatArea
    }

    renderSidebar();
    renderChatArea();
})();
