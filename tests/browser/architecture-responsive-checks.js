/* Mobile layout and reduced-motion behavior in an isolated same-origin frame. */
(async()=>{
    let passed=0;
    const check=(condition,message)=>{if(!condition)throw new Error(message);passed++;};
    const frame=document.createElement('iframe');
    frame.title='Architecture responsive acceptance fixture';
    frame.width='390';frame.height='844';
    const html=(await(await fetch('/static/architecture.html')).text()).replace('<script src="/static/architecture.js" defer></script>','');
    const loaded=new Promise(resolve=>frame.onload=resolve);
    frame.srcdoc=html;document.body.append(frame);
    await loaded;
    try {
        const w=frame.contentWindow,d=w.document;
        await d.fonts.ready;
        const nativeMatch=w.matchMedia.bind(w);
        w.matchMedia=query=>query.includes('prefers-reduced-motion') ? {matches:true,media:query,addEventListener(){},removeEventListener(){}} : nativeMatch(query);
        const script=d.createElement('script');script.src='/static/architecture.js';
        const ready=new Promise((resolve,reject)=>{script.onload=resolve;script.onerror=reject;});d.head.append(script);await ready;
        check(d.documentElement.scrollWidth<=w.innerWidth,'Mobile page must not overflow horizontally.');
        check(d.querySelectorAll('[data-stage]').length===8,'Every stage must remain available on mobile.');
        check(w.getComputedStyle(d.querySelector('.flow-grid')).gridTemplateColumns.split(' ').length===1,'Narrow screens must use a single readable flow column.');
        check(d.getElementById('flow-play').textContent.includes('Next step'),'Reduced motion must use manual step controls.');
        d.getElementById('flow-play').click();
        check(d.querySelector('[data-stage="1"]').getAttribute('aria-pressed')==='true','Reduced-motion controls must step without animation.');
        const canvas=d.getElementById('flow-canvas'),snapshot=canvas.toDataURL();
        await new Promise(resolve=>setTimeout(resolve,180));
        check(canvas.toDataURL()===snapshot,'Reduced-motion canvas must stay static.');
        d.getElementById('mode-hit').click();
        for(let i=0;i<3;i++)d.getElementById('flow-play').click();
        check(d.querySelector('[data-stage="7"]').getAttribute('aria-pressed')==='true','Reduced-motion cache path must step directly to the answer.');
        return {passed,viewport:w.innerWidth,reducedMotion:'static and manual stepping verified'};
    } finally { frame.remove(); }
})();
