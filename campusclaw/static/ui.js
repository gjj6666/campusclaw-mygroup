(() => {
  const $ = id => document.getElementById(id);
  const key = 'campusclaw_access_token';
  function el(tag, text, className) {const n = document.createElement(tag); if (text != null) n.textContent = text; if (className) n.className = className; return n;}
  function notice(text, error = false) {
    const n = $('notice'); n.textContent = text; n.classList.toggle('error-text', error);
    if ($('dialog')?.open) {let alert=$('dialog-body').querySelector('.dialog-notice');if(!alert){alert=el('p',null,'dialog-notice');alert.setAttribute('role','status');$('dialog-body').prepend(alert);}alert.textContent=text;alert.classList.toggle('error-text',error);}
  }
  function run(fn) {return async event => {event?.preventDefault(); try {await fn(event);} catch (err) {notice(err.message, true);}};}
  async function request(path, options = {}) {
    const token = sessionStorage.getItem(key);
    if (!token) {location.replace('/login'); throw new Error('请先登录');}
    const response = await fetch(path, {...options, cache:'no-store', headers:{Accept:'application/json', ...options.headers, Authorization:`Bearer ${token}`}});
    if (response.status === 401) {sessionStorage.removeItem(key); location.replace('/login'); throw new Error('登录已失效');}
    if (!response.ok) {const data = await response.json(); throw new Error(data.message || (response.status === 403 ? '此功能仅教师可用' : response.status === 404 ? '资源不存在或不可访问' : data.error || '请求失败'));}
    return response;
  }
  async function json(path, method='GET', data) {return (await request(path,{method,...(data === undefined ? {} : {headers:{'Content-Type':'application/json'},body:JSON.stringify(data)})})).json();}
  function button(label, fn, className='secondary') {const n = el('button', label, className); n.type='button'; n.onclick=run(fn); return n;}
  async function file(file, maximum=12000, bytes=32768) {
    if (!file || !/\.(md|txt)$/i.test(file.name)) throw new Error('请选择 .md/.txt 文件');
    if (file.size > bytes) throw new Error(`文件最多 ${Math.floor(bytes/1024)} KiB`);
    let text; try {text = new TextDecoder('utf-8',{fatal:true}).decode(await file.arrayBuffer());} catch {throw new Error('文件须为 UTF-8 编码');}
    if (!text.trim() || [...text].length > maximum || text.includes('\0')) throw new Error(`文件须为非空纯文本，最多${maximum}字`);
    return text;
  }
  function option(select, value, label) {const n = el('option', label); n.value=value; select.append(n);}
  function sourceText(parent, content, markdown=false) {
    parent.replaceChildren();
    if (!markdown) {const pre=el('pre',content,'plain-text'); parent.append(pre); return;}
    // A small DOM-only Markdown subset. Raw HTML and remote images remain text.
    function inline(node, text) {
      const re = /(`[^`]+`|\*\*[^*]+\*\*|(?<!!)\[[^\]]+\]\([^\s)]+\))/g; let pos=0, m;
      while ((m=re.exec(text))) {
        node.append(document.createTextNode(text.slice(pos,m.index))); const v=m[0];
        if (v.startsWith('`')) node.append(el('code',v.slice(1,-1)));
        else if (v.startsWith('**')) node.append(el('strong',v.slice(2,-2)));
        else {const parts=/^\[([^\]]+)\]\(([^)]+)\)$/.exec(v); let safe=false; try {safe=['http:','https:'].includes(new URL(parts[2]).protocol);} catch {}
          if (safe) {const a=el('a',parts[1]); a.href=parts[2]; a.rel='noopener noreferrer'; a.target='_blank'; node.append(a);} else node.append(document.createTextNode(v));}
        pos=re.lastIndex;
      } node.append(document.createTextNode(text.slice(pos)));
    }
    let code=null, list=null;
    for (const line of content.split(/\r?\n/)) {
      if (/^```/.test(line)) {if (code) code=null; else {code=el('pre', '', 'code-block'); parent.append(code);} list=null; continue;}
      if (code) {code.append(document.createTextNode(line+'\n')); continue;}
      const h=/^(#{1,6})\s+(.+)$/.exec(line), li=/^\s*(?:[-*+] |\d+\. )(.+)$/.exec(line);
      if (li) {if (!list) {list=el('ul');parent.append(list);} const n=el('li');inline(n,li[1]);list.append(n);continue;}
      list=null; if (!line.trim()) continue;
      const n=el(h ? 'h'+h[1].length : 'p');inline(n,h ? h[2] : line);parent.append(n);
    }
  }
  function modal(title, build) {
    const d=$('dialog'), body=$('dialog-body'); $('dialog-title').textContent=title; body.replaceChildren(); build(body); d.showModal();
  }
  function confirmAction(message) {
    return new Promise(resolve => {
      let accepted=false;
      modal('确认操作',body=>{body.append(el('p',message));const actions=el('div',null,'actions');
        actions.append(button('取消，保留内容',()=>{$('dialog').close();}),button('确认继续',()=>{accepted=true;$('dialog').close();},''));body.append(actions);});
      $('dialog').addEventListener('close',()=>resolve(accepted),{once:true});
    });
  }
  $('dialog-close')?.addEventListener('click',()=>$('dialog').close());
  $('theme-toggle')?.addEventListener('click',window.toggleCampusTheme);
  $('theme-toggle')?.setAttribute('aria-pressed',String(document.documentElement.dataset.theme==='dark'));
  $('logout')?.addEventListener('click',()=>{sessionStorage.removeItem(key);location.replace('/login');});
  const mobileNav=matchMedia('(max-width:760px)'), nav=document.querySelector('.global-nav');
  function setNav(open){
    const focused=nav?.contains(document.activeElement);
    document.body.classList.toggle('nav-open',open);
    $('nav-toggle')?.setAttribute('aria-expanded',String(open));
    if(nav)nav.inert=mobileNav.matches&&!open;
    if(focused&&mobileNav.matches&&!open)$('nav-toggle')?.focus();
  }
  function closeNav(){setNav(false);}
  $('nav-toggle')?.addEventListener('click',()=>setNav(!document.body.classList.contains('nav-open')));
  $('nav-backdrop')?.addEventListener('click',closeNav);
  mobileNav.addEventListener('change',closeNav);
  document.addEventListener('keydown',event=>{if(event.key==='Escape')closeNav();});
  closeNav();
  window.CampusUI = {$,el,notice,run,request,json,button,file,option,sourceText,modal,confirmAction,closeNav};
})();
