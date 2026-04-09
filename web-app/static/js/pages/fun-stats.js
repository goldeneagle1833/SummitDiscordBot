(function () {
  "use strict";

  const eventSelect = document.getElementById("event-filter");
  const sourceSelect = document.getElementById("source-filter");
  const statsGrid = document.getElementById("stats-grid");

  // ── Filters ──────────────────────────────────────────────────────

  async function fetchFilters() {
    try {
      const res = await fetch("/api/fun-stats/filters");
      if (!res.ok) return;
      const data = await res.json();

      // Populate event dropdown
      if (data.events) {
        data.events.forEach((ev) => {
          const opt = document.createElement("option");
          opt.value = ev.event_id;
          opt.textContent = ev.event_name + (ev.is_active ? " (Active)" : "");
          eventSelect.appendChild(opt);
        });
      }
      // Add "All Time" option
      const allOpt = document.createElement("option");
      allOpt.value = "all";
      allOpt.textContent = "All Time";
      eventSelect.appendChild(allOpt);

      // Populate source dropdown
      if (data.sources) {
        data.sources.forEach((src) => {
          const opt = document.createElement("option");
          opt.value = src;
          opt.textContent = src;
          sourceSelect.appendChild(opt);
        });
      }
    } catch (err) {
      console.error("Failed to fetch filters:", err);
    }
  }

  function buildFilterParams() {
    const params = new URLSearchParams();
    if (eventSelect.value) params.set("event", eventSelect.value);
    if (sourceSelect.value) params.set("source", sourceSelect.value);
    return params.toString();
  }

  // ── Data fetch ───────────────────────────────────────────────────

  async function fetchStats() {
    showLoading();
    try {
      const qs = buildFilterParams();
      const url = "/api/fun-stats" + (qs ? "?" + qs : "");
      const res = await fetch(url);
      if (!res.ok) throw new Error("API returned " + res.status);
      const data = await res.json();
      if (!data.success) throw new Error(data.error || "Unknown error");
      renderStats(data.stats);
    } catch (err) {
      console.error("Failed to fetch stats:", err);
      showError(err.message);
    }
  }

  // ── Rendering ────────────────────────────────────────────────────

  function showLoading() {
    statsGrid.innerHTML =
      '<div class="stats-loading"><div class="spinner"></div><p>Loading stats...</p></div>';
  }

  function showError(msg) {
    statsGrid.innerHTML =
      '<div class="stats-error"><p>Failed to load stats: ' +
      escapeHtml(msg) +
      "</p></div>";
  }

  function escapeHtml(str) {
    const div = document.createElement("div");
    div.textContent = str;
    return div.innerHTML;
  }

  function renderStats(stats) {
    statsGrid.innerHTML = "";
    if (!stats) {
      showError("No data returned");
      return;
    }

    renderWinStreaks(stats.win_streaks);
    renderMostDiverse(stats.most_diverse);
    renderMostActive(stats.most_active);
    renderBiggestUpsets(stats.biggest_upsets);
    renderNemesisPairs(stats.nemesis_pairs);
    renderMatchDuration(stats.match_duration);
    renderMostImproved(stats.most_improved);
    renderIronmanStreak(stats.ironman_streak);

    // If nothing rendered, show empty message
    if (statsGrid.children.length === 0) {
      statsGrid.innerHTML =
        '<div class="stats-loading"><p>No stats available for this filter.</p></div>';
    }
  }

  // ── Win Streaks ──────────────────────────────────────────────────

  function renderWinStreaks(data) {
    if (!data || (!data.best && !data.active)) return;
    if ((!data.best || data.best.length === 0) && (!data.active || data.active.length === 0)) return;

    const bestRows = (data.best || [])
      .map(
        (p, i) =>
          `<tr>
        <td class="rank">${i + 1}</td>
        <td class="name">${escapeHtml(p.name)}</td>
        <td class="number">${p.best_streak}</td>
        <td class="number">${p.current_streak > 0 ? p.current_streak + " \ud83d\udd25" : "-"}</td>
      </tr>`
      )
      .join("");

    const activeRows =
      data.active && data.active.length > 0
        ? data.active
            .map(
              (p, i) =>
                `<tr>
          <td class="rank">${i + 1}</td>
          <td class="name">${escapeHtml(p.name)}</td>
          <td class="number">${p.current_streak} \ud83d\udd25</td>
        </tr>`
            )
            .join("")
        : '<tr><td colspan="3" style="text-align:center;color:rgba(255,255,255,0.5);padding:1rem">No active win streaks</td></tr>';

    const bestTable = `<div class="stat-table-wrap"><table class="stat-table">
        <thead><tr><th></th><th>Player</th><th>Best</th><th>Current</th></tr></thead>
        <tbody>${bestRows}</tbody>
      </table></div>`;

    const activeTable = `<div class="stat-table-wrap"><table class="stat-table">
        <thead><tr><th></th><th>Player</th><th>Streak</th></tr></thead>
        <tbody>${activeRows}</tbody>
      </table></div>`;

    const card = document.createElement("div");
    card.className = "stat-card";
    card.innerHTML =
      `<h3>\ud83c\udfc6 Win Streaks</h3>` +
      `<div class="streak-toggle">` +
      `<button class="toggle-btn active" data-view="best">Best All-Time</button>` +
      `<button class="toggle-btn" data-view="active">Active Streaks</button>` +
      `</div>` +
      `<div class="streak-view" data-view="best">${bestTable}</div>` +
      `<div class="streak-view" data-view="active" style="display:none">${activeTable}</div>`;

    card.querySelectorAll(".toggle-btn").forEach((btn) => {
      btn.addEventListener("click", () => {
        card.querySelectorAll(".toggle-btn").forEach((b) => b.classList.remove("active"));
        btn.classList.add("active");
        const view = btn.dataset.view;
        card.querySelectorAll(".streak-view").forEach((v) => {
          v.style.display = v.dataset.view === view ? "" : "none";
        });
      });
    });

    statsGrid.appendChild(card);
  }

  // ── Most Diverse ─────────────────────────────────────────────────

  function renderMostDiverse(data) {
    if (!data || data.length === 0) return;
    const rows = data
      .map(
        (p, i) =>
          `<tr>
        <td class="rank">${i + 1}</td>
        <td class="name">${escapeHtml(p.name)}</td>
        <td class="number">${p.unique_avatars}</td>
        <td class="avatar-list">${(p.avatars || []).map(escapeHtml).join(", ")}</td>
      </tr>`
      )
      .join("");
    appendCard(
      "\ud83c\udfad Most Diverse",
      `<div class="stat-table-wrap"><table class="stat-table">
        <thead><tr><th></th><th>Player</th><th>#</th><th>Avatars</th></tr></thead>
        <tbody>${rows}</tbody>
      </table></div>`
    );
  }

  // ── Most Active ──────────────────────────────────────────────────

  function renderMostActive(data) {
    if (!data || data.length === 0) return;
    const rows = data
      .map(
        (p, i) =>
          `<tr>
        <td class="rank">${i + 1}</td>
        <td class="name">${escapeHtml(p.name)}</td>
        <td class="number">${p.games}</td>
        <td class="number">${p.wins}-${p.losses}</td>
      </tr>`
      )
      .join("");
    appendCard(
      "\u26a1 Most Active",
      `<div class="stat-table-wrap"><table class="stat-table">
        <thead><tr><th></th><th>Player</th><th>Games</th><th>W-L</th></tr></thead>
        <tbody>${rows}</tbody>
      </table></div>`
    );
  }

  // ── Biggest Upsets ───────────────────────────────────────────────

  function renderBiggestUpsets(data) {
    if (!data || data.length === 0) return;
    const rows = data
      .map(
        (m, i) =>
          `<tr>
        <td class="rank">${i + 1}</td>
        <td class="name">${escapeHtml(m.winner_name)}</td>
        <td class="number text-positive">+${m.elo_change}</td>
      </tr>`
      )
      .join("");
    appendCard(
      "\ud83d\udca5 Biggest Upsets",
      `<div class="stat-table-wrap"><table class="stat-table">
        <thead><tr><th></th><th>Player</th><th>ELO Gained</th></tr></thead>
        <tbody>${rows}</tbody>
      </table></div>`
    );
  }

  // ── Nemesis Pairs ────────────────────────────────────────────────

  function renderNemesisPairs(data) {
    if (!data || data.length === 0) return;
    const rows = data
      .map(
        (p, i) =>
          `<tr>
        <td class="rank">${i + 1}</td>
        <td class="name">${escapeHtml(p.player1_name)}</td>
        <td style="color:rgba(255,255,255,0.4)">vs</td>
        <td class="name">${escapeHtml(p.player2_name)}</td>
        <td class="number">${p.encounters}</td>
        <td class="number">${p.p1_wins}-${p.p2_wins}</td>
      </tr>`
      )
      .join("");
    appendCard(
      "\u2694\ufe0f Nemesis Pairs",
      `<div class="stat-table-wrap"><table class="stat-table">
        <thead><tr><th></th><th>Player</th><th></th><th>Player</th><th>Games</th><th>H2H</th></tr></thead>
        <tbody>${rows}</tbody>
      </table></div>`
    );
  }

  // ── Match Duration ───────────────────────────────────────────────

  function renderMatchDuration(data) {
    if (!data) return;
    appendCard(
      "\u23f1\ufe0f Match Duration",
      `<div class="stat-highlight">
        <div class="big-number">${data.average_minutes} min</div>
        <div class="big-label">Average match time</div>
        <div class="sub-stats">
          <div class="sub-stat">
            <div class="value">${data.fastest_minutes} min</div>
            <div class="label">Fastest</div>
          </div>
          <div class="sub-stat">
            <div class="value">${data.longest_minutes} min</div>
            <div class="label">Longest</div>
          </div>
          <div class="sub-stat">
            <div class="value">${data.total_with_data}</div>
            <div class="label">Matches</div>
          </div>
        </div>
      </div>`
    );
  }

  // ── Most Improved ────────────────────────────────────────────────

  function renderMostImproved(data) {
    if (!data || data.length === 0) return;
    const rows = data
      .map(
        (p, i) =>
          `<tr>
        <td class="rank">${i + 1}</td>
        <td class="name">${escapeHtml(p.name)}</td>
        <td class="number text-positive">+${p.elo_change}</td>
      </tr>`
      )
      .join("");
    appendCard(
      "\ud83d\udcc8 Most Improved <span style='font-size:0.7rem;color:rgba(255,255,255,0.4);font-weight:400'>Last 7 Days</span>",
      `<div class="stat-table-wrap"><table class="stat-table">
        <thead><tr><th></th><th>Player</th><th>ELO</th></tr></thead>
        <tbody>${rows}</tbody>
      </table></div>`
    );
  }

  // ── Ironman Streak ───────────────────────────────────────────────

  function renderIronmanStreak(data) {
    if (!data || data.length === 0) return;
    const rows = data
      .map(
        (p, i) =>
          `<tr>
        <td class="rank">${i + 1}</td>
        <td class="name">${escapeHtml(p.name)}</td>
        <td class="number">${p.consecutive_days} days</td>
      </tr>`
      )
      .join("");
    appendCard(
      "\ud83d\udcaa Ironman Streak",
      `<div class="stat-table-wrap"><table class="stat-table">
        <thead><tr><th></th><th>Player</th><th>Streak</th></tr></thead>
        <tbody>${rows}</tbody>
      </table></div>`
    );
  }

  // ── Helpers ──────────────────────────────────────────────────────

  function appendCard(title, bodyHtml) {
    const card = document.createElement("div");
    card.className = "stat-card";
    card.innerHTML = "<h3>" + title + "</h3>" + bodyHtml;
    statsGrid.appendChild(card);
  }

  // ── Init ─────────────────────────────────────────────────────────

  eventSelect.addEventListener("change", fetchStats);
  sourceSelect.addEventListener("change", fetchStats);

  fetchFilters().then(fetchStats);
})();
