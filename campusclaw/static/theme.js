// Only visual preferences are persistent. Credentials stay in sessionStorage.
try { document.documentElement.dataset.theme = localStorage.getItem('campusclaw_theme') === 'dark' ? 'dark' : 'light'; } catch {}
window.toggleCampusTheme = () => {
  const theme = document.documentElement.dataset.theme === 'dark' ? 'light' : 'dark';
  document.documentElement.dataset.theme = theme;
  try {localStorage.setItem('campusclaw_theme', theme);} catch {}
  const button = document.getElementById('theme-toggle');
  if (button) button.setAttribute('aria-pressed', String(theme === 'dark'));
};
