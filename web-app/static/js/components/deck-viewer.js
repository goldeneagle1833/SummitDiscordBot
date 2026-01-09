// Deck Viewer Component JavaScript

class DeckViewer {
  constructor(containerId, deckData) {
    this.container = document.getElementById(containerId);
    this.deckData = deckData;

    if (this.container && this.deckData) {
      this.init();
    }
  }

  init() {
    this.render();
    this.attachEventListeners();
  }

  render() {
    // Organize cards by type
    const cardsByType = this.organizeCardsByType();

    // Calculate deck stats
    const stats = this.calculateStats();

    // Render the deck
    this.container.innerHTML = this.generateHTML(cardsByType, stats);
  }

  organizeCardsByType() {
    const types = {};

    this.deckData.cards.forEach((card) => {
      const type = card.type || "Unknown";
      if (!types[type]) {
        types[type] = [];
      }
      types[type].push(card);
    });

    return types;
  }

  calculateStats() {
    let totalCards = 0;
    let totalCost = 0;
    const elements = { earth: 0, air: 0, water: 0, fire: 0 };

    this.deckData.cards.forEach((card) => {
      totalCards += card.quantity || 1;
      totalCost += (card.cost || 0) * (card.quantity || 1);

      if (card.elements) {
        const cardElements = card.elements.toLowerCase();
        if (cardElements.includes("earth")) elements.earth++;
        if (cardElements.includes("air")) elements.air++;
        if (cardElements.includes("water")) elements.water++;
        if (cardElements.includes("fire")) elements.fire++;
      }
    });

    return {
      totalCards,
      avgCost: totalCards > 0 ? (totalCost / totalCards).toFixed(1) : 0,
      elements,
    };
  }

  generateHTML(cardsByType, stats) {
    return `
      <div class="deck-viewer__header">
        <div>
          <h2 class="deck-viewer__title">${
            this.deckData.name || "Unnamed Deck"
          }</h2>
          <p class="deck-viewer__subtitle">by ${
            this.deckData.username || "Unknown"
          }</p>
        </div>
        <div class="deck-viewer__actions">
          <button class="btn btn--outline btn--sm" data-action="export">Export</button>
          <button class="btn btn--primary btn--sm" data-action="copy">Copy Link</button>
        </div>
      </div>

      <div class="deck-stats">
        <div class="deck-stat">
          <span class="deck-stat__value">${stats.totalCards}</span>
          <span class="deck-stat__label">Total Cards</span>
        </div>
        <div class="deck-stat">
          <span class="deck-stat__value">${stats.avgCost}</span>
          <span class="deck-stat__label">Avg Cost</span>
        </div>
        ${Object.entries(stats.elements)
          .map(
            ([element, count]) => `
          <div class="deck-stat">
            <span class="deck-stat__value">${count}</span>
            <span class="deck-stat__label">${element}</span>
          </div>
        `
          )
          .join("")}
      </div>

      ${Object.entries(cardsByType)
        .map(
          ([type, cards]) => `
        <div class="deck-viewer__section">
          <h3 class="deck-viewer__section-title">${type} (${cards.length})</h3>
          <div class="deck-viewer__cards">
            ${cards
              .map(
                (card) => `
              <div class="deck-card" data-card-id="${card.identifier || ""}">
                <div class="deck-card__name">${card.name || "Unknown"}</div>
                <div class="deck-card__details">
                  <span class="deck-card__cost">Cost: ${
                    card.cost !== null ? card.cost : "N/A"
                  }</span>
                  <span class="deck-card__quantity">x${
                    card.quantity || 1
                  }</span>
                </div>
              </div>
            `
              )
              .join("")}
          </div>
        </div>
      `
        )
        .join("")}
    `;
  }

  attachEventListeners() {
    // Export button
    const exportBtn = this.container.querySelector('[data-action="export"]');
    if (exportBtn) {
      exportBtn.addEventListener("click", () => this.exportDeck());
    }

    // Copy link button
    const copyBtn = this.container.querySelector('[data-action="copy"]');
    if (copyBtn) {
      copyBtn.addEventListener("click", () => this.copyLink());
    }

    // Card hover/click events
    const cards = this.container.querySelectorAll(".deck-card");
    cards.forEach((card) => {
      card.addEventListener("click", () => {
        const cardId = card.dataset.cardId;
        this.showCardDetails(cardId);
      });
    });
  }

  exportDeck() {
    const exportData = JSON.stringify(this.deckData, null, 2);
    const blob = new Blob([exportData], { type: "application/json" });
    const url = URL.createObjectURL(blob);
    const a = document.createElement("a");
    a.href = url;
    a.download = `${this.deckData.name || "deck"}.json`;
    a.click();
    URL.revokeObjectURL(url);
  }

  copyLink() {
    const deckId = this.deckData.id;
    const url = `https://curiosa.io/decks/${deckId}`;

    navigator.clipboard
      .writeText(url)
      .then(() => {
        alert("Deck link copied to clipboard!");
      })
      .catch((err) => {
        console.error("Failed to copy:", err);
      });
  }

  showCardDetails(cardId) {
    console.log("Show card details for:", cardId);
    // Implement card detail modal or tooltip
  }
}

// Export for use in other scripts
window.DeckViewer = DeckViewer;
