// Navbar component JavaScript - Updated for Tailwind CSS
document.addEventListener("DOMContentLoaded", function () {
  const hamburgerBtn = document.getElementById("hamburger-toggle");
  const sidebar = document.getElementById("sidebar");
  const backdrop = document.getElementById("sidebar-backdrop");

  // Remove legacy 'collapsed' class if it exists (from cache)
  if (sidebar) {
    sidebar.classList.remove("collapsed");
  }

  // Toggle sidebar with backdrop
  function toggleSidebar() {
    const isOpen = !sidebar.classList.contains("-translate-x-full");

    if (isOpen) {
      // Close sidebar
      sidebar.classList.add("-translate-x-full");
      if (backdrop) {
        backdrop.classList.add("opacity-0", "pointer-events-none");
      }
    } else {
      // Open sidebar
      sidebar.classList.remove("-translate-x-full");
      if (backdrop) {
        backdrop.classList.remove("opacity-0", "pointer-events-none");
      }
    }
  }

  // Event listener for hamburger button
  if (hamburgerBtn) {
    hamburgerBtn.addEventListener("click", toggleSidebar);
  }

  // Close sidebar when clicking backdrop
  if (backdrop) {
    backdrop.addEventListener("click", toggleSidebar);
  }

  // Close sidebar on escape key
  document.addEventListener("keydown", function (e) {
    if (e.key === "Escape" && !sidebar.classList.contains("-translate-x-full")) {
      toggleSidebar();
    }
  });

  // Close sidebar when clicking a link (mobile only)
  const sidebarLinks = sidebar.querySelectorAll("a");
  sidebarLinks.forEach((link) => {
    link.addEventListener("click", function () {
      // Check if we're on mobile (< 768px)
      if (window.innerWidth < 768) {
        toggleSidebar();
      }
    });
  });

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
