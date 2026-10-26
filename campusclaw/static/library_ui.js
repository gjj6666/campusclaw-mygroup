(() => {
  const {$,el,button,json,notice,run,sourceText,modal,file} = CampusUI;
  let shared=[], personal=[], group={source:'shared',subject:null}, selected=null, mode='list';
  try {mode=localStorage.getItem('campusclaw_material_view') || 'list';} catch {}
  function back() {$('reading').hidden=true;$('material-list').hidden=false;}
  function groups() {
    const box=$('material-groups');box.replaceChildren();
    for (const [source,label,items] of [['shared','本班资料',shared],['personal','我的个人资料',personal]]) {
      const all=button(`${label} · ${items.length}`,()=>{group={source,subject:null};back();draw();groups();},'list-item');all.classList.toggle('selected',group.source===source && !group.subject);box.append(all);
      for (const subject of [...new Set(items.map(i=>i.subject))]) {
        const b=button(`　${subject} · ${items.filter(i=>i.subject===subject).length}`,()=>{group={source,subject};back();draw();groups();},'list-item');b.classList.toggle('selected',group.source===source && group.subject===subject);box.append(b);
      }
    }
  }
  function draw() {
    const list=$('material-list');list.replaceChildren();list.classList.toggle('grid-view',mode==='grid');
    const items=(group.source==='shared'?shared:personal).filter(i=>(!group.subject || i.subject===group.subject)&&i.title.toLowerCase().includes($('material-filter').value.toLowerCase()));
    $('list-mode').setAttribute('aria-pressed',String(mode==='list'));$('grid-mode').setAttribute('aria-pressed',String(mode==='grid'));
    if (!items.length) {list.append(el('p',group.source==='personal'?'还没有个人资料。可直接上传，或从本班资料保存副本。':'没有匹配的本班资料。','empty'));return;}
    for (const item of items) {const card=el('article',null,'material-card'),info=el('div',null,'details');info.append(el('h3',item.title),el('span',`${item.subject} · ${group.source==='personal'?'仅本人':'本班共享'}${item.index_status?' · '+item.index_status:''}`,'state'));card.append(el('span','文','badge'),info,button('阅读',()=>open(group.source,item.id)));list.append(card);}
  }
  async function refresh() {shared=(await json('/api/library/materials')).materials;personal=(await json('/api/personal-materials')).materials;groups();draw();return {shared,personal};}
  async function open(source,id) {
    const {material}=await json(source==='personal'?`/api/personal-materials/${id}`:`/api/library/materials/${id}`);selected={source,material};
    $('material-list').hidden=true;$('reading').hidden=false;$('save-personal').hidden=source==='personal';
    $('reading-meta').textContent=`${material.filename} · ${material.subject} · ${source==='personal'?'仅本人':'本班共享'}`;
    sourceText($('reader'),material.content,/\.md$/i.test(material.filename));
  }
  async function upload() {
    modal('上传我的个人资料',body=>{
      const label=el('label','选择 UTF-8 .md/.txt（32 KiB / 12000字）'),input=el('input');input.type='file';input.accept='.md,.txt';label.append(input);
      const subjectLabel=el('label','学科'),subject=el('input');subject.value='通用';subject.maxLength=64;subjectLabel.append(subject);
      const preview=el('pre','选择文件后预览。','preview');let content='',filename='';
      input.onchange=run(async()=>{filename='';content=await file(input.files[0]);filename=input.files[0].name;preview.textContent=content;});
      const save=button('保存到个人资料库',async()=>{if(!filename)throw new Error('请先选择合法文件');save.disabled=true;try{await json('/api/personal-materials','POST',{filename,content,subject:subject.value});await refresh();group={source:'personal',subject:null};back();groups();draw();$('dialog').close();notice('个人资料已保存，可在本人的不同会话中选择');}finally{save.disabled=false;}},'');
      body.append(label,subjectLabel,preview,save);
    });
  }
  $('material-filter').oninput=()=>{back();draw();};$('back-materials').onclick=back;
  for(const value of ['list','grid']) $(value+'-mode').onclick=()=>{mode=value;try{localStorage.setItem('campusclaw_material_view',value);}catch{}draw();};
  $('save-personal').onclick=run(async()=>{if(selected?.source!=='shared')return;await json('/api/personal-materials','POST',{source:{kind:'shared',id:selected.material.id}});await refresh();notice('已保存个人副本，可跨本人会话复用');});
  $('personal-upload').onclick=run(upload);
  window.CampusLibrary={refresh,open,upload};
})();
