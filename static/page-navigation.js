/* Shared navigation for the companion pages; no API or provider requests. */
(() => {
    'use strict';
    const items = [
        ['/', 'Chat workspace', '<path d="M21 11.5a8.5 8.5 0 0 1-8.5 8.5H4l-2 2V11.5a9.5 9.5 0 0 1 19 0Z"/><path d="M7 9h9M7 13h6"/>'],
        ['/static/architecture.html', 'Architecture', '<rect x="8" y="2" width="8" height="5" rx="1.5"/><rect x="2" y="17" width="7" height="5" rx="1.5"/><rect x="15" y="17" width="7" height="5" rx="1.5"/><path d="M12 7v5M5.5 17v-5h13v5"/>'],
        ['/static/data.html', 'About the data', '<ellipse cx="12" cy="5" rx="8" ry="3"/><path d="M4 5v14c0 4 16 4 16 0V5M4 12c0 4 16 4 16 0"/>'],
        ['/static/evaluations.html', 'Evaluations', '<path d="M9 3h6v4H9zM9 5H6a2 2 0 0 0-2 2v13a2 2 0 0 0 2 2h12a2 2 0 0 0 2-2V7a2 2 0 0 0-2-2h-3M8 14l3 3 5-6"/>'],
        ['https://github.com/manyakaistha/nl-analytics-query-engine-', 'GitHub', '<path d="M9 19c-4 1-4-2-6-2m12 4v-3.4c0-1 .1-1.5-.5-2.1 3.4-.4 7-1.7 7-7.6 0-1.7-.6-3.1-1.6-4.2.2-.4.7-2-.2-4.1 0 0-1.3-.4-4.4 1.6a15 15 0 0 0-8 0C4.2-.8 2.9-.4 2.9-.4c-.9 2.1-.4 3.7-.2 4.1C1.7 4.8 1.1 6.2 1.1 7.9c0 5.9 3.6 7.2 7 7.6-.4.4-.8 1.1-.8 2.1V21" transform="translate(1 1) scale(.9)"/>'],
    ];
    const nav = document.querySelector('.companion-dock .dock-links');
    if (!nav) return;
    const ordered = [items[0], items[4], items[1], items[2], items[3]];
    ordered.forEach(([href, label, paths]) => {
        const anchor = document.createElement('a');
        anchor.className = 'dock-link glass-pill';
        anchor.href = href;
        anchor.title = label;
        anchor.setAttribute('aria-label', label);
        if (href === location.pathname) anchor.setAttribute('aria-current', 'page');
        if (href.startsWith('https:')) {
            anchor.target = '_blank';
            anchor.rel = 'noopener noreferrer';
        }
        // Icons are trusted constants, never model output or user input.
        anchor.innerHTML = `<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.6" aria-hidden="true">${paths}</svg>`;
        const text = document.createElement('span');
        text.textContent = label;
        anchor.append(text);
        const arrow = document.createElement('span');
        arrow.className = 'dock-link-arrow';
        arrow.setAttribute('aria-hidden', 'true');
        arrow.textContent = '↗';
        anchor.append(arrow);
        nav.append(anchor);
    });

    const headings = [...document.querySelectorAll('main h2[id]')];
    if (!headings.length) return;
    const contents = document.createElement('details');
    contents.className = 'reading-dock';
    let wasAtTop = scrollY <= 64;
    let lastScrollY = scrollY;
    contents.open = wasAtTop;
    const summary = document.createElement('summary');
    summary.className = 'glass-pill reading-heading';
    summary.innerHTML = '<span class="reading-icon" aria-hidden="true">☷</span><span class="reading-label">On this page</span>';
    summary.setAttribute('aria-label', 'Toggle contents and reading progress');
    const percent = document.createElement('span');
    percent.className = 'reading-percent';
    percent.textContent = '0%';
    summary.append(percent);
    const panel = document.createElement('div');
    panel.className = 'reading-panel';
    const progress = document.createElement('progress');
    progress.className = 'reading-progress';
    progress.max = 100;
    progress.value = 0;
    progress.setAttribute('aria-label', 'Page reading progress');
    panel.append(progress);
    const list = document.createElement('nav');
    list.className = 'reading-links';
    list.setAttribute('aria-label', 'Page contents');
    const links = headings.map((heading, index) => {
        const link = document.createElement('a');
        link.className = 'dock-link glass-pill reading-link';
        link.href = `#${heading.id}`;
        const number = document.createElement('span');
        number.className = 'reading-number';
        number.textContent = String(index + 1).padStart(2, '0');
        number.setAttribute('aria-hidden', 'true');
        const title = document.createElement('span');
        title.textContent = heading.textContent.trim();
        link.append(number, title);
        link.addEventListener('click', () => {
            setContentsOpen(false);
        });
        list.append(link);
        return link;
    });
    panel.append(list);
    contents.append(summary, panel);
    document.body.append(contents);
    const reducedMotion = matchMedia('(prefers-reduced-motion: reduce)');
    let disclosureAnimation = null;
    let disclosureTimer = null;
    let requestedOpen = contents.open;
    function setContentsOpen(open) {
        if (requestedOpen === open) return;
        requestedOpen = open;
        const opacity = contents.open ? getComputedStyle(panel).opacity : '0';
        const transform = contents.open ? getComputedStyle(panel).transform : 'translateY(-8px) scaleY(.94)';
        clearTimeout(disclosureTimer);
        disclosureAnimation?.cancel();
        disclosureAnimation = null;
        if (reducedMotion.matches) {
            contents.open = open;
            return;
        }
        if (open) contents.open = true;
        // Keep native details open until the reverse animation finishes.
        // This avoids its immediate display:none cutting off the exit motion.
        disclosureAnimation = panel.animate([
            { opacity, transform },
            { opacity: open ? 1 : 0, transform: open ? 'translateY(0) scaleY(1)' : 'translateY(-8px) scaleY(.94)' },
        ], { duration: 260, easing: 'cubic-bezier(.22,1,.36,1)', fill: 'both' });
        const animation = disclosureAnimation;
        const finish = () => {
            if (disclosureAnimation !== animation) return;
            clearTimeout(disclosureTimer);
            contents.open = requestedOpen;
            animation.cancel();
            disclosureAnimation = null;
        };
        animation.onfinish = finish;
        // Complete even if a background/preview document pauses its animation clock.
        disclosureTimer = setTimeout(finish, 280);
    }
    summary.addEventListener('click', event => {
        event.preventDefault();
        setContentsOpen(!requestedOpen);
    });
    let queued = false;
    function updateReading() {
        queued = false;
        const atTop = scrollY <= 64;
        // Open on returning to the top; collapse on downward reading scrolls.
        // A manual reopen stays open until the reader continues scrolling down.
        if (atTop !== wasAtTop) setContentsOpen(atTop);
        else if (!atTop && scrollY > lastScrollY + 1) setContentsOpen(false);
        wasAtTop = atTop;
        lastScrollY = scrollY;
        const max = Math.max(0, document.documentElement.scrollHeight - innerHeight);
        const value = max ? Math.round(Math.min(1, Math.max(0, scrollY / max)) * 100) : 100;
        progress.value = value;
        percent.textContent = `${value}%`;
        let current = 0;
        headings.forEach((heading, index) => {
            if (heading.getBoundingClientRect().top <= innerHeight * .3) current = index;
        });
        if (value === 100) current = headings.length - 1;
        links.forEach((link, index) => {
            if (index === current) link.setAttribute('aria-current', 'location');
            else link.removeAttribute('aria-current');
        });
    }
    function queueReading() {
        if (!queued) { queued = true; requestAnimationFrame(updateReading); }
    }
    addEventListener('scroll', queueReading, { passive: true });
    addEventListener('resize', queueReading, { passive: true });
    new ResizeObserver(queueReading).observe(document.querySelector('main'));
    document.fonts.ready.then(queueReading);
    updateReading();
})();
