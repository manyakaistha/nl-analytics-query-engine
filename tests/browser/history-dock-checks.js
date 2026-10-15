/* Run in a fresh offline frontend fixture tab with an empty chat library,
   in the page's main frame after it has loaded.
   Restores stored history with window.restoreHistoryDockTest() followed by reload. */
(() => {
    let passed = 0;
    function check(condition, message) { if (!condition) throw new Error(message); passed++; }
    const keys = ['aqe-chat-library-v1', 'aqe-session-history-v2'];
    const backup = keys.map(key => [key, sessionStorage.getItem(key)]);
    window.restoreHistoryDockTest = () => {
        backup.forEach(([key,value]) => value === null ? sessionStorage.removeItem(key) : sessionStorage.setItem(key,value));
    };
    const originalFetch = window.fetch;
    let requests = 0;
    window.fetch = (...args) => { requests++; return originalFetch(...args); };
    const fixture = index => ({ query: `History fixture ${index}`, generated_sql: 'SELECT 1 AS fixture', generated_logic: 'Browser UI fixture.', result: '1', explanation: 'Offline history interaction check.', confidence_score: .5, model: 'openai/gpt-oss-120b', response_time_ms: 0, attempts: 1, feedback_id: 'fixture-not-a-server-receipt' });
    try {
        // Keep these checks independent of any pre-existing tab history.
        const saved = JSON.parse(sessionStorage.getItem(keys[0]));
        check(saved.chats.length === 0, 'Run this fixture with an empty chat library.');
        for (let i = 1; i <= 8; i++) { newChat(); historyDock.record([fixture(i)]); }
        check(document.querySelectorAll('#recent-chat-list .history-chat').length === 6, 'The dock must show exactly six recent chats.');
        check(document.querySelector('#recent-chat-list .history-chat-title').textContent === 'History fixture 8', 'Newest completed chat comes first.');
        newChat();
        check(document.querySelectorAll('#recent-chat-list .history-chat').length === 6, 'New chat must preserve previous chats.');
        check(!document.getElementById('welcome-message').hidden, 'New chat must show the welcome screen.');
        document.getElementById('history-more').click();
        const dialog = document.getElementById('chat-history-dialog');
        check(dialog.open, 'The plus button must open the history dialog.');
        check(document.querySelectorAll('#all-chat-list .history-chat').length === 8, 'Expanded list must include older chats.');
        check(document.activeElement.id === 'history-search', 'Opening history must focus the search field.');
        const search = document.getElementById('history-search');
        search.value = 'fixture 1'; search.dispatchEvent(new Event('input'));
        check(document.querySelectorAll('#all-chat-list .history-chat').length === 1, 'Search must find chats outside the recent six.');
        document.querySelector('#all-chat-list .history-chat').click();
        check(!dialog.open, 'Selecting a chat must close the dialog.');
        check(sessionHistory[0].query === 'History fixture 1', 'Selecting history must restore its answers.');
        check(document.getElementById('chat-container').innerText.includes('Offline history interaction check.'), 'Restored answers must render.');
        check(document.getElementById('welcome-message').hidden, 'Opening a saved chat must hide the new-chat welcome screen.');
        check(getComputedStyle(document.getElementById('welcome-message')).display === 'none', 'The welcome screen must not occupy space above saved messages.');
        historyDock.record([...sessionHistory, fixture('continued')]);
        check(JSON.parse(sessionStorage.getItem(keys[0])).chats.length === 8, 'Continuing a chat must update it, not duplicate it.');
        check(document.querySelector('#recent-chat-list .history-chat-meta').textContent.startsWith('2 questions'), 'Conversation metadata must reflect its turns.');
        historyDock.setBusy(true);
        check([...document.querySelectorAll('#recent-chat-list button')].every(button => button.disabled), 'History switching must be disabled while a query runs.');
        historyDock.setBusy(false);
        for (let i = 9; i <= 37; i++) { newChat(); historyDock.record([fixture(i)]); }
        check(JSON.parse(sessionStorage.getItem(keys[0])).chats.length === 30, 'The library must remain bounded at 30 chats.');
        newChat();
        historyDock.record([{...fixture('escaped'),query:'<img src=x onerror=alert(1)>'}]);
        check(!document.querySelector('#recent-chat-list img'), 'History titles must be text, never injected HTML.');
        check(document.querySelector('#recent-chat-list .history-chat-title').textContent.includes('<img'), 'Special characters must remain visible as text.');
        check(requests === 0, 'Restoring and browsing history must make zero API requests.');
        return {passed, recent:6, retained:30, historyRequests:requests};
    } finally {
        window.fetch = originalFetch;
    }
})();
