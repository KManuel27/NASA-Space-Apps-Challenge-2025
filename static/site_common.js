// site_common.js - consolidated client logic: theme toggle, tabs, sidebar and Plotly relayout
(function(){
  const THEME_KEY = 'site-theme';
  const root = document.documentElement;

  function findThemeButtons(){ return Array.from(document.querySelectorAll('#themeToggle, [data-theme-toggle]')); }

  function applyTheme(t){
    if(t === 'dark'){
      root.classList.add('theme-dark'); root.classList.remove('theme-light');
      findThemeButtons().forEach(b=> b.textContent = 'Light mode');
    } else {
      root.classList.add('theme-light'); root.classList.remove('theme-dark');
      findThemeButtons().forEach(b=> b.textContent = 'Dark mode');
    }
  }

  function getStored(){ try { return localStorage.getItem(THEME_KEY); } catch(e){ return null; } }
  function setStored(v){ try{ localStorage.setItem(THEME_KEY, v); } catch(e){} }

  // Tabs behaviour (any page using role=tab)
  function initTabs(){
    const tabs = Array.from(document.querySelectorAll('[role="tab"]'));
    if(!tabs.length) return;
    const panels = Array.from(document.querySelectorAll('.tab-panel'));
    function selectTab(tab){
      tabs.forEach(t=>t.setAttribute('aria-selected','false'));
      tab.setAttribute('aria-selected','true');
      panels.forEach(p=>p.classList.add('hidden'));
      const id = 'tab-' + tab.dataset.tab;
      const el = document.getElementById(id);
      if(el) el.classList.remove('hidden');
    }
    tabs.forEach(t=> t.addEventListener('click', ()=> selectTab(t)) );
    const initial = tabs.find(t=> t.getAttribute('aria-selected') === 'true') || tabs[0];
    if(initial) selectTab(initial);
  }

  // Sidebar open/close helpers used by meteorViz template
  function makeSidebarControls(){
    const openBtn = document.getElementById('openBtn');
    const sidebar = document.getElementById('mySidebar');
    if(!sidebar) return;
    window.openSidebar = function(){
      sidebar.classList.add('open');
      if(openBtn) sidebar.addEventListener('transitionend', function onEnd(e){ if(e.propertyName==='width'){ if(openBtn) openBtn.style.display='none'; sidebar.removeEventListener('transitionend', onEnd);} });
    };
    window.closeSidebar = function(){ if(openBtn) openBtn.style.display='block'; sidebar.classList.remove('open'); };
    // attach click handlers if elements exist
    if(openBtn) openBtn.addEventListener('click', openSidebar);
    const closeBtn = sidebar.querySelector('.closebtn');
    if(closeBtn) closeBtn.addEventListener('click', closeSidebar);
  }

  // Plotly relayout to adopt theme colours and transparent backgrounds
  function syncPlotlyTheme(){
    if(typeof Plotly === 'undefined') return;
    const plots = document.querySelectorAll('.js-plotly-plot');
    const isDark = root.classList.contains('theme-dark');
    const textcolor = (isDark ? getComputedStyle(root).getPropertyValue('--text-dark') : getComputedStyle(root).getPropertyValue('--text-light')) || (isDark ? '#f7f9fb' : '#0b1220');
    plots.forEach(div=>{
      try{
        Plotly.relayout(div, {
          'paper_bgcolor': 'rgba(0,0,0,0)',
          'plot_bgcolor': 'rgba(0,0,0,0)',
          'font.color': textcolor.trim()
        });
      }catch(e){}
      try{ div.on('plotly_afterplot', function(){ Plotly.relayout(div, {'font.color': textcolor.trim()}); }); }catch(e){}
    });
  }

  document.addEventListener('DOMContentLoaded', function(){
    // Theme init
    const stored = getStored();
    if(stored) applyTheme(stored);
    else {
      const prefersDark = window.matchMedia && window.matchMedia('(prefers-color-scheme: dark)').matches;
      applyTheme(prefersDark ? 'dark' : 'light');
    }
    findThemeButtons().forEach(b=> b.addEventListener('click', function(){ const current = getStored() || (root.classList.contains('theme-dark') ? 'dark' : 'light'); const next = current === 'dark' ? 'light' : 'dark'; applyTheme(next); setStored(next); }));

    // Init tabs and sidebar
    initTabs();
    makeSidebarControls();

    // Sync Plotly colours (if used)
    syncPlotlyTheme();
  });

})();
