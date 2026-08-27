import { useState, useEffect, useMemo } from "react";
import { getPlayedWinrates, getPlayedWinrateFilters, getPlayedWinrateSeasonStats } from "@/api/cards";
import Spinner from "@/components/ui/Spinner";
import usePageTitle from "@/hooks/usePageTitle";

const SORT_OPTIONS = [
  { value: "played-score", label: "Played Score" },
  { value: "winrate", label: "Win Rate" },
  { value: "alphabetical", label: "Alphabetical" },
  { value: "most-played", label: "Most Played" },
  { value: "most-wins", label: "Wins" },
];

const SORT_LABELS = {
  "played-score": "played score",
  winrate: "win rate",
  alphabetical: "name (A\u2013Z)",
  "most-played": "most games played",
  "most-wins": "wins",
};

const MIN_GAMES_OPTIONS = [1, 3, 5, 10, 20];

function getWinRateColor(winRate) {
  const pct = Math.max(0, Math.min(100, winRate));
  if (pct <= 50) {
    const ratio = pct / 50;
    return `rgb(${Math.round(231 + 24 * ratio)}, ${Math.round(76 + 179 * ratio)}, ${Math.round(60 + 195 * ratio)})`;
  }
  const ratio = (pct - 50) / 50;
  return `rgb(${Math.round(255 - 209 * ratio)}, ${Math.round(255 - 51 * ratio)}, ${Math.round(255 - 142 * ratio)})`;
}

function sortCards(data, key) {
  const d = [...data];
  switch (key) {
    case "winrate":
      return d.sort((a, b) => b.win_rate - a.win_rate || b.total - a.total);
    case "alphabetical":
      return d.sort((a, b) => a.name.localeCompare(b.name));
    case "most-played":
      return d.sort((a, b) => b.total - a.total || b.win_rate - a.win_rate);
    case "most-wins":
      return d.sort((a, b) => b.wins - a.wins || b.win_rate - a.win_rate);
    case "played-score":
    default:
      return d.sort((a, b) => (b.played_score ?? 0) - (a.played_score ?? 0) || b.wins - a.wins);
  }
}

export default function CardPlayedWinrates() {
  usePageTitle("Card Played Win Rates");
  const [cards, setCards] = useState([]);
  const [filters, setFilters] = useState({ events: [] });
  const [seasonStats, setSeasonStats] = useState([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState(null);
  const [eventFilter, setEventFilter] = useState("all");
  const [sortBy, setSortBy] = useState("played-score");
  const [minGames, setMinGames] = useState(3);
  const [search, setSearch] = useState("");

  useEffect(() => {
    Promise.allSettled([
      getPlayedWinrateFilters(),
      getPlayedWinrateSeasonStats(),
    ]).then(([flt, ss]) => {
      if (flt.status === "fulfilled") setFilters(flt.value);
      if (ss.status === "fulfilled") setSeasonStats(ss.value);
    });
  }, []);

  useEffect(() => {
    setLoading(true);
    const params = {};
    if (eventFilter !== "all") params.event = eventFilter;
    getPlayedWinrates(params)
      .then(setCards)
      .catch((err) => setError(err.message))
      .finally(() => setLoading(false));
  }, [eventFilter]);

  const filtered = useMemo(() => {
    let result = cards.filter((c) => c.total >= minGames);
    if (search) {
      const q = search.toLowerCase();
      result = result.filter((c) => c.name.toLowerCase().includes(q));
    }
    return sortCards(result, sortBy);
  }, [cards, sortBy, minGames, search]);

  const totalGames = useMemo(
    () => cards.reduce((s, c) => s + c.total, 0),
    [cards],
  );

  if (error) return <p className="text-center text-accent-red py-8">{error}</p>;

  return (
    <div>
      <section className="text-center mb-6">
        <h1 className="text-2xl font-display text-secondary">
          Card Played Win Rates
        </h1>
        <p className="text-sm text-text-muted mt-1">
          When a card is played in a game, how likely is the player to win?
          Sorted by {SORT_LABELS[sortBy]}
        </p>
        <p className="text-xs text-text-muted mt-1">
          Data from Sorcery Online reported matches
          {totalGames > 0 && ` \u2014 ${Math.round(totalGames / 2).toLocaleString()} games analyzed`}
        </p>
        {seasonStats.length > 0 && (
          <p className="text-xs text-text-muted mt-1">
            {seasonStats.map((s, i) => (
              <span key={s.id}>
                {i > 0 && " | "}
                {s.name}{s.is_active ? " (current)" : ""}: {s.total_games.toLocaleString()} games
              </span>
            ))}
          </p>
        )}
      </section>

      <div className="flex flex-wrap justify-center gap-4 mb-6">
        <div className="flex items-center gap-2">
          <label className="text-sm text-text-muted">Event:</label>
          <select
            value={eventFilter}
            onChange={(e) => setEventFilter(e.target.value)}
            className="bg-bg-surface border border-border rounded px-2 py-1 text-sm"
          >
            <option value="all">All Events</option>
            {(filters.events || []).map((ev) => (
              <option
                key={ev.event_id || "current"}
                value={ev.is_active ? "current" : String(ev.event_id)}
              >
                {ev.event_name}
              </option>
            ))}
          </select>
        </div>
        <div className="flex items-center gap-2">
          <label className="text-sm text-text-muted">Min games:</label>
          <select
            value={minGames}
            onChange={(e) => setMinGames(Number(e.target.value))}
            className="bg-bg-surface border border-border rounded px-2 py-1 text-sm"
          >
            {MIN_GAMES_OPTIONS.map((n) => (
              <option key={n} value={n}>{n}+</option>
            ))}
          </select>
        </div>
        <div className="flex items-center gap-2">
          <label className="text-sm text-text-muted">Sort by:</label>
          <select
            value={sortBy}
            onChange={(e) => setSortBy(e.target.value)}
            className="bg-bg-surface border border-border rounded px-2 py-1 text-sm"
          >
            {SORT_OPTIONS.map((o) => (
              <option key={o.value} value={o.value}>{o.label}</option>
            ))}
          </select>
        </div>
        <input
          type="text"
          placeholder="Search cards..."
          value={search}
          onChange={(e) => setSearch(e.target.value)}
          className="w-48 px-3 py-1 bg-bg-surface border border-border rounded text-sm text-text placeholder:text-text-muted focus:outline-none focus:border-primary"
        />
      </div>

      {loading ? (
        <Spinner className="py-20" />
      ) : (
        <>
          <p className="text-xs text-text-muted text-center mb-4">
            Showing {filtered.length} of {cards.length} cards (min {minGames} games)
          </p>
          <div className="grid grid-cols-2 sm:grid-cols-3 md:grid-cols-4 lg:grid-cols-5 gap-3">
            {filtered.map((card) => (
              <div
                key={card.name}
                className="bg-bg-surface border border-border rounded-soft overflow-hidden hover:border-primary/50 transition-colors"
              >
                {card.image_url ? (
                  <img
                    src={card.image_url}
                    alt={card.name}
                    className="w-full aspect-[2.5/3.5] object-cover"
                    loading="lazy"
                  />
                ) : (
                  <div className="w-full aspect-[2.5/3.5] bg-bg-elevated flex items-center justify-center">
                    <span className="text-text-muted text-xs text-center px-2">{card.name}</span>
                  </div>
                )}
                <div className="p-2 text-center">
                  <h3 className="text-xs font-semibold truncate mb-1">{card.name}</h3>
                  <div
                    className="text-lg font-bold"
                    style={{ color: getWinRateColor(card.win_rate) }}
                  >
                    {card.win_rate}%
                  </div>
                  <div className="text-xs text-text-muted">
                    {card.wins}W - {card.losses}L ({card.total} games)
                  </div>
                </div>
              </div>
            ))}
          </div>
          {filtered.length === 0 && (
            <p className="text-center text-text-muted py-8">
              No cards found with {minGames}+ games played.
            </p>
          )}
        </>
      )}
    </div>
  );
}
