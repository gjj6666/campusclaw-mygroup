from .pages import head, dialog, scripts


def tutor_page(library=False):
    return head('CampusClaw · 学习工作区') + '<body data-initial-view="' + ('library' if library else 'chat') + '">' + WORKSPACE + dialog() + scripts('tutor.js', 'library_ui.js', 'workspace.js')


WORKSPACE = """
<div class="app-shell"><div id="nav-backdrop" class="nav-backdrop"></div>
<nav class="global-nav" aria-label="主导航"><div class="brand-block"><span class="brand">CAMPUSCLAW</span><p id="class-name" class="muted">学习空间</p></div>
<div class="global-links"><button id="nav-chat" type="button" class="selected"><span class="nav-icon">智</span>智能体</button><button id="nav-library" type="button"><span class="nav-icon">资</span>资料库</button><a href="/admin" id="admin-link" hidden><span class="nav-icon">管</span>教师管理</a></div>
<div class="account"><strong id="identity">正在验证登录…</strong><div class="actions"><button type="button" id="theme-toggle" class="ghost" aria-label="切换深浅主题">◐ 主题</button><button id="logout" class="ghost">退出</button></div></div></nav>
<aside class="side-list" id="sidebar"><div id="chat-sidebar"><h2>学习助手</h2><div id="app-list"></div><button id="new-chat" type="button" class="ghost">＋ 新对话</button><p class="section-label">最近对话</p><div id="conversations"></div></div>
<div id="library-sidebar" hidden><h2>资料库</h2><div id="material-groups"></div><button id="personal-upload" type="button" class="ghost">＋ 上传个人资料</button></div></aside>
<main class="main-area"><header class="topbar"><button id="nav-toggle" type="button" class="secondary mobile-menu" aria-label="展开主导航" aria-expanded="false">☰</button><strong id="view-title">学习工作区</strong><span class="badge right" id="view-badge">一起探索</span></header><p id="notice" class="notice" role="status"></p>
<section id="chat-view" class="chat-workspace"><div id="welcome" class="welcome"><span class="welcome-mark">✦</span><h1 id="welcome-title">你的学习助手，我帮你</h1><p id="welcome-description">带上技能与资料，写下你卡在哪一步。</p><div id="suggestions" class="suggestions"></div></div><div id="history" class="history" aria-live="polite" hidden></div>
<form id="question-form" class="question-form"><label for="question">你的问题（2–500字）</label><textarea id="question" minlength="2" maxlength="500" required placeholder="今天想解决什么问题？写下你的思路…"></textarea>
<div class="composer-tools"><button type="button" id="pick-skill">＋ 技能</button><button type="button" id="pick-material">＋ 资料</button><label>上传<select id="upload-kind" aria-label="上传类型"><option value="material">资料</option><option value="skill">技能</option></select></label><label>范围<select id="upload-target" aria-label="上传范围"><option value="upload">仅本会话</option><option value="personal">个人资料库</option></select></label><button type="button" id="upload-file">↑ 选择文件</button><input type="file" id="context-file" accept=".md,.txt" hidden></div>
<div id="context-tags" class="context-tags" aria-label="本轮上下文"></div><div class="composer-bottom"><p class="state" id="upload-state" role="status">UTF-8 .md/.txt · 最多32 KiB · 选择只作用于本轮</p><button id="send" type="submit" class="send" aria-label="发送问题">↑</button></div></form></section>
<section id="library-view" class="library-workspace" hidden><div class="toolbar"><input id="material-filter" placeholder="按标题筛选资料" aria-label="按标题筛选资料"><button id="list-mode" type="button" class="secondary">列表</button><button id="grid-mode" type="button" class="secondary">网格</button></div><div id="material-list" class="material-list"></div><div id="reading" class="reading" hidden><div class="actions"><button id="back-materials" class="secondary" type="button">← 返回资料</button><button id="save-personal" type="button">保存到我的资料</button></div><p id="reading-meta" class="state"></p><article id="reader" class="reader"></article></div></section>
</main></div>
"""
