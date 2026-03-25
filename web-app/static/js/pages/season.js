/**
 * Page: Season Leaderboard
 * Template: templates/pages/season.html
 * Description: Fetches and renders season members as a ranked leaderboard
 */

async function fetchSeasonLeaderboard() {
  try {
    const res = await fetch(`/api/seasons/${SEASON_ID}/members`);
    const data = await res.json();

    if (!data.success) {
      document.getElementById("season-subtitle").textContent =
        data.error || "Season not found";
      return;
    }

    // Populate season header
    document.getElementById("season-title").textContent = data.title;
    document.getElementById("season-subtitle").textContent = "Season Leaderboard";

    // Populate season info
    const infoSection = document.getElementById("season-info");
    infoSection.style.display = "";

    document.getElementById("season-dates").textContent =
      "\u{1F4C5} " + data.start_date + " \u2014 " + data.end_date;

    if (data.region) {
      const region = document.getElementById("season-region");
      region.textContent = "\u{1F4CD} " + data.region;
      region.style.display = "";
    }

    document.getElementById("season-creator").textContent =
      "Created by " + data.creator_display_name;

    if (data.description) {
      const desc = document.getElementById("season-description");
      desc.textContent = data.description;
      desc.style.display = "";
    }

    // Render leaderboard
    const members = data.members || [];
    const tbody = document.getElementById("leaderboard-tbody");
    const emptyMsg = document.getElementById("leaderboard-empty");
    tbody.innerHTML = "";

    if (members.length === 0) {
      emptyMsg.style.display = "";
      return;
    }

    members.forEach(function (member) {
      var rank = member.rank;
      var rankDisplay = '<span class="rank-display">' + rank + "</span>";

      if (rank <= 3) {
        rankDisplay =
          '<span class="rank-badge rank-' + rank + '">' + rank + "</span>";
      }

      var creatorBadge = member.is_creator
        ? ' <span class="creator-badge">Owner</span>'
        : "";

      var row = document.createElement("tr");
      row.innerHTML =
        "<td>" + rankDisplay + "</td>" +
        '<td><a href="/player/' + member.user_id + '" class="player-link">' +
          member.display_name + "</a>" + creatorBadge + "</td>" +
        '<td class="col-align-right"><span class="win-loss">' +
          member.wins + "W / " + member.losses + "L</span></td>" +
        '<td class="col-align-right"><span class="lifetime-elo">' +
          member.season_elo + "</span></td>";
      tbody.appendChild(row);
    });
  } catch (error) {
    console.error("Error fetching season leaderboard:", error);
    document.getElementById("season-subtitle").textContent =
      "Error loading season data";
  }
}

document.addEventListener("DOMContentLoaded", function () {
  fetchSeasonLeaderboard();
});
