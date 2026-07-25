
(function(){
  const KEY = 'akillicuzdan-theme';

  function getTheme(){
    try { return localStorage.getItem(KEY) || 'dark'; }
    catch(e){ return 'dark'; }
  }

  function setTheme(theme){
    const next = theme === 'light' ? 'light' : 'dark';
    document.documentElement.setAttribute('data-theme', next);
    try { localStorage.setItem(KEY, next); } catch(e) {}
    updateButtons(next);
  }

  function updateButtons(theme){
    document.querySelectorAll('[data-theme-toggle]').forEach(function(btn){
      const icon = btn.querySelector('i');
      const label = btn.querySelector('.theme-label');
      if(icon){ icon.className = theme === 'light' ? 'bi bi-moon-stars' : 'bi bi-sun'; }
      if(label){ label.textContent = theme === 'light' ? 'Koyu Tema' : 'Açık Tema'; }
      btn.setAttribute('aria-label', theme === 'light' ? 'Koyu temaya geç' : 'Açık temaya geç');
      btn.setAttribute('title', theme === 'light' ? 'Koyu temaya geç' : 'Açık temaya geç');
    });
  }

  function toggleTheme(){
    const current = document.documentElement.getAttribute('data-theme') || getTheme();
    setTheme(current === 'light' ? 'dark' : 'light');
  }

  window.AkilliTheme = { setTheme:setTheme, toggle:toggleTheme };
  setTheme(getTheme());

  document.addEventListener('DOMContentLoaded', function(){
    updateButtons(document.documentElement.getAttribute('data-theme') || getTheme());
    document.querySelectorAll('[data-theme-toggle]').forEach(function(btn){
      btn.addEventListener('click', toggleTheme);
    });
  });
})();
