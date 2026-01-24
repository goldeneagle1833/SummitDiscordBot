// Navbar component JavaScript - Icon-based sidebar
document.addEventListener("DOMContentLoaded", function () {
  const sidebarToggle = document.getElementById("sidebar-toggle");
  const sidebar = document.getElementById("sidebar");
  const sidebarTexts = document.querySelectorAll(".sidebar-text");

  // Check if sidebar was expanded (from localStorage)
  const isExpanded = localStorage.getItem("sidebarExpanded") === "true";
  if (isExpanded) {
    expandSidebar();
  }

  // Toggle sidebar width
  function toggleSidebar() {
    if (sidebar.classList.contains("w-16")) {
      expandSidebar();
      localStorage.setItem("sidebarExpanded", "true");
    } else {
      collapseSidebar();
      localStorage.setItem("sidebarExpanded", "false");
    }
  }

  function expandSidebar() {
    sidebar.classList.remove("w-16");
    sidebar.classList.add("w-60");
    sidebarTexts.forEach(text => {
      text.classList.remove("opacity-0", "w-0");
      text.classList.add("opacity-100", "w-auto");
    });
  }

  function collapseSidebar() {
    sidebar.classList.remove("w-60");
    sidebar.classList.add("w-16");
    sidebarTexts.forEach(text => {
      text.classList.remove("opacity-100", "w-auto");
      text.classList.add("opacity-0", "w-0");
    });
  }

  // Event listener for toggle button
  if (sidebarToggle) {
    sidebarToggle.addEventListener("click", toggleSidebar);
  }

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
