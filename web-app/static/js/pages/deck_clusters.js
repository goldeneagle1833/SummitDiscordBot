/**
 * Page: Deck Clusters
 * Template: templates/pages/deck_clusters.html
 * Description: Hierarchical clustering of match report decks by card similarity
 */

let currentMetric = "distinct";
let currentScope = "spells";
let lastData = null;

document.addEventListener("DOMContentLoaded", () => {
  initControls();
});

function initControls() {
  const analyzeBtn = document.getElementById("analyze-btn");
  const thresholdSlider = document.getElementById("threshold-slider");
  const thresholdValue = document.getElementById("threshold-value");

  thresholdSlider.addEventListener("input", () => {
    thresholdValue.textContent = parseFloat(thresholdSlider.value).toFixed(2);
  });

  analyzeBtn.addEventListener("click", fetchClusters);

  // Metric toggles
  document.querySelectorAll("[data-metric]").forEach((btn) => {
    btn.addEventListener("click", () => {
      document.querySelectorAll("[data-metric]").forEach((b) => b.classList.remove("active"));
      btn.classList.add("active");
      currentMetric = btn.dataset.metric;
    });
  });

  // Scope toggles
  document.querySelectorAll("[data-scope]").forEach((btn) => {
    btn.addEventListener("click", () => {
      document.querySelectorAll("[data-scope]").forEach((b) => b.classList.remove("active"));
      btn.classList.add("active");
      currentScope = btn.dataset.scope;
    });
  });
}

async function fetchClusters() {
  const threshold = document.getElementById("threshold-slider").value;

  document.getElementById("results").style.display = "none";
  document.getElementById("error-section").style.display = "none";
  document.getElementById("loading").style.display = "flex";

  try {
    const url = `/api/deck-clusters?threshold=${threshold}&metric=${currentMetric}&scope=${currentScope}`;
    const res = await fetch(url);

    if (!res.ok) {
      const err = await res.json().catch(() => ({}));
      throw new Error(err.error || `Request failed (${res.status})`);
    }

    const data = await res.json();
    lastData = data;

    document.getElementById("loading").style.display = "none";
    document.getElementById("results").style.display = "block";

    renderSummary(data);
    renderClusterGroups(data);
    renderHeatmap(data);
  } catch (err) {
    document.getElementById("loading").style.display = "none";
    document.getElementById("error-section").style.display = "block";
    document.getElementById("error-message").textContent = err.message;
  }
}

function renderSummary(data) {
  const container = document.getElementById("cluster-summary");
  container.innerHTML = `
    <div class="summary-cards">
      <div class="summary-card">
        <div class="summary-number">${data.total_decks}</div>
        <div class="summary-label">Total Decks</div>
      </div>
      <div class="summary-card">
        <div class="summary-number">${data.num_clusters}</div>
        <div class="summary-label">Clusters Found</div>
      </div>
      <div class="summary-card">
        <div class="summary-number">${data.threshold}</div>
        <div class="summary-label">Threshold</div>
      </div>
      <div class="summary-card">
        <div class="summary-number">${data.metric === "distinct" ? "Distinct" : "Total"}</div>
        <div class="summary-label">Metric</div>
      </div>
    </div>
  `;
}

function renderClusterGroups(data) {
  const container = document.getElementById("cluster-groups");

  if (!data.clusters || data.clusters.length === 0) {
    container.innerHTML = '<p class="no-data">No clusters found.</p>';
    return;
  }

  const clusterColors = data.clusters.map((_, i) => getClusterColor(i));

  let html = "";
  data.clusters.forEach((cluster, idx) => {
    const color = clusterColors[idx];
    const elemBars = renderElementBars(cluster.elements);
    const coreCardsHtml = cluster.core_cards
      .slice(0, 20)
      .map((card) => {
        const elClass = getElementClass(card.elements);
        return `<span class="core-card ${elClass}" title="${card.type} - ${card.elements} (${Math.round(card.frequency * 100)}%)">${card.name}</span>`;
      })
      .join("");

    const deckListHtml = cluster.decks
      .map((deck) => {
        return `<div class="deck-item"><span class="deck-player">${deck.username}</span> - ${deck.name} <span class="deck-avatar">(${deck.avatar})</span></div>`;
      })
      .join("");

    html += `
      <div class="cluster-card">
        <div class="cluster-header" onclick="toggleCluster(${idx})" style="border-left: 4px solid ${color};">
          <div class="cluster-header-left">
            <span class="cluster-expand" id="expand-${idx}">+</span>
            <h3 class="cluster-name">${cluster.label}</h3>
            <span class="cluster-size">${cluster.size} deck${cluster.size !== 1 ? "s" : ""}</span>
          </div>
          <div class="cluster-header-right">
            <span class="cluster-similarity">Avg similarity: ${Math.round(cluster.avg_internal_similarity * 100)}%</span>
          </div>
        </div>
        <div class="cluster-body" id="cluster-body-${idx}" style="display: none;">
          <div class="cluster-section">
            <h4>Element Breakdown</h4>
            <div class="element-bars-mini">${elemBars}</div>
          </div>
          <div class="cluster-section">
            <h4>Core Cards <span class="core-note">(in &gt;50% of cluster decks)</span></h4>
            <div class="core-cards-grid">${coreCardsHtml || '<span class="no-data">No shared core cards</span>'}</div>
          </div>
          <div class="cluster-section">
            <h4>Decks</h4>
            <div class="deck-list">${deckListHtml}</div>
          </div>
        </div>
      </div>
    `;
  });

  container.innerHTML = html;
}

function toggleCluster(idx) {
  const body = document.getElementById(`cluster-body-${idx}`);
  const expand = document.getElementById(`expand-${idx}`);
  if (body.style.display === "none") {
    body.style.display = "block";
    expand.textContent = "\u2212";
  } else {
    body.style.display = "none";
    expand.textContent = "+";
  }
}

// Make toggleCluster available globally
window.toggleCluster = toggleCluster;

function renderElementBars(elements) {
  const total = Object.values(elements).reduce((s, v) => s + v, 0) || 1;
  const order = ["Fire", "Water", "Earth", "Air"];
  return order
    .map((el) => {
      const count = elements[el] || 0;
      const pct = Math.round((count / total) * 100);
      return `<div class="elem-bar-row">
        <span class="elem-name element-${el.toLowerCase()}">${el}</span>
        <div class="elem-bar-track"><div class="elem-bar-fill element-bg-${el.toLowerCase()}" style="width: ${pct}%;"></div></div>
        <span class="elem-pct">${pct}%</span>
      </div>`;
    })
    .join("");
}

/* ─── Heatmap ─── */

function renderHeatmap(data) {
  const canvas = document.getElementById("heatmap-canvas");
  const ctx = canvas.getContext("2d");
  const tooltip = document.getElementById("heatmap-tooltip");
  const matrix = data.distance_matrix;
  const labels = data.deck_labels;
  const n = matrix.length;

  if (n === 0) return;

  // Reorder by cluster
  const order = [];
  data.clusters.forEach((cluster) => {
    cluster.decks.forEach((deck) => {
      const label = `${deck.username} - ${deck.avatar}`;
      const idx = labels.indexOf(label);
      if (idx !== -1 && !order.includes(idx)) order.push(idx);
    });
  });
  // Add any missing indices
  for (let i = 0; i < n; i++) {
    if (!order.includes(i)) order.push(i);
  }

  const cellSize = Math.max(3, Math.min(12, Math.floor(600 / n)));
  const size = cellSize * n;
  canvas.width = size;
  canvas.height = size;
  canvas.style.width = size + "px";
  canvas.style.height = size + "px";

  // Draw cells
  for (let row = 0; row < n; row++) {
    for (let col = 0; col < n; col++) {
      const dist = matrix[order[row]][order[col]];
      const sim = 1 - dist;
      ctx.fillStyle = similarityColor(sim);
      ctx.fillRect(col * cellSize, row * cellSize, cellSize, cellSize);
    }
  }

  // Draw cluster boundary lines
  let offset = 0;
  ctx.strokeStyle = "rgba(255, 255, 255, 0.5)";
  ctx.lineWidth = 1;
  data.clusters.forEach((cluster) => {
    offset += cluster.size;
    const pos = offset * cellSize;
    ctx.beginPath();
    ctx.moveTo(pos, 0);
    ctx.lineTo(pos, size);
    ctx.stroke();
    ctx.beginPath();
    ctx.moveTo(0, pos);
    ctx.lineTo(size, pos);
    ctx.stroke();
  });

  // Tooltip on hover
  canvas.addEventListener("mousemove", (e) => {
    const rect = canvas.getBoundingClientRect();
    const x = e.clientX - rect.left;
    const y = e.clientY - rect.top;
    const col = Math.floor(x / cellSize);
    const row = Math.floor(y / cellSize);

    if (row >= 0 && row < n && col >= 0 && col < n) {
      const dist = matrix[order[row]][order[col]];
      const sim = ((1 - dist) * 100).toFixed(1);
      tooltip.innerHTML = `<strong>${labels[order[row]]}</strong><br>vs<br><strong>${labels[order[col]]}</strong><br>Similarity: ${sim}%`;
      tooltip.style.display = "block";
      tooltip.style.left = e.clientX - canvas.parentElement.getBoundingClientRect().left + 15 + "px";
      tooltip.style.top = e.clientY - canvas.parentElement.getBoundingClientRect().top + 15 + "px";
    } else {
      tooltip.style.display = "none";
    }
  });

  canvas.addEventListener("mouseleave", () => {
    tooltip.style.display = "none";
  });
}

function similarityColor(sim) {
  // 0 (different) = red, 1 (identical) = green
  const r = Math.round(220 - sim * 180);
  const g = Math.round(60 + sim * 160);
  const b = Math.round(60);
  return `rgb(${r}, ${g}, ${b})`;
}

function getClusterColor(index) {
  const colors = [
    "#a855f7", "#3b82f6", "#10b981", "#f59e0b",
    "#ef4444", "#ec4899", "#06b6d4", "#84cc16",
    "#f97316", "#6366f1", "#14b8a6", "#e11d48",
  ];
  return colors[index % colors.length];
}

function getElementClass(elements) {
  if (!elements || elements === "None") return "";
  const first = elements.split(",")[0].trim().toLowerCase();
  if (["fire", "water", "earth", "air"].includes(first)) return `element-${first}`;
  return "";
}
