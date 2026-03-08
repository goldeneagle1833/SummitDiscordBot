// Main JavaScript - Global functionality

document.addEventListener("DOMContentLoaded", () => {
  // Initialize all components
  initializeScrollEffects();
  initializeTooltips();
});

// Scroll effects
function initializeScrollEffects() {
  let lastScroll = 0;
  const navbar = document.querySelector(".navbar");

  if (!navbar) return;

  window.addEventListener("scroll", () => {
    const currentScroll = window.pageYOffset;

    // Add shadow on scroll
    if (currentScroll > 10) {
      navbar.classList.add("navbar--scrolled");
    } else {
      navbar.classList.remove("navbar--scrolled");
    }

    lastScroll = currentScroll;
  });
}

// Simple tooltip system
function initializeTooltips() {
  const tooltipElements = document.querySelectorAll("[data-tooltip]");

  tooltipElements.forEach((element) => {
    element.addEventListener("mouseenter", showTooltip);
    element.addEventListener("mouseleave", hideTooltip);
  });

  function showTooltip(e) {
    const text = e.target.getAttribute("data-tooltip");
    if (!text) return;

    const tooltip = document.createElement("div");
    tooltip.className = "tooltip";
    tooltip.textContent = text;
    tooltip.id = "active-tooltip";

    document.body.appendChild(tooltip);

    const rect = e.target.getBoundingClientRect();
    tooltip.style.top = `${rect.top - tooltip.offsetHeight - 8}px`;
    tooltip.style.left = `${
      rect.left + rect.width / 2 - tooltip.offsetWidth / 2
    }px`;
  }

  function hideTooltip() {
    const tooltip = document.getElementById("active-tooltip");
    if (tooltip) {
      tooltip.remove();
    }
  }
}

// Utility: Debounce function
function debounce(func, wait) {
  let timeout;
  return function executedFunction(...args) {
    const later = () => {
      clearTimeout(timeout);
      func(...args);
    };
    clearTimeout(timeout);
    timeout = setTimeout(later, wait);
  };
}

// Utility: Throttle function
function throttle(func, limit) {
  let inThrottle;
  return function () {
    const args = arguments;
    const context = this;
    if (!inThrottle) {
      func.apply(context, args);
      inThrottle = true;
      setTimeout(() => (inThrottle = false), limit);
    }
  };
}

// Utility: Format numbers
function formatNumber(num) {
  return new Intl.NumberFormat().format(num);
}

// Utility: Calculate win rate
function calculateWinRate(wins, losses) {
  const total = wins + losses;
  if (total === 0) return "0.0";
  return ((wins / total) * 100).toFixed(1);
}

// Export utilities
window.utils = {
  debounce,
  throttle,
  formatNumber,
  calculateWinRate,
};
