// Sorcery Deck Rec — client-side fetch and render logic
// Handles both the list page (/deck-rec) and the detail page (/deck-rec/<id>)

(function () {
  "use strict";

  // ------------------------------------------------------------------ //
  // Avatar image helpers (shared by both pages)                        //
  // ------------------------------------------------------------------ //

  const _avatarImages = typeof AVATAR_IMAGE_FILES !== "undefined" ? AVATAR_IMAGE_FILES : [];

  function _normalize(str) {
    return str.toLowerCase().replace(/[^a-z0-9]/g, "");
  }

  function getAvatarImagePath(avatarName) {
    if (!avatarName || _avatarImages.length === 0) return null;
    const norm = _normalize(avatarName);
    for (const img of _avatarImages) {
      if (_normalize(img.replace(/\.(png|jpg|jpeg)$/i, "")) === norm) return img;
    }
    for (const img of _avatarImages) {
      if (_normalize(img.replace(/\.(png|jpg|jpeg)$/i, "")).includes(norm)) return img;
    }
    for (const img of _avatarImages) {
      if (norm.includes(_normalize(img.replace(/\.(png|jpg|jpeg)$/i, "")))) return img;
    }
    return null;
  }

  // ------------------------------------------------------------------ //
  // List page: /deck-rec                                                //
  // ------------------------------------------------------------------ //

  // Element icon map (same files used in player match history)
  const ELEMENT_ICONS = {
    Fire:  "fire.png",
    Water: "water.png",
    Earth: "earth.png",
    Air:   "wind.png",
  };

  function renderElementIcons(elements) {
    if (!elements || elements.length === 0) return "";
    return elements
      .filter((el) => ELEMENT_ICONS[el])
      .map((el) => `<img src="/avatar-images/${ELEMENT_ICONS[el]}" alt="${escHtml(el)}" title="${escHtml(el)}" width="18" height="18">`)
      .join("");
  }

  // All decks cached after first fetch, used for client-side filtering
  let _allDecks = [];
  let _activeAvatar = "all";
  let _activeElements = new Set(); // empty = show all
  let _activeYear = "";

  async function fetchDeckList() {
    const grid = document.getElementById("deck-grid");
    const loading = document.getElementById("loading");
    const errorState = document.getElementById("error-state");

    if (!grid) return; // Not on the list page

    try {
      const res = await fetch("/api/deck-rec/decks");
      const data = await res.json();

      if (loading) loading.style.display = "none";

      if (!res.ok || !data.decks || data.decks.length === 0) {
        if (errorState) errorState.style.display = "block";
        return;
      }

      _allDecks = data.decks;
      buildAvatarFilter(_allDecks);
      buildYearFilter(_allDecks);
      initElementFilter();
      applyFilters();
      grid.style.display = "grid";
    } catch (err) {
      console.error("Failed to load deck list:", err);
      if (loading) loading.style.display = "none";
      if (errorState) errorState.style.display = "block";
    }
  }

  function buildAvatarFilter(decks) {
    const bar = document.getElementById("filter-bar");
    const input = document.getElementById("avatar-search");
    const clearBtn = document.getElementById("avatar-search-clear");
    const dropdown = document.getElementById("avatar-dropdown");
    const activeTag = document.getElementById("avatar-active-tag");
    if (!bar || !input || !dropdown) return;

    const avatars = [...new Set(decks.map((d) => d.avatar_name).filter(Boolean))].sort();
    if (avatars.length === 0) return;

    let highlightIndex = -1;

    function getMatches(query) {
      if (!query) return avatars;
      const q = query.toLowerCase();
      return avatars.filter((a) => a.toLowerCase().includes(q));
    }

    function renderDropdown(matches) {
      dropdown.innerHTML = "";
      highlightIndex = -1;
      if (matches.length === 0) {
        dropdown.style.display = "none";
        return;
      }
      matches.forEach((avatar, i) => {
        const item = document.createElement("div");
        item.className = "avatar-dropdown-item";
        item.textContent = avatar;
        item.addEventListener("mousedown", (e) => {
          e.preventDefault(); // keep focus on input
          selectAvatar(avatar);
        });
        dropdown.appendChild(item);
      });
      dropdown.style.display = "block";
    }

    function closeDropdown() {
      dropdown.style.display = "none";
      highlightIndex = -1;
    }

    function setHighlight(idx) {
      const items = dropdown.querySelectorAll(".avatar-dropdown-item");
      items.forEach((el) => el.classList.remove("highlighted"));
      if (idx >= 0 && idx < items.length) {
        items[idx].classList.add("highlighted");
        items[idx].scrollIntoView({ block: "nearest" });
      }
      highlightIndex = idx;
    }

    function selectAvatar(avatar) {
      _activeAvatar = avatar;
      input.value = "";
      clearBtn.style.display = "none";
      closeDropdown();

      // Show active tag
      activeTag.innerHTML = `
        <span class="avatar-active-tag">
          ${escHtml(avatar)}
          <button aria-label="Clear filter">✕</button>
        </span>`;
      activeTag.querySelector("button").addEventListener("click", clearFilter);

      applyFilters();
    }

    function clearFilter() {
      _activeAvatar = "all";
      input.value = "";
      clearBtn.style.display = "none";
      activeTag.innerHTML = "";
      closeDropdown();
      applyFilters();
    }

    input.addEventListener("input", () => {
      const val = input.value;
      clearBtn.style.display = val ? "block" : "none";
      renderDropdown(getMatches(val));
    });

    input.addEventListener("focus", () => {
      renderDropdown(getMatches(input.value));
    });

    input.addEventListener("blur", () => {
      // Small delay so mousedown on item fires first
      setTimeout(closeDropdown, 150);
    });

    input.addEventListener("keydown", (e) => {
      const items = dropdown.querySelectorAll(".avatar-dropdown-item");
      if (e.key === "ArrowDown") {
        e.preventDefault();
        setHighlight(Math.min(highlightIndex + 1, items.length - 1));
      } else if (e.key === "ArrowUp") {
        e.preventDefault();
        setHighlight(Math.max(highlightIndex - 1, 0));
      } else if (e.key === "Enter") {
        if (highlightIndex >= 0 && items[highlightIndex]) {
          selectAvatar(items[highlightIndex].textContent);
        }
      } else if (e.key === "Escape") {
        closeDropdown();
        input.blur();
      }
    });

    clearBtn.addEventListener("click", () => {
      input.value = "";
      clearBtn.style.display = "none";
      renderDropdown(avatars);
      input.focus();
    });

    bar.style.display = "flex";
  }

  function buildYearFilter(decks) {
    const group = document.getElementById("year-filter-group");
    const sel = document.getElementById("year-select");
    if (!group || !sel) return;

    const years = [...new Set(decks.map((d) => d.event_year).filter(Boolean))].sort((a, b) => b - a);
    if (years.length === 0) return;

    years.forEach((yr) => {
      const opt = document.createElement("option");
      opt.value = yr;
      opt.textContent = yr;
      sel.appendChild(opt);
    });

    sel.addEventListener("change", () => {
      _activeYear = sel.value;
      applyFilters();
    });

    group.style.display = "flex";
  }

  function initElementFilter() {
    document.querySelectorAll(".el-btn").forEach((btn) => {
      btn.addEventListener("click", () => {
        const el = btn.dataset.element;
        if (_activeElements.has(el)) {
          _activeElements.delete(el);
          btn.classList.remove("active");
        } else {
          _activeElements.add(el);
          btn.classList.add("active");
        }
        applyFilters();
      });
    });
  }

  function applyFilters() {
    const grid = document.getElementById("deck-grid");
    if (!grid) return;

    let filtered = _allDecks;

    if (_activeAvatar !== "all") {
      filtered = filtered.filter((d) => d.avatar_name === _activeAvatar);
    }

    if (_activeElements.size > 0) {
      filtered = filtered.filter((d) =>
        d.elements && [..._activeElements].every((el) => d.elements.includes(el))
      );
    }

    if (_activeYear) {
      filtered = filtered.filter((d) => String(d.event_year) === String(_activeYear));
    }

    renderDeckGrid(filtered, grid);
  }

  function renderDeckGrid(decks, container) {
    container.innerHTML = "";

    if (decks.length === 0) {
      container.innerHTML = `<p style="color:rgba(255,255,255,0.4);padding:2rem 0;grid-column:1/-1;text-align:center;">No decks found for this avatar.</p>`;
      return;
    }

    decks.forEach((deck) => {
      const a = document.createElement("a");
      a.href = `/deck-rec/${encodeURIComponent(deck.deck_id)}`;
      a.className = "deck-card";

      const clusterLabel =
        deck.cluster_size === 1
          ? "1 similar build"
          : `${deck.cluster_size} similar builds`;

      const avatarImg = getAvatarImagePath(deck.avatar_name);
      const avatarImgHtml = avatarImg
        ? `<img class="deck-card-avatar-img" src="/avatar-images/${escHtml(avatarImg)}" alt="${escHtml(deck.avatar_name)}" loading="lazy">`
        : "";

      const elementIconsHtml = renderElementIcons(deck.elements);

      a.innerHTML = `
        <div class="deck-card-header">
          ${avatarImgHtml}
          <div class="deck-card-name" title="${escHtml(deck.deck_name)}">${escHtml(deck.deck_name)}</div>
        </div>
        <div class="deck-card-meta">${escHtml(deck.avatar_name)}</div>
        <div class="deck-card-meta">${escHtml(deck.event_name)}</div>
        ${elementIconsHtml ? `<div class="deck-card-elements">${elementIconsHtml}</div>` : ""}
        <div class="deck-card-cluster">Community: <span>${escHtml(clusterLabel)}</span></div>
      `;
      container.appendChild(a);
    });
  }

  // ------------------------------------------------------------------ //
  // Detail page: /deck-rec/<deck_id>                                   //
  // ------------------------------------------------------------------ //

  async function fetchRecommendations() {
    const coreSection = document.getElementById("core-cards");
    if (!coreSection) return; // Not on the detail page

    const loading = document.getElementById("loading");
    const errorState = document.getElementById("error-state");

    // Extract deck_id from the current URL path
    const pathParts = window.location.pathname.split("/").filter(Boolean);
    const deckId = pathParts[pathParts.length - 1];
    if (!deckId) return;

    try {
      const res = await fetch(`/api/deck-rec/${encodeURIComponent(deckId)}/recommendations`);
      const data = await res.json();

      if (loading) loading.style.display = "none";

      if (!res.ok) {
        if (res.status === 404) {
          showNotFound(errorState);
        } else {
          showError(errorState, "Failed to load recommendations.");
        }
        return;
      }

      renderArchetype(data);
    } catch (err) {
      console.error("Failed to load recommendations:", err);
      if (loading) loading.style.display = "none";
      showError(errorState, "Failed to load recommendations.");
    }
  }

  function renderArchetype(data) {
    const contentWrapper = document.getElementById("archetype-content");
    if (contentWrapper) contentWrapper.style.display = "block";

    // Seed deck header
    const seedName = document.getElementById("seed-name");
    const seedAvatar = document.getElementById("seed-avatar");
    const seedEvent = document.getElementById("seed-event");
    const seedPlayer = document.getElementById("seed-player");
    const seedLink = document.getElementById("seed-link");

    if (seedName) seedName.textContent = data.seed.deck_name || "Unnamed Deck";
    if (seedAvatar) {
      const imgPath = getAvatarImagePath(data.seed.avatar_name);
      seedAvatar.innerHTML = imgPath
        ? `<img class="seed-avatar-img" src="/avatar-images/${escHtml(imgPath)}" alt="${escHtml(data.seed.avatar_name)}" loading="lazy"> ${escHtml(data.seed.avatar_name)}`
        : escHtml(data.seed.avatar_name);
    }
    if (seedEvent) seedEvent.textContent = data.seed.event_name;
    if (seedPlayer) seedPlayer.textContent = data.seed.player_name;
    if (seedLink) {
      seedLink.href = data.seed.curiosa_url;
      seedLink.style.display = data.seed.curiosa_url ? "inline" : "none";
    }

    // Cluster stats
    const clusterSize = document.getElementById("cluster-size");
    const avgSim = document.getElementById("avg-similarity");
    if (clusterSize) clusterSize.textContent = data.cluster_size;
    if (avgSim) avgSim.textContent = `${Math.round(data.avg_similarity * 100)}%`;

    // Empty cluster message
    if (data.cluster_size === 0) {
      const emptyMsg = document.getElementById("empty-cluster-msg");
      if (emptyMsg) emptyMsg.style.display = "block";
      hideTierSections();
      initFringeToggle(data); // still init (will hide button)
      return;
    }

    // Render tiers
    renderTier("core-cards", data.core_cards);
    renderTier("common-cards", data.common_cards);
    renderTier("tech-cards", data.tech_cards);

    initFringeToggle(data);
  }

  function renderTier(sectionId, cards) {
    // sectionId points to the <ul> element directly
    const list = document.getElementById(sectionId);
    if (!list) return;

    const wrapper = list.closest(".tier-section");

    if (!cards || cards.length === 0) {
      if (wrapper) wrapper.style.display = "none";
      return;
    }

    list.innerHTML = "";
    cards.forEach((card) => {
      const li = document.createElement("li");
      li.className = "card-row";
      if (card.image) li.dataset.cardImage = card.image;
      li.innerHTML = `
        <span class="card-row-name">${escHtml(card.card_name)}</span>
        <span class="card-row-pct">${escHtml(card.inclusion_pct)}</span>
      `;
      if (card.image) {
        li.addEventListener("mouseenter", (e) => showCardPopup(card.image, e.currentTarget));
        li.addEventListener("mouseleave", hideCardPopup);
        li.addEventListener("click", (e) => toggleCardPopupPin(card.image, e.currentTarget));
      }
      list.appendChild(li);
    });

    if (wrapper) wrapper.style.display = "block";
  }

  function hideTierSections() {
    ["core-cards-wrapper", "common-cards-wrapper", "tech-cards-wrapper", "fringe-cards-wrapper"].forEach((id) => {
      const el = document.getElementById(id);
      if (el) el.style.display = "none";
    });
  }

  // ------------------------------------------------------------------ //
  // Fringe cards toggle (US3)                                           //
  // ------------------------------------------------------------------ //

  function initFringeToggle(data) {
    const btn = document.getElementById("fringe-toggle-btn");
    const fringeSection = document.getElementById("fringe-cards");

    if (!btn || !fringeSection) return;

    // Hide toggle entirely if no fringe cards
    if (!data.fringe_cards || data.fringe_cards.length === 0) {
      const wrapper = btn.closest(".fringe-toggle-wrapper") || btn.parentElement;
      if (wrapper) wrapper.style.display = "none";
      return;
    }

    let rendered = false;
    let visible = false;

    btn.addEventListener("click", () => {
      visible = !visible;

      if (!rendered) {
        renderTier("fringe-cards", data.fringe_cards);
        rendered = true;
      }

      const tierWrapper = document.getElementById("fringe-cards-wrapper");
      if (tierWrapper) tierWrapper.style.display = visible ? "block" : "none";

      btn.textContent = visible ? "Hide Fringe Cards" : "Show Fringe Cards";
    });
  }

  // ------------------------------------------------------------------ //
  // Card image popup                                                   //
  // ------------------------------------------------------------------ //

  let _popup = null;
  let _pinnedRow = null;

  function _getOrCreatePopup() {
    if (!_popup) {
      _popup = document.createElement("div");
      _popup.id = "card-img-popup";
      _popup.innerHTML = `<img alt="Card image">`;
      document.body.appendChild(_popup);
      document.addEventListener("click", (e) => {
        if (_pinnedRow && !_pinnedRow.contains(e.target)) {
          hideCardPopup();
          _pinnedRow = null;
        }
      });
    }
    return _popup;
  }

  function showCardPopup(imageFile, anchorEl) {
    if (_pinnedRow) return; // don't override a pinned popup
    const popup = _getOrCreatePopup();
    popup.querySelector("img").src = `/card-images/${imageFile}`;
    _positionPopup(popup, anchorEl);
    popup.classList.add("visible");
  }

  function hideCardPopup() {
    if (_pinnedRow) return;
    if (_popup) _popup.classList.remove("visible");
  }

  function toggleCardPopupPin(imageFile, anchorEl) {
    const popup = _getOrCreatePopup();
    if (_pinnedRow === anchorEl) {
      // Unpin
      _pinnedRow = null;
      popup.classList.remove("visible", "pinned");
      return;
    }
    _pinnedRow = anchorEl;
    popup.querySelector("img").src = `/card-images/${imageFile}`;
    _positionPopup(popup, anchorEl);
    popup.classList.add("visible", "pinned");
  }

  function _positionPopup(popup, anchorEl) {
    const rect = anchorEl.getBoundingClientRect();
    const popupW = 220;
    const spaceRight = window.innerWidth - rect.right;
    const left = spaceRight >= popupW + 12
      ? rect.right + 8 + window.scrollX
      : rect.left - popupW - 8 + window.scrollX;
    popup.style.left = `${left}px`;
    popup.style.top = `${rect.top + window.scrollY}px`;
  }

  // ------------------------------------------------------------------ //
  // Helpers                                                             //
  // ------------------------------------------------------------------ //

  function showNotFound(el) {
    if (!el) return;
    el.innerHTML = `
      Archetype not found. <a href="/deck-rec" style="color:inherit;text-decoration:underline;">Back to Deck Rec</a>
    `;
    el.style.display = "block";
  }

  function showError(el, msg) {
    if (!el) return;
    el.textContent = msg;
    el.style.display = "block";
  }

  function escHtml(str) {
    if (!str && str !== 0) return "";
    return String(str)
      .replace(/&/g, "&amp;")
      .replace(/</g, "&lt;")
      .replace(/>/g, "&gt;")
      .replace(/"/g, "&quot;");
  }

  // ------------------------------------------------------------------ //
  // Entry point                                                         //
  // ------------------------------------------------------------------ //

  document.addEventListener("DOMContentLoaded", () => {
    fetchDeckList();
    fetchRecommendations();
  });
})();
