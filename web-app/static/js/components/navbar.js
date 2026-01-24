// Navbar component JavaScript
document.addEventListener("DOMContentLoaded", function () {
  try {
    console.log("[navbar] DOMContentLoaded");
    const hamburgerBtn = document.getElementById("hamburger-toggle");
    const sidebar = document.getElementById("sidebar");
    const backdrop = document.getElementById("sidebar-backdrop");

    console.log("[navbar] elements:", {
      hamburgerBtn: !!hamburgerBtn,
      sidebar: !!sidebar,
      backdrop: !!backdrop,
    });

    // Toggle sidebar
    function toggleSidebar() {
      try {
        const isOpen = sidebar && sidebar.classList.contains("open");
        console.log("[navbar] toggleSidebar called, isOpen=", isOpen);

        if (isOpen) {
          // Close sidebar
          sidebar.classList.remove("open");
          console.log("[navbar] closing sidebar");
          if (backdrop) {
            backdrop.classList.add("opacity-0");
            backdrop.classList.remove("opacity-100");
            setTimeout(() => {
              backdrop.classList.add("hidden");
              console.log("[navbar] backdrop hidden");
            }, 300);
          }
        } else {
          // Open sidebar
          if (sidebar) sidebar.classList.add("open");
          console.log("[navbar] opening sidebar");
          if (backdrop) {
            backdrop.classList.remove("hidden");
            setTimeout(() => {
              backdrop.classList.add("opacity-100");
              backdrop.classList.remove("opacity-0");
              console.log("[navbar] backdrop shown 12345");
            }, 10);
          }
        }
      } catch (err) {
        console.error("[navbar] toggleSidebar error:", err);
      }
    }

    // Event listener for hamburger button
    if (hamburgerBtn) {
      console.log("[navbar] attaching click listener to hamburgerBtn");
      hamburgerBtn.addEventListener("click", function (e) {
        console.log("[navbar] hamburger clicked", e);
        toggleSidebar();
      });
    } else {
      console.warn("[navbar] hamburgerBtn not found");
    }

    // Close sidebar when clicking backdrop
    if (backdrop) {
      console.log("[navbar] attaching click listener to backdrop");
      backdrop.addEventListener("click", function (e) {
        console.log("[navbar] backdrop clicked", e);
        toggleSidebar();
      });
    }

    // Close sidebar on escape key
    document.addEventListener("keydown", function (e) {
      if (e.key === "Escape" && sidebar && sidebar.classList.contains("open")) {
        console.log("[navbar] Escape pressed, closing sidebar");
        toggleSidebar();
      }
    });

    // Close sidebar when clicking a link
    if (sidebar) {
      const sidebarLinks = sidebar.querySelectorAll("a");
      sidebarLinks.forEach((link) => {
        link.addEventListener("click", function (ev) {
          console.log(
            "[navbar] sidebar link clicked",
            link.href || link.textContent
          );
          if (sidebar.classList.contains("open")) {
            toggleSidebar();
          }
        });
      });
    } else {
      console.warn(
        "[navbar] sidebar element not found; cannot attach link handlers"
      );
    }

    // Secret easter egg: Triple-click the brand name to access secret fart leaderboard
    const brandLink = document.getElementById("brand-secret");
    if (brandLink) {
      let clickCount = 0;
      let clickTimer;

      brandLink.addEventListener("click", function (e) {
        clickCount++;
        console.log("[navbar] brand click count:", clickCount);

        if (clickCount === 3) {
          e.preventDefault();
          console.log(
            "[navbar] triple-click detected, navigating to secret leaderboard"
          );
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
  } catch (e) {
    console.error("[navbar] initialization error:", e);
  }
});
