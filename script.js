document.addEventListener('DOMContentLoaded', () => {
  const startBtn = document.getElementById('start-button');
  const loadingScreen = document.getElementById('loading-screen');
  const app = document.getElementById('app');

  // Simple accessible activation (click or Enter/Space)
  startBtn.addEventListener('click', startApp);
  startBtn.addEventListener('keydown', (e) => {
    if (e.key === 'Enter' || e.key === ' ') startApp();
  });

  function startApp() {
    // small animation: fade out loading screen
    loadingScreen.style.transition = 'opacity 360ms ease, transform 360ms ease';
    loadingScreen.style.opacity = '0';
    loadingScreen.style.transform = 'translateY(-10px)';
    startBtn.disabled = true;

    // after transition, hide and reveal app
    setTimeout(() => {
      loadingScreen.classList.add('hidden');
      app.classList.remove('hidden');
      // focus first meaningful element in the app (friendly for keyboard users)
      const first = app.querySelector('h2, button, a, input');
      if (first) first.focus();
      console.log('Started Meteor Madness');
    }, 380);
  }
});
