/* Run in the architecture page's main frame. No provider calls are made. */
(async () => {
    let passed=0;
    function check(condition,message) { if(!condition)throw new Error(message);passed++; }
    const wait=ms=>new Promise(resolve=>setTimeout(resolve,ms));
    await document.fonts.ready;
    const board=document.getElementById('flow-board');
    board.scrollIntoView({block:'center'});
    await wait(100);
    const originalFetch=window.fetch;
    let requests=0;
    window.fetch=(...args)=>{requests++;return originalFetch(...args);};
    try {
        check(document.querySelectorAll('[data-stage]').length===8,'All eight processing steps must be present.');
        document.querySelector('[data-stage="5"]').click();
        check(document.getElementById('detail-source').textContent.includes('validate_sql'),'Selecting a stage must show its actual implementation boundary.');
        check(document.getElementById('flow-play').textContent.includes('Replay'),'Inspecting a step must pause automatic playback.');
        document.getElementById('mode-hit').click();
        check(document.querySelectorAll('[data-bypassed="true"]').length===4,'A cache hit must bypass inference, parsing, guard, and database execution.');
        check(!document.getElementById('cache-route-note').hidden,'The cache shortcut needs a visible explanation.');
        document.getElementById('mode-miss').click();
        check(document.querySelectorAll('[data-bypassed="true"]').length===0,'A cache miss must restore the complete path.');
        const canvas=document.getElementById('flow-canvas');
        const rect=board.getBoundingClientRect();
        check(Math.abs(canvas.width-rect.width*devicePixelRatio)<=1,'The canvas backing store must follow device pixel ratio.');
        document.getElementById('flow-play').click();
        await wait(120);
        const moving=canvas.toDataURL();
        await wait(180);
        check(canvas.toDataURL()!==moving,'The illustrative flow must animate while playing.');
        document.getElementById('flow-play').click();
        const paused=canvas.toDataURL();
        await wait(160);
        check(canvas.toDataURL()===paused,'Paused animation must remain static.');
        check(document.documentElement.scrollWidth<=innerWidth,'The architecture page must not overflow horizontally.');
        check(requests===0,'Inspecting and animating the flow must make zero API requests.');
        return {passed,stages:8,animation:'moving and paused verified',apiRequests:requests};
    } finally { window.fetch=originalFetch; }
})();
