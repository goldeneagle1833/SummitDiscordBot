// Leaderboard Component JavaScript

class Leaderboard {
  constructor(containerId, options = {}) {
    this.container = document.getElementById(containerId);
    this.options = {
      sortable: true,
      paginated: true,
      itemsPerPage: 50,
      autoRefresh: false,
      refreshInterval: 30000,
      ...options,
    };

    this.currentPage = 1;
    this.sortColumn = "rank";
    this.sortDirection = "asc";
    this.data = [];

    if (this.container) {
      this.init();
    }
  }

  init() {
    if (this.options.sortable) {
      this.initializeSorting();
    }

    if (this.options.paginated) {
      this.initializePagination();
    }

    if (this.options.autoRefresh) {
      this.startAutoRefresh();
    }
  }

  initializeSorting() {
    const headers = this.container.querySelectorAll("th[data-sortable]");

    headers.forEach((header) => {
      header.style.cursor = "pointer";
      header.addEventListener("click", () => {
        const column = header.dataset.sortable;
        this.sortBy(column);
      });
    });
  }

  sortBy(column) {
    if (this.sortColumn === column) {
      this.sortDirection = this.sortDirection === "asc" ? "desc" : "asc";
    } else {
      this.sortColumn = column;
      this.sortDirection = "asc";
    }

    // Implement sorting logic here
    this.renderTable();
  }

  initializePagination() {
    const pagination = this.container.querySelector(".leaderboard__pagination");
    if (!pagination) return;

    const prevBtn = pagination.querySelector('[data-action="prev"]');
    const nextBtn = pagination.querySelector('[data-action="next"]');

    if (prevBtn) {
      prevBtn.addEventListener("click", () => this.prevPage());
    }

    if (nextBtn) {
      nextBtn.addEventListener("click", () => this.nextPage());
    }
  }

  nextPage() {
    const maxPages = Math.ceil(this.data.length / this.options.itemsPerPage);
    if (this.currentPage < maxPages) {
      this.currentPage++;
      this.renderTable();
    }
  }

  prevPage() {
    if (this.currentPage > 1) {
      this.currentPage--;
      this.renderTable();
    }
  }

  startAutoRefresh() {
    setInterval(() => {
      this.refresh();
    }, this.options.refreshInterval);
  }

  async refresh() {
    // Implement data refresh logic
    console.log("Refreshing leaderboard data...");
  }

  renderTable() {
    // Implement table rendering logic
    console.log("Rendering leaderboard table...");
  }

  setData(data) {
    this.data = data;
    this.renderTable();
  }

  destroy() {
    // Clean up event listeners
    this.container.innerHTML = "";
  }
}

// Initialize leaderboards on page load
document.addEventListener("DOMContentLoaded", () => {
  const leaderboardElement = document.querySelector(".leaderboard");
  if (leaderboardElement && leaderboardElement.id) {
    window.leaderboard = new Leaderboard(leaderboardElement.id, {
      autoRefresh: true,
      refreshInterval: 60000, // 1 minute
    });
  }
});
