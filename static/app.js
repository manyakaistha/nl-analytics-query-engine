'use strict';

    // -----------------------------------------------------------------------
    // State
    // -----------------------------------------------------------------------
    const chatContainer = document.getElementById('chat-container');
    const queryForm = document.getElementById('query-form');
    const queryInput = document.getElementById('query-input');
    const sendBtn = document.getElementById('send-btn');
    const welcomeMessage = document.getElementById('welcome-message');
    const suggestionsEl = document.getElementById('suggestions');
    const modelSelect = document.getElementById('model-select');
    const AVAILABLE_MODELS = [
        'openai/gpt-oss-120b',
        'openai/gpt-oss-20b',
        'qwen/qwen3.8-27b',
    ];
    const DEFAULT_MODEL = AVAILABLE_MODELS[0];
    const MODEL_STORAGE_KEY = 'aqe-selected-model';
    const HISTORY_STORAGE_KEY = 'aqe-session-history-v2';
    let sessionHistory = [];
    let historyDock;
    function readStorage(storage, key) { try { return window[storage].getItem(key); } catch { return null; } }
    function writeStorage(storage, key, value) { try { window[storage].setItem(key, value); } catch { /* Optional browser persistence. */ } }

    const SUGGESTIONS = [
        { label: 'Totals', queries: ['Total sales in India for March', 'Average order value by region'] },
        { label: 'Rankings', queries: ['Top product in each region', 'Revenue of top 3 customers per region'] },
        { label: 'Targets', queries: ['Which region missed its target in Feb?', 'Q1 target attainment by region'] },
        { label: 'Mix & trends', queries: ['Sales contribution % by category', 'Month-over-month revenue growth'] },
    ];

    let isProcessing = false;

    // -----------------------------------------------------------------------
    // Initialize
    // -----------------------------------------------------------------------
    function init() {
        initModelSelect();
        try { sessionStorage.removeItem('aqe-groq-api-key'); } catch {}
        renderSuggestions();
        queryForm.addEventListener('submit', handleSubmit);
        modelSelect.addEventListener('change', onModelChange);
        document.querySelectorAll('[data-action="new-chat"]').forEach(button => button.addEventListener('click', newChat));
        suggestionsEl.addEventListener('click', event => {
            const button = event.target.closest('[data-query]');
            if (button) submitQuery(button.dataset.query);
        });
        try {
            const saved = JSON.parse(readStorage('sessionStorage', HISTORY_STORAGE_KEY) || '[]');
            sessionHistory = Array.isArray(saved) ? saved.filter(item => typeof item.query === 'string' && typeof item.generated_sql === 'string').slice(-10) : [];
        } catch { sessionHistory = []; }
        historyDock = ChatHistory.create({ initialTurns: sessionHistory, onOpen: showConversation });
        sessionHistory = historyDock.getActiveTurns();
        if (sessionHistory.length) {
            welcomeMessage.hidden = true;
            sessionHistory.forEach(data => { appendMessage('user', data.query); appendAIResponse(data); });
        }
    }

    function showConversation(turns) {
        if (isProcessing) return false;
        sessionHistory = turns.slice(-10);
        writeStorage('sessionStorage', HISTORY_STORAGE_KEY, JSON.stringify(sessionHistory));
        [...chatContainer.children].forEach(child => { if (child !== welcomeMessage) child.remove(); });
        welcomeMessage.hidden = sessionHistory.length > 0;
        sessionHistory.forEach(data => { appendMessage('user', data.query); appendAIResponse(data); });
        chatContainer.scrollTop = 0;
        return true;
    }

    function newChat() {
        if (isProcessing) return;
        historyDock?.startNew();
        sessionHistory = [];
        writeStorage('sessionStorage', HISTORY_STORAGE_KEY, '[]');
        [...chatContainer.children].forEach(child => { if (child !== welcomeMessage) child.remove(); });
        welcomeMessage.hidden = false;
        chatContainer.scrollTop = 0;
        queryInput.value = '';
        queryInput.focus();
    }

    function initModelSelect() {
        modelSelect.innerHTML = AVAILABLE_MODELS
            .map(m => `<option value="${m}">${m}</option>`)
            .join('');

        const saved = readStorage('localStorage', MODEL_STORAGE_KEY);
        const selected = AVAILABLE_MODELS.includes(saved) ? saved : DEFAULT_MODEL;
        modelSelect.value = selected;
        writeStorage('localStorage', MODEL_STORAGE_KEY, selected);
        fetch('/api/models').then(response => response.json()).then(data => {
            if (!Array.isArray(data.models) || !data.models.length) return;
            AVAILABLE_MODELS.splice(0, AVAILABLE_MODELS.length, ...data.models);
            modelSelect.replaceChildren(...data.models.map(model => {
                const option = document.createElement('option'); option.value = model; option.textContent = model; return option;
            }));
            modelSelect.value = data.models.includes(saved) ? saved : data.default;
            writeStorage('localStorage', MODEL_STORAGE_KEY, modelSelect.value);
        }).catch(() => {});
    }

    function onModelChange() {
        writeStorage('localStorage', MODEL_STORAGE_KEY, modelSelect.value);
    }

    function getSelectedModel() {
        return AVAILABLE_MODELS.includes(modelSelect.value) ? modelSelect.value : DEFAULT_MODEL;
    }

    function renderSuggestions() {
        suggestionsEl.innerHTML = SUGGESTIONS.map(group => `
            <div class="suggestion-card rounded-3xl bg-white/70 border border-ink-200 p-4">
                <div class="section-label mb-2 px-1">${group.label}</div>
                <div class="flex flex-col gap-1">
                    ${group.queries.map(q => `
                        <button type="button" class="chip text-left px-3 py-2 rounded-xl text-[0.85rem] text-ink-700 border border-transparent cursor-pointer flex items-center justify-between gap-2"
                                data-query="${escapeHtml(q).replace(/"/g, '&quot;')}">
                            <span>${q}</span>
                            <span class="text-ink-300">→</span>
                        </button>`).join('')}
                </div>
            </div>
        `).join('');
    }

    // -----------------------------------------------------------------------
    // Submit
    // -----------------------------------------------------------------------
    async function handleSubmit(e) {
        e.preventDefault();
        const query = queryInput.value.trim();
        if (!query || isProcessing) return;
        await submitQuery(query);
    }

    async function submitQuery(query) {
        if (isProcessing) return;
        query = String(query).trim();
        if (!query || query.length > 1000) return;
        isProcessing = true;
        historyDock?.setBusy(true);
        sendBtn.disabled = true;
        queryInput.disabled = true;
        modelSelect.disabled = true;
        queryInput.value = '';

        // Hide welcome
        if (welcomeMessage) {
            welcomeMessage.hidden = true;
        }

        // Add user message
        appendMessage('user', query);

        // Add loading indicator
        const loadingEl = appendLoading();

        const controller = new AbortController();
        const timeout = setTimeout(() => controller.abort(), 70000);
        try {
            const res = await fetch('/api/query', {
                method: 'POST',
                headers: { 'Content-Type': 'application/json' },
                body: JSON.stringify({ query, model: getSelectedModel() }),
                signal: controller.signal,
            });

            if (!res.ok) {
                const err = await res.json().catch(() => ({ detail: 'Unknown error' }));
                throw new Error(typeof err.detail === 'string' ? err.detail : `The query could not be completed (HTTP ${res.status}).`);
            }

            const data = await res.json();
            loadingEl.remove();
            const renderStart = performance.now();
            appendAIResponse(data);
            data.frontend_render_ms = performance.now() - renderStart;
            sessionHistory.push(data);
            sessionHistory = sessionHistory.slice(-10);
            historyDock?.record(sessionHistory);
            writeStorage('sessionStorage', HISTORY_STORAGE_KEY, JSON.stringify(sessionHistory));
        } catch (err) {
            loadingEl.remove();
            appendMessage('error', err.name === 'AbortError' ? 'This analysis took too long. Please try a simpler question.' : `Error: ${err.message}`);
        } finally {
            clearTimeout(timeout);
            isProcessing = false;
            historyDock?.setBusy(false);
            sendBtn.disabled = false;
            queryInput.disabled = false;
            modelSelect.disabled = false;
            queryInput.focus();
        }
    }

    // -----------------------------------------------------------------------
    // Message rendering
    // -----------------------------------------------------------------------
    function appendMessage(type, content) {
        const wrapper = document.createElement('div');
        wrapper.className = `flex ${type === 'user' ? 'justify-end' : 'justify-start'} animate-slide-up`;

        const bubble = document.createElement('div');

        if (type === 'user') {
            bubble.className = 'max-w-[80%] px-5 py-3 rounded-[1.75rem] bg-accent-600 text-ink-50 text-[0.95rem] shadow-sm';
            bubble.textContent = content;
        } else if (type === 'error') {
            bubble.className = 'max-w-[80%] px-5 py-3 rounded-[1.75rem] glass text-red-700 text-sm';
            bubble.textContent = content;
        }

        wrapper.appendChild(bubble);
        chatContainer.appendChild(wrapper);
        while (chatContainer.children.length > 21) {
            const oldest = [...chatContainer.children].find(child => child !== welcomeMessage);
            if (oldest) oldest.remove(); else break;
        }
        scrollToBottom();
    }

    function appendLoading() {
        const wrapper = document.createElement('div');
        wrapper.className = 'flex justify-start animate-slide-up';
        wrapper.id = 'loading-indicator';
        wrapper.setAttribute('role', 'status');

        wrapper.innerHTML = `
            <div class="glass px-5 py-3 rounded-full flex items-center gap-2">
                <div class="flex gap-1">
                    <span class="loading-dot w-2 h-2 rounded-full bg-accent-400"></span>
                    <span class="loading-dot w-2 h-2 rounded-full bg-accent-400"></span>
                    <span class="loading-dot w-2 h-2 rounded-full bg-accent-400"></span>
                </div>
                <span class="text-xs text-ink-500 ml-1">Analyzing…</span>
            </div>
        `;

        chatContainer.appendChild(wrapper);
        while (chatContainer.children.length > 21) {
            const oldest = [...chatContainer.children].find(child => child !== welcomeMessage);
            if (oldest) oldest.remove(); else break;
        }
        scrollToBottom();
        return wrapper;
    }

    function appendAIResponse(data) {
        const wrapper = document.createElement('div');
        wrapper.className = 'flex justify-start min-w-0 animate-slide-up';

        const bubble = document.createElement('div');
        bubble.className = 'w-full max-w-[92%] min-w-0 glass rounded-[1.75rem] overflow-hidden';

        // Confidence badge
        const conf = data.confidence_score;
        let badgeColor, badgeLabel;
        if (conf >= 0.8) {
            badgeColor = 'bg-[#eef0e2] text-[#4d6b1f] border-[#d5dcb8]';
            badgeLabel = 'High confidence';
        } else if (conf >= 0.5) {
            badgeColor = 'bg-amber-50 text-amber-800 border-amber-200';
            badgeLabel = 'Medium confidence';
        } else {
            badgeColor = 'bg-red-50 text-red-700 border-red-200';
            badgeLabel = 'Low confidence';
        }

        // Build HTML
        let html = `
            <div class="px-6 pt-5 pb-5">
                <div class="flex flex-wrap items-center gap-2 mb-3">
                    <span class="instrument-serif-regular text-2xl text-ink-900 mr-auto leading-none">Answer</span>
                    <span class="inline-flex items-center px-3 py-1 rounded-full text-[0.7rem] font-medium border ${badgeColor}" title="Model estimate; not calibrated">
                        ${badgeLabel} · ${(conf * 100).toFixed(0)}%
                    </span>
                    ${data.model ? `
                    <span class="inline-flex items-center gap-1 px-3 py-1 rounded-full text-[0.7rem] font-medium bg-ink-50 text-ink-500 border border-ink-200" title="Model used to generate this answer">
                        <svg class="w-3 h-3" fill="none" viewBox="0 0 24 24" stroke="currentColor" stroke-width="2">
                            <path stroke-linecap="round" stroke-linejoin="round" d="M9.75 3.104v5.714a2.25 2.25 0 0 1-.659 1.591L5 14.5M9.75 3.104c-.251.023-.501.05-.75.082m.75-.082a24.301 24.301 0 0 1 4.5 0m0 0v5.714c0 .597.237 1.17.659 1.591L19.8 15.3M14.25 3.104c.251.023.501.05.75.082M19.8 15.3l-1.57.393A9.065 9.065 0 0 1 12 15a9.065 9.065 0 0 0-6.23.693L5 14.5m14.8.8 1.402 1.402c1.232 1.232.65 3.318-1.067 3.611l-.772.13A18.142 18.142 0 0 1 12 21a18.142 18.142 0 0 1-7.363-1.457l-.772-.13c-1.717-.293-2.3-2.379-1.067-3.61L5 14.5" />
                        </svg>
                        ${escapeHtml(data.model)}
                    </span>` : ''}
                    <span class="inline-flex items-center gap-1 px-3 py-1 rounded-full text-[0.7rem] font-medium bg-ink-50 text-ink-500 border border-ink-200" title="Response time">
                        <svg class="w-3 h-3" fill="none" viewBox="0 0 24 24" stroke="currentColor" stroke-width="2">
                            <path stroke-linecap="round" stroke-linejoin="round" d="M12 6v6h4.5m4.5 0a9 9 0 1 1-18 0 9 9 0 0 1 18 0Z" />
                        </svg>
                        ${formatDuration(data.response_time_ms)}
                    </span>
                    ${data.cache_hit ? `
                    <span class="inline-flex items-center gap-1 px-3 py-1 rounded-full text-[0.7rem] font-medium bg-accent-600/10 text-accent-700 border border-accent-600/20" title="Served from a previous identical query">
                        <svg class="w-3 h-3" fill="none" viewBox="0 0 24 24" stroke="currentColor" stroke-width="2">
                            <path stroke-linecap="round" stroke-linejoin="round" d="m3.75 13.5 10.5-11.25L12 10.5h8.25L9.75 21.75 12 13.5H3.75Z" />
                        </svg>
                        Cached
                    </span>` : ''}
                    ${!data.cache_hit && data.attempts > 1 ? `<span class="text-[0.7rem] text-ink-400">${data.attempts} attempts</span>` : ''}
                </div>
                <p class="text-[0.95rem] text-ink-800 leading-relaxed">${escapeHtml(data.explanation)}</p>
            </div>
        `;

        // Result: table or scalar
        const result = data.result;
        if (Array.isArray(result) && result.length > 0) {
            html += `
                <div class="px-6 pt-4 flex items-baseline justify-between border-t border-ink-100">
                    <span class="section-label">Result</span>
                    <span class="text-[0.7rem] text-ink-400">${result.length} row${result.length === 1 ? '' : 's'}</span>
                </div>`;
            html += renderTable(result);
        } else if (typeof result === 'string' && result !== 'No results found.') {
            html += `
                <div class="px-6 py-4 border-t border-ink-100">
                    <span class="section-label">Result</span>
                    <p class="instrument-serif-regular text-5xl text-ink-900 mt-1 leading-tight">${escapeHtml(formatScalar(result))}</p>
                </div>
            `;
        } else if (result === 'No results found.') {
            html += `
                <div class="px-5 py-3 border-t border-ink-100">
                    <p class="text-sm text-ink-500 italic">No results found.</p>
                </div>
            `;
        }

        // SQL (formatted + highlighted)
        const sqlId = `sql-${crypto.randomUUID()}`;
        html += `
            <details class="border-t border-ink-100" open>
                <summary class="px-6 py-3 cursor-pointer select-none flex items-center justify-between">
                    <span class="section-label flex items-center gap-1.5">
                        <svg class="w-3.5 h-3.5" fill="none" viewBox="0 0 24 24" stroke="currentColor" stroke-width="2">
                            <path stroke-linecap="round" stroke-linejoin="round" d="M17.25 6.75 22.5 12l-5.25 5.25m-10.5 0L1.5 12l5.25-5.25m7.5-3-4.5 16.5" />
                        </svg>
                        Generated SQL
                    </span>
                    <button type="button" class="px-3 py-1 rounded-full text-[0.7rem] text-ink-500 border border-ink-200 hover:bg-ink-50 hover:text-ink-800 transition-colors"
                            data-copy-sql="${sqlId}">Copy</button>
                </summary>
                <div class="px-5 pb-4">
                    <pre class="sql-block" id="${sqlId}">${renderSql(data.generated_sql)}</pre>
                </div>
            </details>
        `;

        // Logic collapsible
        if (data.generated_logic) {
            html += `
                <details class="border-t border-ink-100">
                    <summary class="section-label px-6 py-3 cursor-pointer hover:text-ink-700 transition-colors select-none flex items-center gap-1.5">
                        <svg class="w-3.5 h-3.5" fill="none" viewBox="0 0 24 24" stroke="currentColor" stroke-width="2">
                            <path stroke-linecap="round" stroke-linejoin="round" d="M12 18v-5.25m0 0a6.01 6.01 0 0 0 1.5-.189m-1.5.189a6.01 6.01 0 0 1-1.5-.189m3.75 7.478a12.06 12.06 0 0 1-4.5 0m3.75 2.383a14.406 14.406 0 0 1-3 0M14.25 18v-.192c0-.983.658-1.823 1.508-2.316a7.5 7.5 0 1 0-7.517 0c.85.493 1.509 1.333 1.509 2.316V18" />
                        </svg>
                        Reasoning
                    </summary>
                    <div class="px-6 pb-4">
                        ${renderReasoning(data.generated_logic)}
                    </div>
                </details>
            `;
        }

        // Feedback buttons
        const responseId = `resp-${crypto.randomUUID()}`;
        html += `
            <div class="flex items-center gap-1 px-5 py-2.5 border-t border-ink-100" id="${responseId}">
                <span class="text-[0.65rem] text-ink-400 mr-auto feedback-status">Was this helpful?</span>
                <button type="button" data-download class="px-3 py-1 rounded-full text-[0.7rem] text-ink-500 border border-ink-200 hover:bg-ink-50">Download CSV</button>
                <button class="feedback-btn p-2 rounded-full hover:bg-ink-100 text-ink-400" title="Helpful" aria-label="Helpful"
                        data-feedback="positive">
                    <svg class="w-4 h-4" fill="none" viewBox="0 0 24 24" stroke="currentColor" stroke-width="2">
                        <path stroke-linecap="round" stroke-linejoin="round" d="M6.633 10.25c.806 0 1.533-.446 2.031-1.08a9.041 9.041 0 0 1 2.861-2.4c.723-.384 1.35-.956 1.653-1.715a4.498 4.498 0 0 0 .322-1.672V3a.75.75 0 0 1 .75-.75 2.25 2.25 0 0 1 2.25 2.25c0 1.152-.26 2.243-.723 3.218-.266.558.107 1.282.725 1.282m0 0h3.126c1.026 0 1.945.694 2.054 1.715.045.422.068.85.068 1.285a11.95 11.95 0 0 1-2.649 7.521c-.388.482-.987.729-1.605.729H13.48c-.483 0-.964-.078-1.423-.23l-3.114-1.04a4.501 4.501 0 0 0-1.423-.23H5.904m10.598-9.75H14.25M5.904 18.5c.083.205.173.405.27.602.197.4-.078.898-.523.898h-.908c-.889 0-1.713-.518-1.972-1.368a12 12 0 0 1-.521-3.507c0-1.553.295-3.036.831-4.398C3.387 9.953 4.167 9.5 5 9.5h1.053c.472 0 .745.556.5.96a8.958 8.958 0 0 0-1.302 4.665c0 1.194.232 2.333.654 3.375Z" />
                    </svg>
                </button>
                <button class="feedback-btn p-2 rounded-full hover:bg-ink-100 text-ink-400" title="Not helpful" aria-label="Not helpful"
                        data-feedback="negative">
                    <svg class="w-4 h-4" fill="none" viewBox="0 0 24 24" stroke="currentColor" stroke-width="2">
                        <path stroke-linecap="round" stroke-linejoin="round" d="M7.498 15.25H4.372c-1.026 0-1.945-.694-2.054-1.715a12.137 12.137 0 0 1-.068-1.285c0-2.848.992-5.464 2.649-7.521C5.287 4.247 5.886 4 6.504 4h4.016a4.5 4.5 0 0 1 1.423.23l3.114 1.04a4.5 4.5 0 0 0 1.423.23h1.294M7.498 15.25c.618 0 .991.724.725 1.282A7.471 7.471 0 0 0 7.5 19.75 2.25 2.25 0 0 0 9.75 22a.75.75 0 0 0 .75-.75v-.633c0-.573.11-1.14.322-1.672.304-.76.93-1.33 1.653-1.715a9.04 9.04 0 0 0 2.86-2.4c.498-.634 1.226-1.08 2.032-1.08h.384m-10.253 1.5H9.7m8.075-9.75c.01.05.027.1.05.148.593 1.2.925 2.55.925 3.977 0 1.487-.36 2.89-.999 4.125m.023-8.25c-.076-.365.183-.75.575-.75h.908c.889 0 1.713.518 1.972 1.368.339 1.11.521 2.287.521 3.507 0 1.553-.295 3.036-.831 4.398-.306.774-1.086 1.227-1.918 1.227h-1.053c-.472 0-.745-.556-.5-.96a8.95 8.95 0 0 0 .303-.54" />
                    </svg>
                </button>
            </div>
        `;

        bubble.innerHTML = html;
        bubble.querySelector('[data-copy-sql]').addEventListener('click', event => {
            event.preventDefault(); copySql(sqlId, event.currentTarget);
        });
        bubble.querySelectorAll('[data-feedback]').forEach(button => button.addEventListener('click', () => sendFeedback(responseId, data.feedback_id, button.dataset.feedback, button)));
        bubble.querySelector('[data-download]').addEventListener('click', () => downloadCSV(data));
        wrapper.appendChild(bubble);
        chatContainer.appendChild(wrapper);
        while (chatContainer.children.length > 21) {
            const oldest = [...chatContainer.children].find(child => child !== welcomeMessage);
            if (oldest) oldest.remove(); else break;
        }
        scrollToBottom();
    }

    // -----------------------------------------------------------------------
    // Table renderer
    // -----------------------------------------------------------------------
    function renderTable(rows) {
        if (!rows.length) return '';
        const keys = Object.keys(rows[0]);

        let html = `
            <div class="px-5 pt-2 pb-4 result-scroll" tabindex="0" role="region" aria-label="Query results">
                <div class="rounded-2xl border border-ink-200 min-w-max overflow-hidden"><table class="result-table w-full text-left">
                    <thead><tr>
        `;
        keys.forEach(k => {
            html += `<th>${escapeHtml(k)}</th>`;
        });
        html += `</tr></thead><tbody>`;

        rows.slice(0, 200).forEach(row => {
            html += '<tr>';
            keys.forEach(k => {
                const val = row[k];
                const formatted = formatValue(val);
                html += `<td>${formatted}</td>`;
            });
            html += '</tr>';
        });

        html += '</tbody></table></div></div>';
        return html;
    }

    function formatValue(val) {
        if (val === null || val === undefined) return '<span class="text-ink-300">NULL</span>';
        if (typeof val === 'string' && /^-?\d+\.\d+$/.test(val)) val = Number(val);
        if (typeof val === 'number') {
            // Format numbers nicely
            if (Number.isInteger(val)) return val.toLocaleString();
            return val.toLocaleString(undefined, { minimumFractionDigits: 2, maximumFractionDigits: 2 });
        }
        return escapeHtml(String(val));
    }

    // -----------------------------------------------------------------------
    // Feedback
    // -----------------------------------------------------------------------
    async function sendFeedback(responseId, feedbackId, feedback, btnEl) {
        const container = document.getElementById(responseId);
        if (!container) return;
        const statusEl = container.querySelector('.feedback-status');

        // Visual feedback
        const allBtns = container.querySelectorAll('.feedback-btn');
        allBtns.forEach(b => {
            b.classList.remove('active-positive', 'active-negative');
            b.disabled = true;
        });
        btnEl.classList.add(feedback === 'positive' ? 'active-positive' : 'active-negative');
        if (statusEl) statusEl.textContent = 'Saving…';

        try {
            const res = await fetch('/api/feedback', {
                method: 'POST',
                headers: { 'Content-Type': 'application/json' },
                body: JSON.stringify({ feedback_id: feedbackId, feedback }),
            });
            if (!res.ok) throw new Error(res.status === 404 ? 'Feedback expired — run this query again' : 'Could not save feedback — try again');
            if (statusEl) statusEl.textContent = 'Thanks, feedback saved ✓';
        } catch (err) {
            console.error('Feedback error:', err);
            if (statusEl) statusEl.textContent = err.message;
            allBtns.forEach(b => { b.disabled = false; });
            btnEl.classList.remove('active-positive', 'active-negative');
        }
    }

    // -----------------------------------------------------------------------
    // Utilities
    // -----------------------------------------------------------------------
    function escapeHtml(str) {
        const div = document.createElement('div');
        div.textContent = str;
        return div.innerHTML;
    }

    function renderReasoning(text) {
        if (!text) return '';

        // Split "1. ... 2. ... 3. ..." into individual numbered steps.
        // Model output is one paragraph with inline "N. " markers, not real newlines.
        // Only treat "N." as a step boundary when N is the next expected integer —
        // otherwise numbers inside the reasoning itself (e.g. "* 100.") get misread as steps.
        const marker = /(?:^|(?<=\s))(\d+)\.\s+/g;
        const boundaries = [];
        let m, next = 1;
        while ((m = marker.exec(text)) !== null) {
            if (Number(m[1]) === next) {
                boundaries.push({ index: m.index, matchEnd: m.index + m[0].length });
                next += 1;
            }
        }
        const steps = boundaries.map((b, i) => {
            const end = i + 1 < boundaries.length ? boundaries[i + 1].index : text.length;
            return text.slice(b.matchEnd, end).trim();
        });

        const highlight = s => escapeHtml(s).replace(
            /\b[a-z][a-z0-9]*(?:_[a-z0-9]+)+\b/g,
            m => `<code class="reasoning-code">${m}</code>`
        );

        if (steps.length < 2) {
            return `<p class="text-sm text-ink-600 leading-relaxed">${highlight(text)}</p>`;
        }

        return `
            <ol class="text-sm text-ink-600 leading-relaxed space-y-2 list-none">
                ${steps.map((step, i) => `
                    <li class="flex gap-3">
                        <span class="flex-none w-5 h-5 rounded-full bg-ink-100 text-ink-500 text-[0.7rem] font-medium flex items-center justify-center mt-0.5">${i + 1}</span>
                        <span>${highlight(step)}</span>
                    </li>
                `).join('')}
            </ol>
        `;
    }

    function renderSql(sql) {
        let pretty = sql || '';
        try {
            if (window.sqlFormatter) {
                pretty = sqlFormatter.format(pretty, { language: 'duckdb', keywordCase: 'upper', tabWidth: 2 });
            }
        } catch (e) {
            console.warn('SQL formatting failed, showing raw SQL:', e);
        }
        if (window.hljs) {
            return hljs.highlight(pretty, { language: 'sql' }).value;
        }
        return escapeHtml(pretty);
    }

    async function copySql(id, btn) {
        const text = document.getElementById(id)?.innerText || '';
        try {
            await navigator.clipboard.writeText(text);
            btn.textContent = 'Copied';
            setTimeout(() => { btn.textContent = 'Copy'; }, 1500);
        } catch { btn.textContent = 'Select SQL to copy'; }
    }

    function csvCell(value) {
        let text = value == null ? '' : String(value);
        if (/^[=+\-@\t\r]/.test(text)) text = "'" + text;
        return '"' + text.replaceAll('"', '""') + '"';
    }

    function downloadCSV(data) {
        const rows = Array.isArray(data.result) ? data.result : [{ result: data.result }];
        if (!rows.length) return;
        const columns = Object.keys(rows[0]);
        const csv = [columns, ...rows.map(row => columns.map(key => row[key]))].map(row => row.map(csvCell).join(',')).join('\r\n');
        const url = URL.createObjectURL(new Blob([csv], {type:'text/csv;charset=utf-8'}));
        const link = document.createElement('a'); link.href = url; link.download = 'analytics-results.csv'; link.click();
        setTimeout(() => URL.revokeObjectURL(url), 1000);
    }

    function formatScalar(val) {
        const n = Number(val);
        if (val !== '' && Number.isFinite(n)) {
            return n.toLocaleString(undefined, { maximumFractionDigits: 2 });
        }
        return val;
    }

    function formatDuration(ms) {
        if (ms === undefined || ms === null) return '—';
        if (ms < 1000) return `${ms} ms`;
        return `${(ms / 1000).toFixed(2)} s`;
    }

    function scrollToBottom() {
        requestAnimationFrame(() => {
            if (welcomeMessage.hidden) chatContainer.scrollTop = chatContainer.scrollHeight;
        });
    }

    // -----------------------------------------------------------------------
    // Boot
    // -----------------------------------------------------------------------
    init();
