// Event Card Component JavaScript

class EventCard {
  constructor(element) {
    this.element = element;
    this.isExpanded = false;

    if (this.element) {
      this.init();
    }
  }

  init() {
    // Add click handler for expandable event cards
    if (this.element.dataset.expandable) {
      this.element.addEventListener("click", (e) => {
        // Don't expand if clicking a link
        if (e.target.tagName === "A") return;
        this.toggle();
      });
    }

    // Add navigation on card click
    const eventLink = this.element.dataset.eventLink;
    if (eventLink) {
      this.element.addEventListener("click", (e) => {
        if (e.target.tagName !== "A") {
          window.location.href = eventLink;
        }
      });
    }
  }

  toggle() {
    this.isExpanded = !this.isExpanded;
    this.element.classList.toggle("event-card--expanded");

    const content = this.element.querySelector(".event-card__content");
    if (content) {
      content.style.display = this.isExpanded ? "block" : "none";
    }
  }

  expand() {
    if (!this.isExpanded) {
      this.toggle();
    }
  }

  collapse() {
    if (this.isExpanded) {
      this.toggle();
    }
  }
}

// Initialize all event cards
document.addEventListener("DOMContentLoaded", () => {
  const eventCards = document.querySelectorAll(".event-card");
  eventCards.forEach((card) => {
    new EventCard(card);
  });
});

// Filter and search functionality for event lists
class EventFilter {
  constructor() {
    this.searchInput = document.getElementById("event-search");
    this.filterButtons = document.querySelectorAll("[data-filter]");
    this.eventCards = document.querySelectorAll(".event-card");

    if (this.searchInput || this.filterButtons.length > 0) {
      this.init();
    }
  }

  init() {
    if (this.searchInput) {
      this.searchInput.addEventListener(
        "input",
        window.utils.debounce((e) => {
          this.filterBySearch(e.target.value);
        }, 300)
      );
    }

    this.filterButtons.forEach((button) => {
      button.addEventListener("click", () => {
        const filterValue = button.dataset.filter;
        this.filterByType(filterValue);
      });
    });
  }

  filterBySearch(query) {
    const lowerQuery = query.toLowerCase();

    this.eventCards.forEach((card) => {
      const title = card.querySelector(".event-card__title")?.textContent || "";
      const matches = title.toLowerCase().includes(lowerQuery);
      card.style.display = matches ? "" : "none";
    });
  }

  filterByType(type) {
    this.eventCards.forEach((card) => {
      if (type === "all" || card.dataset.eventType === type) {
        card.style.display = "";
      } else {
        card.style.display = "none";
      }
    });

    // Update active button
    this.filterButtons.forEach((button) => {
      button.classList.toggle("active", button.dataset.filter === type);
    });
  }
}

// Initialize event filter if on events page
document.addEventListener("DOMContentLoaded", () => {
  if (document.querySelector(".event-card")) {
    new EventFilter();
  }
});
