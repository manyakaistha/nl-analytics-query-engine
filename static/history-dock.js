/* Session-local chat library. Separate from query generation and response caching. */
(() => {
    'use strict';
    const STORAGE_KEY = 'aqe-chat-library-v1';
    const MAX_CHATS = 30;
    const MAX_BYTES = 2 * 1024 * 1024;
    const icon = '<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.6" aria-hidden="true"><path stroke-linecap="round" stroke-linejoin="round" d="M8 9h8M8 13h5M5 4h14a2 2 0 0 1 2 2v11a2 2 0 0 1-2 2H9l-5 3v-3H5a2 2 0 0 1-2-2V6a2 2 0 0 1 2-2Z"/></svg>';
    const clock = '<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.6" aria-hidden="true"><path stroke-linecap="round" stroke-linejoin="round" d="M3 11a9 9 0 1 1 2.7 7M3 4v7h7m2-4v5l3 2"/></svg>';
    const plus = '<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.6" aria-hidden="true"><path stroke-linecap="round" d="M12 5v14M5 12h14"/></svg>';

    function create({ initialTurns = [], onOpen }) {
        const dock = document.getElementById('history-dock');
        const recent = document.getElementById('recent-chat-list');
        const dialog = document.getElementById('chat-history-dialog');
        const all = document.getElementById('all-chat-list');
        const more = document.getElementById('history-more');
        const search = document.getElementById('history-search');
        let busy = false;
        let state = { activeId: null, chats: [] };
        try {
            const saved = JSON.parse(sessionStorage.getItem(STORAGE_KEY) || 'null');
            if (saved && Array.isArray(saved.chats)) {
                state.chats = saved.chats.filter(chat => chat && typeof chat.id === 'string' && Array.isArray(chat.turns))
                    .map(chat => ({ ...chat, turns: chat.turns.filter(turn => turn && typeof turn.query === 'string' && typeof turn.generated_sql === 'string').slice(-10) }))
                    .filter(chat => chat.turns.length).slice(0, MAX_CHATS);
                state.activeId = state.chats.some(chat => chat.id === saved.activeId) ? saved.activeId : null;
            } else if (initialTurns.length) {
                state.activeId = crypto.randomUUID();
                state.chats = [{ id: state.activeId, title: initialTurns[0].query, updatedAt: Date.now(), turns: initialTurns.slice(-10) }];
            }
        } catch { /* Storage may be disabled; keep the current tab usable. */ }

        function persist() {
            // Bound both retained result data and browser storage; never evict the active chat.
            while (new Blob([JSON.stringify(state)]).size > MAX_BYTES && state.chats.length) {
                const index = state.chats.findLastIndex(chat => chat.id !== state.activeId);
                if (index >= 0) state.chats.splice(index, 1);
                else if (state.chats[0].turns.length > 1) state.chats[0].turns.shift();
                else { state.chats = []; state.activeId = null; }
            }
            try { sessionStorage.setItem(STORAGE_KEY, JSON.stringify(state)); }
            catch { /* An in-memory history still works if the browser refuses storage. */ }
        }

        function age(timestamp) {
            const minutes = Math.max(0, Math.floor((Date.now() - timestamp) / 60000));
            if (!Number.isFinite(minutes) || minutes < 1) return 'Just now';
            if (minutes < 60) return `${minutes}m ago`;
            return `${Math.floor(minutes / 60)}h ago`;
        }

        function open(id) {
            if (busy) return;
            const chat = state.chats.find(item => item.id === id);
            if (!chat || onOpen(chat.turns.slice()) === false) return;
            state.activeId = id;
            persist();
            if (dialog.open) dialog.close();
            render();
        }

        function row(chat) {
            const button = document.createElement('button');
            button.type = 'button';
            button.className = 'history-chat';
            button.dataset.chatId = chat.id;
            button.disabled = busy;
            const title = typeof chat.title === 'string' ? chat.title : chat.turns[0].query;
            button.title = title;
            button.setAttribute('aria-label', `Open chat: ${title}`);
            if (chat.id === state.activeId) button.setAttribute('aria-current', 'page');
            const mark = document.createElement('span');
            mark.className = 'history-chat-icon';
            mark.innerHTML = icon;
            const copy = document.createElement('span');
            copy.className = 'history-chat-copy';
            const name = document.createElement('span');
            name.className = 'history-chat-title';
            name.textContent = title;
            const metadata = document.createElement('span');
            metadata.className = 'history-chat-meta';
            metadata.textContent = `${chat.turns.length} ${chat.turns.length === 1 ? 'question' : 'questions'} · ${age(chat.updatedAt)}`;
            copy.append(name, metadata);
            button.append(mark, copy);
            button.addEventListener('click', () => open(chat.id));
            return button;
        }

        function empty(container, message) {
            const text = document.createElement('p');
            text.className = 'history-empty';
            text.textContent = message;
            container.append(text);
        }

        function renderAll() {
            all.replaceChildren();
            const term = search.value.trim().toLocaleLowerCase();
            const matches = state.chats.filter(chat => chat.turns.some(turn => turn.query.toLocaleLowerCase().includes(term)));
            matches.forEach(chat => all.append(row(chat)));
            if (!matches.length) empty(all, state.chats.length ? 'No chats match your search.' : 'Your chats will appear here after your first answer.');
            document.getElementById('history-count').textContent = `${state.chats.length} ${state.chats.length === 1 ? 'chat' : 'chats'} · This tab only`;
        }

        function render() {
            recent.replaceChildren();
            state.chats.slice(0, 6).forEach(chat => recent.append(row(chat)));
            if (!state.chats.length) empty(recent, 'A little space for your past questions. Your first chat will appear here.');
            dock.classList.toggle('history-dock-empty', !state.chats.length);
            document.getElementById('recent-count').textContent = String(Math.min(state.chats.length, 6)).padStart(2, '0');
            renderAll();
        }

        document.querySelector('.history-dock-heading-icon').innerHTML = clock;
        more.querySelector('.history-more-icon').innerHTML = plus;
        more.addEventListener('click', () => {
            search.value = '';
            renderAll();
            dialog.showModal();
            more.setAttribute('aria-expanded', 'true');
            search.focus();
        });
        document.getElementById('history-close').addEventListener('click', () => dialog.close());
        dialog.addEventListener('click', event => {
            const bounds = dialog.getBoundingClientRect();
            if (event.target === dialog && (event.clientX < bounds.left || event.clientX > bounds.right || event.clientY < bounds.top || event.clientY > bounds.bottom)) dialog.close();
        });
        dialog.addEventListener('close', () => {
            more.setAttribute('aria-expanded', 'false');
            more.focus({ preventScroll: true });
        });
        search.addEventListener('input', renderAll);
        persist();
        render();
        return {
            getActiveTurns: () => state.chats.find(chat => chat.id === state.activeId)?.turns.slice() || [],
            startNew() { state.activeId = null; persist(); render(); },
            record(turns) {
                if (!turns.length) return;
                const previous = state.chats.find(chat => chat.id === state.activeId);
                const chat = { id: previous?.id || crypto.randomUUID(), title: previous?.title || turns[0].query, updatedAt: Date.now(), turns: turns.slice(-10) };
                state.activeId = chat.id;
                state.chats = [chat, ...state.chats.filter(item => item.id !== chat.id)].slice(0, MAX_CHATS);
                persist();
                render();
            },
            setBusy(value) { busy = value; render(); },
        };
    }
    window.ChatHistory = { create };
})();
