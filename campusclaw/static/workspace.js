(async () => {
  const {$,el,button,json,notice,run,request,file,modal,sourceText,confirmAction}=CampusUI;
  let apps=[], agents=[], skills=[], shared=[], personal=[], attachments=[], currentApp=null, active=null, busy=false, uploading=false;
  let context={}, staged=[], sequence=0, view='chat';
  const key=r=>`${r.source}:${r.id}`;
  function defaults(){return agents.find(a=>a.id===currentApp?.agent_id)?.material_ids.map(id=>({source:'shared',id})) || [];}
  function listFor(source,kind){return source==='staged'?staged:source==='personal'?personal:source==='upload'?attachments:kind==='skill'?skills:shared;}
  function name(ref,kind){const v=listFor(ref.source,kind).find(i=>i.id===ref.id);return v?.name||v?.title||v?.filename||`内容 ${ref.id}`;}
  function changed(){return $('question').value.trim() || staged.length || Object.keys(context).length;}
  async function guard(){if(busy||uploading)throw new Error('请等待当前操作完成');return !changed()||await confirmAction('有尚未发送的问题或选择。确定放弃草稿并切换吗？选择取消可继续保留。');}
  function tags(){
    $('context-tags').replaceChildren();
    function add(label,remove){const n=el('span',label,'context-tag'),b=button('×',()=>{if(busy||uploading)return;remove();tags();},'ghost');b.setAttribute('aria-label',`移除${label}`);n.append(b);$('context-tags').append(n);}
    add(!('skill' in context)?'技能 · 自动匹配':context.skill?`技能 · ${name(context.skill,'skill')}`:'本轮不使用技能',()=>{context.skill=null;staged=staged.filter(i=>i.kind!=='skill');});
    for(const r of context.materials??defaults())add(`${r.source==='personal'?'个人资料':'资料'} · ${name(r,'material')}`,()=>{context.materials=(context.materials??defaults()).filter(i=>key(i)!==key(r));if(r.source==='staged')staged=staged.filter(i=>i.id!==r.id);});
  }
  function choose(ref,kind){
    if(busy||uploading)throw new Error('请等待当前操作完成');
    if(kind==='skill'){context.skill=ref;staged=staged.filter(i=>i.kind!=='skill'||(ref.source==='staged'&&i.id===ref.id));}
    else {const refs=context.materials??defaults();if(refs.some(i=>key(i)===key(ref)))return;if(refs.length>=3)throw new Error('每轮最多三份资料，请先移除部分资料');context.materials=[...refs,ref];}tags();
  }
  async function refreshData(){
    agents=(await json('/api/agents')).agents;skills=(await json('/api/skills')).skills.filter(i=>i.enabled);
    const data=await CampusLibrary.refresh();shared=data.shared;personal=data.personal;
  }
  async function refreshConversations(){
    const {conversations}=await json('/api/conversations');$('conversations').replaceChildren();
    for(const conv of conversations){const b=button('',()=>openConversation(conv),'list-item');b.append(el('span',conv.title),el('small',`${conv.agent_name} · ${new Date(conv.last_activity.replace(' ','T')+'Z').toLocaleString()}`));b.classList.toggle('selected',conv.id===active);$('conversations').append(b);}
  }
  function showView(next){view=next;$('chat-view').hidden=next!=='chat';$('library-view').hidden=next!=='library';$('chat-sidebar').hidden=next!=='chat';$('library-sidebar').hidden=next!=='library';$('nav-chat').classList.toggle('selected',next==='chat');$('nav-library').classList.toggle('selected',next==='library');$('view-title').textContent=next==='library'?'资料库':currentApp?.name||'学习工作区';CampusUI.closeNav();history.replaceState(null,'','#'+next);}
  function welcome(){ $('welcome').hidden=false;$('history').hidden=true;$('welcome-title').textContent=(currentApp?.name||'学习助手')+'，我帮你';$('welcome-description').textContent=currentApp?.description||'写下你的问题，带上技能与资料，一起探索。';$('suggestions').replaceChildren();
    const examples=[currentApp?.example,'请帮我梳理这个知识点','我做到这一步卡住了，下一步怎么想？'].filter(Boolean);
    for(const question of examples)$('suggestions').append(button(question,()=>{$('question').value=question;$('question').focus();}));
  }
  function reset(){context={};staged=[];attachments=[];$('question').value='';$('history').replaceChildren();$('upload-state').textContent='UTF-8 .md/.txt · 最多32 KiB · 选择只作用于本轮';tags();}
  async function selectApp(app){if(!await guard())return;sequence++;active=null;currentApp=app;reset();welcome();drawApps();showView('chat');await refreshConversations();}
  function drawApps(){$('app-list').replaceChildren();for(const app of apps){const b=button(app.name,()=>selectApp(app),'list-item');b.disabled=!app.enabled;b.classList.toggle('selected',app===currentApp);$('app-list').append(b);}}
  function contextLine(parent,snapshot){const labels=[];if(snapshot?.skill)labels.push('技能：'+snapshot.skill.name);for(const r of snapshot?.materials||[])labels.push('资料：'+r.name);if(labels.length)parent.append(el('p',labels.join(' · '),'state'));}
  function renderSources(parent,sources){const box=el('div',null,'refs');for(const s of sources||[])box.append(button(`[${s.citation}] ${s.material_title}`,async()=>{const data=await json(s.url),item=data.material||data.attachment;modal(s.material_title,body=>sourceText(body,item.content,/\.md$/i.test(item.filename||'')));}));parent.append(box);}
  function bubble(role,content,status='completed',sources=[]){const n=el('div',null,`bubble ${role} ${status}`),state=el('div',`${role==='user'?'你':'学习助手'} · ${status==='completed'?'已完成':status==='generating'?'生成中':'未完成'}`,'state'),body=el('div',content);n.append(state,body);renderSources(n,sources);$('history').append(n);$('history').scrollTop=$('history').scrollHeight;return {n,state,body};}
  async function openConversation(conv){if(!await guard())return;const op=++sequence;active=conv.id;currentApp=apps.find(i=>i.agent_id===conv.agent_id)||{name:conv.agent_name,agent_id:conv.agent_id};reset();showView('chat');$('welcome').hidden=true;$('history').hidden=false;
    const [{messages},choices]=await Promise.all([json(`/api/conversations/${conv.id}/messages`),json(`/api/conversations/${conv.id}/context`)]);if(op!==sequence||active!==conv.id)return;
    attachments=choices.attachments;personal=choices.personal||personal;
    for(const m of messages){const b=bubble(m.role,m.content,m.status,m.sources);if(m.role==='user')contextLine(b.n,m.context);}if(!messages.length)welcome();tags();drawApps();await refreshConversations();notice('');
  }
  async function picker(kind){if(busy||uploading)throw new Error('请等待当前操作完成');await refreshData();if(active)attachments=(await json(`/api/conversations/${active}/attachments`)).attachments;
    modal(kind==='skill'?'为本轮添加技能':'为本轮添加资料',body=>{
      function row(label,action,preview,save){const n=el('div',null,'dialog-option');n.append(el('span',label),button('选择',()=>{action();$('dialog').close();}));if(preview)n.append(button('预览',async()=>{let pre=body.querySelector('.preview');if(!pre){pre=el('pre',null,'preview');body.append(pre);}pre.textContent=await preview();}));if(save)n.append(button('存入个人库',save));body.append(n);}
      if(kind==='skill'){row('自动匹配应用默认技能',()=>{delete context.skill;tags();});row('本轮不使用技能',()=>{context.skill=null;tags();});}
      else row('本轮不使用资料',()=>{context.materials=[];tags();});
      for(const i of kind==='skill'?skills:shared.filter(i=>i.index_status==='ready'))row(`本班共享 · ${i.name||i.title}`,()=>choose({source:'shared',id:i.id},kind),async()=>i.content||(await json(`/api/library/materials/${i.id}`)).material.content);
      if(kind==='material')for(const i of personal)row(`我的个人资料 · ${i.title}`,()=>choose({source:'personal',id:i.id},kind),async()=>i.content);
      for(const i of attachments.filter(i=>i.kind===kind))row(`本会话上传 · ${i.name}`,()=>choose({source:'upload',id:i.id},kind),async()=>i.content,kind==='material'?async()=>{await json('/api/personal-materials','POST',{source:{kind:'attachment',id:i.id,conversation_id:active}});notice('已存入个人资料库，可跨本人会话使用');}:null);
      for(const i of staged.filter(i=>i.kind===kind))row(`待发送文件 · ${i.filename}`,()=>choose({source:'staged',id:i.id},kind),async()=>i.content);
    });
  }
  $('pick-skill').onclick=run(()=>picker('skill'));$('pick-material').onclick=run(()=>picker('material'));
  $('upload-kind').onchange=()=>{const skill=$('upload-kind').value==='skill';$('upload-target').disabled=skill;if(skill)$('upload-target').value='upload';};
  $('upload-file').onclick=run(()=>{if(busy||uploading)throw new Error('请等待当前操作完成');$('context-file').click();});
  $('context-file').onchange=run(async()=>{const chosen=$('context-file').files[0];$('context-file').value='';if(!chosen)return;if(busy||uploading)throw new Error('请等待当前操作完成');
    const kind=$('upload-kind').value,target=$('upload-target').value,op=sequence;uploading=true;$('send').disabled=true;
    try{const content=await file(chosen,kind==='skill'?8000:12000);if(op!==sequence)return;let ref;
      if(target==='personal'&&kind==='material'){$('upload-state').textContent='正在保存个人资料…';const {material}=await json('/api/personal-materials','POST',{filename:chosen.name,content,subject:'通用'});personal.unshift(material);ref={source:'personal',id:material.id};}
      else if(active){$('upload-state').textContent='正在上传会话文件…';const {attachment}=await json(`/api/conversations/${active}/attachments`,'POST',{kind,filename:chosen.name,content});attachments.unshift(attachment);ref={source:'upload',id:attachment.id};}
      else {const item={id:++sequence,kind,filename:chosen.name,content};staged.push(item);ref={source:'staged',id:item.id};}
      uploading=false;choose(ref,kind);$('upload-state').textContent=ref.source==='staged'?`${chosen.name} · 已暂存，发送问题时上传`:`${chosen.name} · 已保存并选中`;
    }catch(err){$('upload-state').textContent=err.message+'；问题草稿保留';throw err;}finally{uploading=false;$('send').disabled=busy;}
  });
  $('question-form').onsubmit=run(async()=>{
    if(busy||uploading)throw new Error('请等待当前操作完成');if(!currentApp)throw new Error('请选择一个助手');const question=$('question').value.trim();if([...question].length<2||[...question].length>500)throw new Error('提问须为2–500字');
    busy=true;$('send').disabled=true;let user,reply,complete=false;notice('');
    try {
      if(!active){const data=currentApp.source==='builtin'?await json(`/api/apps/${currentApp.key}/launch`,'POST',{}):await json('/api/conversations','POST',{agent_id:currentApp.agent_id});active=data.conversation.id;currentApp.agent_id=data.conversation.agent_id;await refreshData();}
      const selectedKeys=new Set([...(context.materials||[]),...(context.skill?[context.skill]:[])].map(key));staged=staged.filter(i=>selectedKeys.has(key({source:'staged',id:i.id})));
      for(const item of [...staged]){
        const {attachment}=await json(`/api/conversations/${active}/attachments`,'POST',{kind:item.kind,filename:item.filename,content:item.content});attachments.push(attachment);
        const old={source:'staged',id:item.id},ref={source:'upload',id:attachment.id};if(context.skill&&key(context.skill)===key(old))context.skill=ref;
        if(context.materials)context.materials=context.materials.map(r=>key(r)===key(old)?ref:r);staged=staged.filter(s=>s.id!==item.id);
      } tags();$('welcome').hidden=true;$('history').hidden=false;user=bubble('user',question,'generating');reply=bubble('assistant','','generating');
      const response=await request(`/api/conversations/${active}/messages`,{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify({question,context})});
      await consumeSSE(response,(event,data)=>{
        if(event==='meta'){contextLine(user.n,data.context);renderSources(reply.n,data.sources);for(const call of data.tool_calls||[])reply.n.append(el('p',`${call.tool_ref} · ${call.status}${call.message?' · '+call.message:''}`,'state'));}
        if(event==='delta'){reply.body.textContent+=data.text;$('history').scrollTop=$('history').scrollHeight;}
        if(event==='done'){complete=true;user.state.textContent='你 · 已发送';reply.state.textContent='学习助手 · 已完成';$('question').value='';context={};staged=[];tags();$('upload-state').textContent='本轮完成，已恢复应用默认选择。';}
        if(event==='error')notice(data.message,true);
      });
    }catch(err){notice(err.message,true);}finally{if(!complete&&reply){reply.n.classList.add('partial');reply.state.textContent='学习助手 · 回答未完成';user.state.textContent='你 · 本轮未完成';}busy=false;$('send').disabled=false;await refreshConversations();}
  });
  $('new-chat').onclick=run(async()=>{if(!await guard())return;active=null;sequence++;reset();welcome();showView('chat');});
  $('nav-chat').onclick=()=>showView('chat');$('nav-library').onclick=run(async()=>{if(busy||uploading)throw new Error('请等待当前操作完成');showView('library');await CampusLibrary.refresh();});
  window.addEventListener('beforeunload',e=>{if(changed()||busy){e.preventDefault();e.returnValue='';}});
  try {const {user}=await json('/api/me');$('identity').textContent=user.username+' · '+(user.role==='teacher'?'教师':'学生');$('class-name').textContent=user.class_name;$('admin-link').hidden=user.role!=='teacher';
    await refreshData();apps=(await json('/api/apps')).apps;currentApp=apps.find(a=>a.enabled);drawApps();welcome();tags();await refreshConversations();showView(location.hash==='#library'||document.body.dataset.initialView==='library'?'library':'chat');
  }catch(err){notice(err.message,true);}
})();
