// Navbar component JavaScript
document.addEventListener("DOMContentLoaded", function () {
  const hamburgerBtn = document.getElementById("hamburger-toggle");
  const sidebar = document.getElementById("sidebar");

  // Check if we're on mobile
  function isMobile() {
    return window.innerWidth <= 768;
  }

  // Initialize sidebar state based on screen size
  function initializeSidebar() {
    if (isMobile()) {
      // On mobile, start collapsed
      sidebar.classList.remove("open");
      sidebar.classList.add("collapsed");
    } else {
      // On desktop, start open
      sidebar.classList.add("open");
      sidebar.classList.remove("collapsed");
    }
  }

  // Toggle sidebar
  function toggleSidebar() {
    if (isMobile()) {
      // On mobile: toggle open/closed
      sidebar.classList.toggle("open");
    } else {
      // On desktop: toggle collapsed/expanded
      sidebar.classList.toggle("collapsed");
    }
  }

  // Event listener for hamburger button
  if (hamburgerBtn) {
    hamburgerBtn.addEventListener("click", toggleSidebar);
  }

  // Close sidebar on escape key (mobile only)
  document.addEventListener("keydown", function (e) {
    if (
      e.key === "Escape" &&
      isMobile() &&
      sidebar.classList.contains("open")
    ) {
      sidebar.classList.remove("open");
    }
  });

  // Close sidebar when clicking a link on mobile
  const sidebarLinks = sidebar.querySelectorAll(".sidebar-link");
  sidebarLinks.forEach((link) => {
    link.addEventListener("click", function () {
      if (isMobile()) {
        sidebar.classList.remove("open");
      }
    });
  });

  // Handle window resize
  let resizeTimer;
  window.addEventListener("resize", function () {
    clearTimeout(resizeTimer);
    resizeTimer = setTimeout(function () {
      initializeSidebar();
    }, 250);
  });

  // Initialize on load
  initializeSidebar();

  // Secret easter egg: Triple-click the brand name to access secret fart leaderboard
  const brandLink = document.getElementById("brand-secret");
  if (brandLink) {
    let clickCount = 0;
    let clickTimer;

    brandLink.addEventListener("click", function (e) {
      clickCount++;

      if (clickCount === 3) {
        e.preventDefault();
        window.location.href = "/secret-fart-leaderboard";
        clickCount = 0;
        clearTimeout(clickTimer);
        return;
      }

      // Reset click count after 600ms if not triple-clicked
      clearTimeout(clickTimer);
      clickTimer = setTimeout(() => {
        clickCount = 0;
      }, 600);
    });
  }
});
