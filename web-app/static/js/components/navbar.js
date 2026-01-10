// Navbar component JavaScript
document.addEventListener("DOMContentLoaded", function () {
  const hamburgerBtn = document.getElementById("hamburger-toggle");
  const sidebar = document.getElementById("sidebar");
  const sidebarOverlay = document.getElementById("sidebar-overlay");
  const closeBtn = document.getElementById("sidebar-close");

  // Open sidebar
  function openSidebar() {
    sidebar.classList.add("open");
    sidebarOverlay.classList.add("visible");
    document.body.style.overflow = "hidden"; // Prevent background scrolling
  }

  // Close sidebar
  function closeSidebar() {
    sidebar.classList.remove("open");
    sidebarOverlay.classList.remove("visible");
    document.body.style.overflow = ""; // Restore scrolling
  }

  // Event listeners
  if (hamburgerBtn) {
    hamburgerBtn.addEventListener("click", openSidebar);
  }

  if (closeBtn) {
    closeBtn.addEventListener("click", closeSidebar);
  }

  if (sidebarOverlay) {
    sidebarOverlay.addEventListener("click", closeSidebar);
  }

  // Close sidebar on escape key
  document.addEventListener("keydown", function (e) {
    if (e.key === "Escape" && sidebar.classList.contains("open")) {
      closeSidebar();
    }
  });

  // Close sidebar when clicking a link (optional, for better UX)
  const sidebarLinks = sidebar.querySelectorAll(".sidebar-link");
  sidebarLinks.forEach((link) => {
    link.addEventListener("click", closeSidebar);
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
