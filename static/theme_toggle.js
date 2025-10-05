// theme_toggle.js
// Simple theme toggle (dark / light) persisted to localStorage.
(function () {
  const KEY = 'site-theme';
  const root = document.documentElement || document.body;
  function findButtons(){ return Array.from(document.querySelectorAll('#themeToggle, [data-theme-toggle]')); }

  function applyTheme(t) {
    if (t === 'dark') {
      root.classList.add('theme-dark');
      root.classList.remove('theme-light');
      findButtons().forEach(b=>{ b.textContent = 'Light mode'; });
    } else {
      root.classList.add('theme-light');
      root.classList.remove('theme-dark');
      findButtons().forEach(b=>{ b.textContent = 'Dark mode'; });
    }
  }

  function getStored() {
    try { return localStorage.getItem(KEY); } catch (e) { return null; }
  }

  function setStored(v) {
    try { localStorage.setItem(KEY, v); } catch (e) { }
  }

  // Initialise after DOM ready so buttons exist
  document.addEventListener('DOMContentLoaded', function(){
    const stored = getStored();
    if (stored) applyTheme(stored);
    else {
      // prefer dark by default if user prefers-colour-scheme
      const prefersDark = window.matchMedia && window.matchMedia('(prefers-color-scheme: dark)').matches;
      applyTheme(prefersDark ? 'dark' : 'light');
    }

    // attach listeners to any buttons
    findButtons().forEach(b=>{
      b.addEventListener('click', function(){
        const current = getStored() || (document.documentElement.classList.contains('theme-dark') ? 'dark' : 'light');
        const next = current === 'dark' ? 'light' : 'dark';
        applyTheme(next);
        setStored(next);
      });
    });
  });

})();
