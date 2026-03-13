// Landing page JS — navbar scroll effect + particle animation

// Navbar scroll
const navbar = document.getElementById('navbar');
window.addEventListener('scroll', () => {
  if (window.scrollY > 40) {
    navbar.classList.add('scrolled');
  } else {
    navbar.classList.remove('scrolled');
  }
});

// Create floating particles
function createParticles() {
  const container = document.getElementById('particles');
  if (!container) return;
  for (let i = 0; i < 30; i++) {
    const p = document.createElement('div');
    p.style.cssText = `
      position:absolute;
      width:${Math.random() * 3 + 1}px;
      height:${Math.random() * 3 + 1}px;
      background:rgba(0,198,255,${Math.random() * 0.4 + 0.1});
      border-radius:50%;
      left:${Math.random() * 100}%;
      top:${Math.random() * 100}%;
      animation:float ${Math.random() * 6 + 4}s ease-in-out infinite;
      animation-delay:${Math.random() * 6}s;
    `;
    container.appendChild(p);
  }
}
createParticles();

// Smooth scroll for anchor links
document.querySelectorAll('a[href^="#"]').forEach(a => {
  a.addEventListener('click', (e) => {
    const target = document.querySelector(a.getAttribute('href'));
    if (target) {
      e.preventDefault();
      target.scrollIntoView({ behavior: 'smooth', block: 'start' });
    }
  });
});

// Intersection observer for fade-in animations
const observer = new IntersectionObserver((entries) => {
  entries.forEach(entry => {
    if (entry.isIntersecting) {
      entry.target.classList.add('animate-fadeInUp');
      observer.unobserve(entry.target);
    }
  });
}, { threshold: 0.1 });

document.querySelectorAll('.feature-card, .step-item').forEach(el => {
  observer.observe(el);
});

// Check login status for landing page buttons
const landingUid = localStorage.getItem('sv_uid');
if (landingUid) {
  const loginBtn = document.getElementById('login-btn');
  const getStartedBtn = document.getElementById('get-started-btn');
  const heroCtaBtn = document.getElementById('hero-cta-btn');
  const ctaFinalBtn = document.getElementById('cta-final-btn');

  if (loginBtn) {
    loginBtn.textContent = 'Dashboard';
    loginBtn.href = '/dashboard';
  }
  if (getStartedBtn) {
    getStartedBtn.textContent = 'Go to Slides';
    getStartedBtn.href = '/dashboard';
  }
  if (heroCtaBtn) {
    heroCtaBtn.innerHTML = `<svg width="20" height="20" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2.5"><rect x="3" y="3" width="7" height="7"/><rect x="14" y="3" width="7" height="7"/><rect x="3" y="14" width="7" height="7"/><rect x="14" y="14" width="7" height="7"/></svg> Go to Dashboard`;
    heroCtaBtn.href = '/dashboard';
  }
  if (ctaFinalBtn) {
    ctaFinalBtn.textContent = 'Go to Dashboard';
    ctaFinalBtn.href = '/dashboard';
  }
}
