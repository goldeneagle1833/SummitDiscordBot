// Navbar component JavaScript
document.addEventListener("DOMContentLoaded", function () {
  const hamburgerBtn = document.getElementById("hamburger-toggle");
  const sidebar = document.getElementById("sidebar");
  const backdrop = document.getElementById("sidebar-backdrop");

  // Toggle sidebar
  function toggleSidebar() {
    const isOpen = sidebar.classList.contains("open");

    if (isOpen) {
      // Close sidebar
      sidebar.classList.remove("open");
      if (backdrop) {
        backdrop.classList.add("opacity-0");
        backdrop.classList.remove("opacity-100");
        setTimeout(() => {
          backdrop.classList.add("hidden");
        }, 300);
      }
    } else {
      // Open sidebar
      sidebar.classList.add("open");
      if (backdrop) {
        backdrop.classList.remove("hidden");
        setTimeout(() => {
          backdrop.classList.add("opacity-100");
          backdrop.classList.remove("opacity-0");
        }, 10);
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
    if (e.key === "Escape" && sidebar.classList.contains("open")) {
      toggleSidebar();
    }
  });

  // Close sidebar when clicking a link
  const sidebarLinks = sidebar.querySelectorAll("a");
  sidebarLinks.forEach((link) => {
    link.addEventListener("click", function () {
      if (sidebar.classList.contains("open")) {
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
