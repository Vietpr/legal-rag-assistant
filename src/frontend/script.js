const API_URL = "/ask";

// DOM elements
const chatArea = document.getElementById("chatArea");
const welcome = document.getElementById("welcome");
const inputForm = document.getElementById("inputForm");
const questionInput = document.getElementById("questionInput");
const sendBtn = document.getElementById("sendBtn");
const versionFilter = document.getElementById("versionFilter");
const lawTypeFilter = document.getElementById("lawTypeFilter");

let isLoading = false;

// Event Listeners  

inputForm.addEventListener("submit", (e) => {
    e.preventDefault();
    handleSend();
});

// Auto-resize textarea
questionInput.addEventListener("input", () => {
    questionInput.style.height = "auto";
    questionInput.style.height = Math.min(questionInput.scrollHeight, 120) + "px";
});

// Enter to send (Shift+Enter for new line)
questionInput.addEventListener("keydown", (e) => {
    if (e.key === "Enter" && !e.shiftKey) {
        e.preventDefault();
        handleSend();
    }
});

// Suggestion Chips 

function useSuggestion(chip) {
    questionInput.value = chip.textContent;
    questionInput.focus();
    handleSend();
}

// Main Send Handler 

async function handleSend() {
    const question = questionInput.value.trim();
    if (!question || isLoading) return;

    // Hide welcome
    if (welcome) {
        welcome.style.display = "none";
    }

    // Add user message
    appendUserMessage(question);

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

        // Add assistant message
        appendAssistantMessage(data.answer, data.citations);
    } catch (error) {
        loadingEl.remove();
        appendErrorMessage(error.message || "Đã xảy ra lỗi khi kết nối tới server.");
    } finally {
        setLoading(false);
    }
}

//  Message Rendering 

function appendUserMessage(text) {
    const div = document.createElement("div");
    div.className = "message message-user";
    div.innerHTML = `<div class="message-bubble">${escapeHtml(text)}</div>`;
    chatArea.appendChild(div);
    scrollToBottom();
}

function appendAssistantMessage(answer, citations) {
    const div = document.createElement("div");
    div.className = "message message-assistant";

    // Format answer (basic markdown-like: **bold**, newlines)
    const formattedAnswer = formatAnswer(answer);

    let html = `
        <div class="message-label">Trợ lý Pháp lý AI</div>
        <div class="message-bubble">${formattedAnswer}</div>
    `;

    // Citations
    if (citations && citations.length > 0) {
        html += `
            <div class="citations">
                <div class="citations-header" onclick="toggleCitations(this)">
                    <span class="arrow open">&rsaquo;</span>
                    Nguon trich dan (${citations.length})
                </div>
                <div class="citations-list">
                    ${citations.map(renderCitation).join("")}
                </div>
            </div>
        `;
    }

    div.innerHTML = html;
    chatArea.appendChild(div);
    scrollToBottom();
}

function appendErrorMessage(text) {
    const div = document.createElement("div");
    div.className = "message message-assistant";
    div.innerHTML = `
        <div class="message-label">Lỗi</div>
        <div class="message-bubble error-bubble">[Loi] ${escapeHtml(text)}</div>
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

//  Citation Rendering

function renderCitation(c) {
    const lawTitle = c.law_title || "N/A";
    const article = c.article || "N/A";
    const lawType = c.law_type || "";
    const year = c.issued_year || "";
    const version = c.version === "update_law" ? "Sửa đổi" : c.version === "origin_law" ? "Gốc" : c.version || "";
    const distance = c.distance != null ? c.distance.toFixed(3) : "";

    return `
        <div class="citation-card">
            <div class="citation-law">${escapeHtml(lawTitle)}</div>
            <div class="citation-article">${escapeHtml(article)}</div>
            <div class="citation-meta">
                ${lawType ? `<span>Loai: ${escapeHtml(lawType)}</span>` : ""}
                ${year ? `<span>Nam: ${year}</span>` : ""}
                ${version ? `<span>Phien ban: ${escapeHtml(version)}</span>` : ""}
                ${distance ? `<span>Do tuong dong: ${distance}</span>` : ""}
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

// Utilities 

function formatAnswer(text) {
    if (!text) return "";

    return text
        // Bold: **text**
        .replace(/\*\*(.*?)\*\*/g, "<strong>$1</strong>")
        // Paragraphs
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
