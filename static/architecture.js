/* Decorative canvas connections; all content and controls remain semantic HTML. */
(() => {
    'use strict';
    const board = document.getElementById('flow-board');
    const canvas = document.getElementById('flow-canvas');
    const ctx = canvas.getContext('2d');
    const nodes = [...document.querySelectorAll('[data-stage]')];
    const play = document.getElementById('flow-play');
    const reduced = matchMedia('(prefers-reduced-motion: reduce)');
    const details = [
        ['BROWSER', 'Start with a business question', 'The browser sends your question and selected model to the same-origin API. The Groq key stays on the server; questions are limited to 1,000 characters.', 'static/app.js → POST /api/query'],
        ['ADMISSION', 'Protect the public boundary', 'FastAPI validates the request shape and model. A bounded body reader, per-client and global rate limits, and concurrency admission keep public requests within the demo’s resources.', 'app/server.py · app/models.py · app/limits.py'],
        ['CONTEXT & CACHE', 'Ground the question. Check for a reusable answer.', 'The engine builds a compact prompt from the actual schema, data profile, metric rules and verified SQL examples. A session-scoped cache key includes the normalized question, prompt, model and dataset fingerprint. A hit returns the saved answer without another model or SQL call.', 'app/prompts.py · app/cache.py · app/engine.py'],
        ['GENERATION', 'Ask Groq for candidate SQL', 'On a cache miss, the configured model receives the prompt and question. Each actual provider call consumes the daily request budget. SDK retries are disabled; the engine controls bounded retries, timeouts and error handling.', 'app/llm.py · app/limits.py'],
        ['STRUCTURED OUTPUT', 'Treat the model response as untrusted', 'The client extracts JSON, handles fenced responses, rejects empty or incomplete output, and validates bounded SQL, explanation, logic and confidence fields with Pydantic. Model confidence is not calibrated.', 'app/llm.py · app/models.py'],
        ['SQL BOUNDARY', 'Validate capabilities before execution', 'SQLGlot checks for one read-only SELECT or set query, approved tables and allowed functions. Mutations, recursive CTEs and external file/table functions are rejected. DuckDB then binds referenced columns against the loaded schema.', 'app/database.py → validate_sql()'],
        ['EXECUTION', 'Run against an immutable startup snapshot', 'DuckDB holds the validated source data in memory with decimal revenue fields. External access is disabled and configuration is locked. Execution is serialized with an interrupt timer; returned rows, columns and bytes are bounded.', 'app/database.py → execute_sql()'],
        ['ANSWER', 'Return facts, with the calculation visible', 'The engine formats the real SQL rows and generates a deterministic explanation grounded in those results. Successful responses enter the private bounded cache. The browser renders the answer and saves the conversation in this tab; feedback uses a separate expiring receipt.', 'app/engine.py · static/app.js · app/feedback.py'],
    ];
    // Overlapping, invisible alternatives reserve each field's tallest layout.
    // CSS recalculates this naturally for narrow screens, zoom and loaded fonts.
    ['detail-label', 'detail-title', 'detail-copy', 'detail-source'].forEach((id, field) => {
        const current = document.getElementById(id);
        const slot = document.createElement('div');
        slot.className = 'detail-field';
        current.before(slot);
        slot.append(current);
        details.forEach(detail => {
            const reserve = document.createElement(current.tagName);
            reserve.className = `${current.className} detail-reserve`;
            reserve.setAttribute('aria-hidden', 'true');
            reserve.textContent = detail[field];
            slot.append(reserve);
        });
    });
    const routes = { miss: [0,1,2,3,4,5,6,7], hit: [0,1,2,7] };
    let mode = 'miss';
    let elapsed = 0;
    let last = null;
    let raf = null;
    let visible = false;
    let playing = !reduced.matches;
    let selected = -1;
    let width = 1, height = 1, curves = [];
    const duration = 1250;

    // The field is seeded once. No random geometry or text measurements in frames.
    function mulberry32(seed) {
        let value = seed | 0;
        return () => {
            value = (value + 0x6D2B79F5) | 0;
            let next = Math.imul(value ^ value >>> 15, 1 | value);
            next = (next + Math.imul(next ^ next >>> 7, 61 | next)) ^ next;
            return ((next ^ next >>> 14) >>> 0) / 4294967296;
        };
    }
    const random = mulberry32(20241015);
    const field = Array.from({length:64}, () => ({x:random(),y:random(),r:.6+random()*.7}));
    const smoothstep = value => value * value * (3-2*value);

    function choose(index) {
        if (selected === index) return;
        selected = index;
        nodes.forEach((node,i) => node.setAttribute('aria-pressed', String(i === index)));
        const [label,title,copy,source] = details[index];
        document.getElementById('detail-number').textContent = String(index+1).padStart(2,'0');
        document.getElementById('detail-label').textContent = label;
        document.getElementById('detail-title').textContent = title;
        document.getElementById('detail-copy').textContent = copy;
        document.getElementById('detail-source').textContent = source;
    }

    function controls() {
        play.textContent = reduced.matches ? 'Next step →' : playing ? 'Ⅱ Pause' : '▶ Replay flow';
        play.setAttribute('aria-label', reduced.matches ? 'Show the next flow step without animation' : playing ? 'Pause flow animation' : 'Replay flow animation');
    }

    function geometry() {
        if (!ctx) return;
        const bounds = board.getBoundingClientRect();
        width = bounds.width;
        height = bounds.height;
        const dpr = window.devicePixelRatio || 1;
        canvas.width = Math.round(width*dpr);
        canvas.height = Math.round(height*dpr);
        ctx.setTransform(dpr,0,0,dpr,0,0);
        const rects = nodes.map(node => {
            const r = node.getBoundingClientRect();
            return {left:r.left-bounds.left,right:r.right-bounds.left,top:r.top-bounds.top,bottom:r.bottom-bounds.top,x:r.left-bounds.left+r.width/2,y:r.top-bounds.top+r.height/2};
        });
        const route = routes[mode];
        curves = route.slice(0,-1).map((index,i) => {
            const a = rects[index], b = rects[route[i+1]];
            const bypass = index === 2 && route[i+1] === 7;
            if (bypass && Math.abs(a.x-b.x) < 3) return [[a.right,a.y],[width-5,a.y],[width-5,b.y],[b.right,b.y]];
            if (Math.abs(a.y-b.y) < 3) {
                const direction = b.x > a.x ? 1 : -1;
                const start = direction > 0 ? a.right : a.left;
                const end = direction > 0 ? b.left : b.right;
                const middle = (start+end)/2;
                return [[start,a.y],[middle,a.y],[middle,b.y],[end,b.y]];
            }
            const middle = (a.bottom+b.top)/2;
            return [[a.x,a.bottom],[a.x,middle],[b.x,middle],[b.x,b.top]];
        });
        paint();
    }

    function point(curve,t) {
        const u=1-t;
        return [0,1].map(axis => u*u*u*curve[0][axis]+3*u*u*t*curve[1][axis]+3*u*t*t*curve[2][axis]+t*t*t*curve[3][axis]);
    }

    function paint() {
        if (!ctx) return;
        ctx.clearRect(0,0,width,height);
        ctx.fillStyle='rgba(139,90,43,.09)';
        field.forEach(p => {ctx.beginPath();ctx.arc(p.x*width,p.y*height,p.r,0,Math.PI*2);ctx.fill();});
        curves.forEach(curve => {
            ctx.beginPath();ctx.moveTo(...curve[0]);ctx.bezierCurveTo(...curve[1],...curve[2],...curve[3]);
            ctx.strokeStyle='rgba(139,90,43,.21)';ctx.lineWidth=1.4;ctx.stroke();
            const end=curve[3], before=point(curve,.94), angle=Math.atan2(end[1]-before[1],end[0]-before[0]);
            ctx.beginPath();ctx.moveTo(end[0]-5*Math.cos(angle-.5),end[1]-5*Math.sin(angle-.5));ctx.lineTo(...end);ctx.lineTo(end[0]-5*Math.cos(angle+.5),end[1]-5*Math.sin(angle+.5));ctx.stroke();
        });
        if (!curves.length) return;
        const route=routes[mode];
        const step=Math.floor(elapsed/duration)%route.length;
        if (playing) choose(route[step]);
        const curve=curves[step];
        if (curve && playing && !reduced.matches) {
            const t=smoothstep((elapsed%duration)/duration);
            const p=point(curve,t);
            ctx.save();ctx.shadowColor='rgba(139,90,43,.4)';ctx.shadowBlur=12;
            ctx.beginPath();ctx.arc(...p,3.2,0,Math.PI*2);ctx.fillStyle='#8b5a2b';ctx.fill();
            ctx.shadowBlur=0;ctx.beginPath();ctx.arc(...p,1.3,0,Math.PI*2);ctx.fillStyle='#fffdf9';ctx.fill();ctx.restore();
        }
    }

    function frame(now) {
        raf=null;
        if (!playing || reduced.matches || !visible || document.hidden) {last=null;return;}
        const dt=last===null ? 0 : Math.max(0,Math.min(64,now-last));
        last=now;elapsed+=dt;
        paint();
        raf=requestAnimationFrame(frame);
    }

    function sync() {
        if (raf!==null) cancelAnimationFrame(raf);
        raf=null;last=null;
        controls();paint();
        if (ctx && playing && !reduced.matches && visible && !document.hidden) raf=requestAnimationFrame(frame);
    }

    function changeMode(next) {
        mode=next;elapsed=0;
        document.getElementById('mode-miss').setAttribute('aria-pressed',String(mode==='miss'));
        document.getElementById('mode-hit').setAttribute('aria-pressed',String(mode==='hit'));
        document.getElementById('cache-route-note').hidden=mode!=='hit';
        nodes.forEach((node,i) => node.dataset.bypassed=String(mode==='hit' && i>=3 && i<=6));
        choose(0);geometry();sync();
    }

    nodes.forEach((node,index) => node.addEventListener('click', () => {playing=false;choose(index);sync();}));
    document.getElementById('mode-miss').addEventListener('click', () => changeMode('miss'));
    document.getElementById('mode-hit').addEventListener('click', () => changeMode('hit'));
    play.addEventListener('click', () => {
        if (reduced.matches) {
            const route=routes[mode];choose(route[(route.indexOf(selected)+1)%route.length]);paint();
        } else {playing=!playing;if(playing)elapsed=0;sync();}
    });
    document.addEventListener('visibilitychange',sync);
    reduced.addEventListener('change', () => {if(reduced.matches)playing=false;sync();});
    const observer=new IntersectionObserver(entries => {visible=entries[0].isIntersecting;sync();});
    observer.observe(board);
    const resize=new ResizeObserver(geometry);resize.observe(board);
    window.addEventListener('resize',geometry);
    window.addEventListener('pagehide', () => {if(raf!==null)cancelAnimationFrame(raf);raf=null;last=null;});
    window.addEventListener('pageshow',sync);
    if(document.fonts)document.fonts.ready.then(geometry);
    choose(0);geometry();sync();
})();
