import { useState, useEffect, useMemo, useCallback } from "react";
import { Link, useNavigate } from "react-router-dom";
import { get } from "@/api/client";
import {
  getAvatars,
  getAvatarImageFiles,
  getAvatarFilters,
  getPlayDrawStats,
} from "@/api/cards";
import { getAvatarImageSettings } from "@/api/admin";
import { useAuth } from "@/context/AuthContext";
import AvatarImageAdmin from "@/components/ui/AvatarImageAdmin";
import Spinner from "@/components/ui/Spinner";
import usePageTitle from "@/hooks/usePageTitle";

const SORT_OPTIONS = [
  { value: "accuracy", label: "Accuracy Score" },
  { value: "winrate", label: "Win Rate" },
  { value: "alphabetical", label: "Alphabetical" },
  { value: "most-played", label: "Most Played" },
  { value: "most-wins", label: "Most Wins" },
  { value: "best-record", label: "Best Record (+/-)" },
];

const SORT_LABELS = {
  accuracy: "accuracy score (win rate \u00d7 games played)",
  winrate: "win rate",
  alphabetical: "name (A\u2013Z)",
  "most-played": "most games played",
  "most-wins": "most wins",
  "best-record": "best record (wins \u2212 losses)",
};

function getWinRateColor(winRate) {
  const pct = Math.max(0, Math.min(100, winRate));
  if (pct <= 50) {
    const ratio = pct / 50;
    return `rgb(${Math.round(231 + 24 * ratio)}, ${Math.round(76 + 179 * ratio)}, ${Math.round(60 + 195 * ratio)})`;
  }
  const ratio = (pct - 50) / 50;
  return `rgb(${Math.round(255 - 209 * ratio)}, ${Math.round(255 - 51 * ratio)}, ${Math.round(255 - 142 * ratio)})`;
}

function getAvatarImagePath(name, files) {
  const norm = (s) => s.toLowerCase().replace(/[^a-z0-9]/g, "");
  const n = norm(name);
  for (const f of files) {
    if (norm(f.replace(/\.\w+$/, "")) === n) return f;
  }
  for (const f of files) {
    if (norm(f.replace(/\.\w+$/, "")).includes(n)) return f;
  }
  for (const f of files) {
    if (n.includes(norm(f.replace(/\.\w+$/, "")))) return f;
  }
  return null;
}

function sortAvatars(data, key) {
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
    case "best-record":
      return d.sort(
        (a, b) => b.wins - b.losses - (a.wins - a.losses) || b.total - a.total,
      );
    default:
      return d.sort((a, b) => b.win_rate * b.total - a.win_rate * a.total);
  }
}

function EloBreakdown({ sourceFilter }) {
  const navigate = useNavigate()
  const [data, setData] = useState(null)
  const [loading, setLoading] = useState(true)
  const [sortCol, setSortCol] = useState('overall')
  const [sortAsc, setSortAsc] = useState(false)

  useEffect(() => {
    setLoading(true)
    get(`/api/avatars/elo-breakdown?source=${sourceFilter}`)
      .then(setData)
      .catch(() => setData(null))
      .finally(() => setLoading(false))
  }, [sourceFilter])

  if (loading) return <p className="text-text-muted text-sm py-4">Loading ELO breakdown...</p>
  if (!data || !data.avatars?.length) return <p className="text-text-muted text-sm py-4">Not enough data for ELO breakdown.</p>

  const { brackets, avatars, bracket_averages } = data

  const toggleSort = (col) => {
    if (sortCol === col) setSortAsc(!sortAsc)
    else { setSortCol(col); setSortAsc(false) }
  }

  const sorted = [...avatars].sort((a, b) => {
    let av, bv
    if (sortCol === 'name') {
      return sortAsc ? a.name.localeCompare(b.name) : b.name.localeCompare(a.name)
    } else if (sortCol === 'overall') {
      av = a.overall.win_rate ?? -1
      bv = b.overall.win_rate ?? -1
    } else {
      const idx = parseInt(sortCol, 10)
      av = a.bracket_rates[idx]?.win_rate ?? -1
      bv = b.bracket_rates[idx]?.win_rate ?? -1
    }
    return sortAsc ? av - bv : bv - av
  })

  const sortIcon = (col) => sortCol === col ? (sortAsc ? ' \u25B2' : ' \u25BC') : ''

  return (
    <div className="overflow-x-auto">
      <table className="w-full text-sm border-collapse">
        <thead>
          <tr className="border-b border-border">
            <th className="px-2 py-2 text-left text-xs font-semibold text-text-muted uppercase whitespace-nowrap cursor-pointer" onClick={() => toggleSort('name')}>
              Avatar{sortIcon('name')}
            </th>
            {brackets.map((b, i) => (
              <th key={b} className="px-2 py-2 text-center text-xs font-semibold text-text-muted uppercase whitespace-nowrap cursor-pointer" onClick={() => toggleSort(String(i))}>
                {b}-{b + 99}{sortIcon(String(i))}
              </th>
            ))}
            <th className="px-2 py-2 text-center text-xs font-bold text-secondary uppercase whitespace-nowrap cursor-pointer" onClick={() => toggleSort('overall')}>
              Overall{sortIcon('overall')}
            </th>
          </tr>
        </thead>
        <tbody>
          {sorted.map((avatar) => (
            <tr key={avatar.name} className="border-b border-border/50 hover:bg-bg-elevated/50 transition-colors">
              <td className="px-2 py-2 text-xs font-bold whitespace-nowrap">
                <Link to={`/avatar/${encodeURIComponent(avatar.name)}`} className="text-primary hover:underline">
                  {avatar.name}
                </Link>
              </td>
              {avatar.bracket_rates.map((cell, i) => {
                const avg = bracket_averages[i]
                const deviation = cell.win_rate != null && avg != null ? cell.win_rate - avg : null
                const cellClickable = cell.total > 0
                return (
                  <td
                    key={brackets[i]}
                    className={`px-2 py-2 text-center whitespace-nowrap ${cellClickable ? 'cursor-pointer hover:bg-bg-elevated/70' : ''}`}
                    onClick={cellClickable ? () => navigate(`/avatars/elo-matches?avatar=${encodeURIComponent(avatar.name)}&bracket=${brackets[i]}&source=${sourceFilter}`) : undefined}
                  >
                    {cell.win_rate != null ? (
                      <>
                        <span className="font-bold" style={{ color: getWinRateColor(cell.win_rate) }}>
                          {cell.win_rate}%
                        </span>
                        <div className="text-xs text-text-muted">({cell.total})</div>
                        {deviation != null && (
                          <div className={`text-xs ${deviation > 0 ? 'text-green-400' : 'text-red-400'}`}>
                            {deviation > 0 ? '+' : ''}{deviation.toFixed(1)}
                          </div>
                        )}
                      </>
                    ) : (
                      <span className="text-text-muted text-xs">{cell.total > 0 ? `${cell.total}g` : '—'}</span>
                    )}
                  </td>
                )
              })}
              <td
                className="px-2 py-2 text-center whitespace-nowrap bg-bg-elevated/30 cursor-pointer hover:bg-bg-elevated/70"
                onClick={() => navigate(`/avatars/elo-matches?avatar=${encodeURIComponent(avatar.name)}&bracket=all&source=${sourceFilter}`)}
              >
                {avatar.overall.win_rate != null ? (
                  <>
                    <span className="font-bold" style={{ color: getWinRateColor(avatar.overall.win_rate) }}>
                      {avatar.overall.win_rate}%
                    </span>
                    <div className="text-xs text-text-muted">({avatar.overall.total})</div>
                  </>
                ) : (
                  <span className="text-text-muted">—</span>
                )}
              </td>
            </tr>
          ))}
          <tr className="border-t-2 border-border bg-bg-elevated/20">
            <td className="px-2 py-2 text-xs font-bold text-text-muted">AVG</td>
            {bracket_averages.map((avg, i) => (
              <td key={brackets[i]} className="px-2 py-2 text-center text-xs font-semibold text-text-muted">
                {avg != null ? `${avg}%` : '—'}
              </td>
            ))}
            <td className="px-2 py-2" />
          </tr>
        </tbody>
      </table>
    </div>
  )
}

export default function Avatars() {
  usePageTitle("Avatar Win Rates");
  const { user } = useAuth();
  const isAdmin = user?.is_admin === true;
  const [avatars, setAvatars] = useState([]);
  const [imageFiles, setImageFiles] = useState([]);
  const [imageSettings, setImageSettings] = useState({});
  const [filters, setFilters] = useState({ events: [], sources: [] });
  const [playDraw, setPlayDraw] = useState(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState(null);
  const [eventFilter, setEventFilter] = useState("all");
  const [sourceFilter, setSourceFilter] = useState("discord");
  const [sortBy, setSortBy] = useState("accuracy");

  useEffect(() => {
    Promise.allSettled([
      getAvatarImageFiles(),
      getAvatarFilters(),
      getPlayDrawStats(),
    ]).then(([imgs, flt, pd]) => {
      if (imgs.status === "fulfilled") setImageFiles(imgs.value);
      if (flt.status === "fulfilled") setFilters(flt.value);
      if (pd.status === "fulfilled") setPlayDraw(pd.value);
    });
  }, []);

  useEffect(() => {
    if (!isAdmin) return;
    getAvatarImageSettings()
      .then((data) => setImageSettings(data.settings || {}))
      .catch(() => {});
  }, [isAdmin]);

  const handleImageSettingsSaved = useCallback((avatarName, newSettings) => {
    setImageSettings((prev) => {
      const next = { ...prev };
      if (newSettings) next[avatarName] = newSettings;
      else delete next[avatarName];
      return next;
    });
  }, []);

  useEffect(() => {
    setLoading(true);
    const params = { source: sourceFilter };
    if (eventFilter !== "all") params.event = eventFilter;
    getAvatars(params)
      .then(setAvatars)
      .catch((err) => setError(err.message))
      .finally(() => setLoading(false));
  }, [eventFilter, sourceFilter]);

  const sorted = useMemo(() => sortAvatars(avatars, sortBy), [avatars, sortBy]);
  const totalGames = useMemo(
    () => avatars.reduce((s, a) => s + a.total, 0),
    [avatars],
  );

  if (error) return <p className="text-center text-accent-red py-8">{error}</p>;

  return (
    <div>
      <section className="text-center mb-6">
        <h1 className="text-2xl font-display text-secondary">
          Avatar Win Rates
        </h1>
        <p className="text-sm text-text-muted mt-1">
          Global statistics from all matches reported with decklists, sorted by{" "}
          {SORT_LABELS[sortBy]}
        </p>
        {playDraw?.play_stats && playDraw?.draw_stats && (
          <p className="text-xs text-text-muted mt-2">
            Overall (from 2/7/2026 onward):&nbsp; On the Play:{" "}
            <span
              style={{ color: getWinRateColor(playDraw.play_stats.win_rate) }}>
              {playDraw.play_stats.win_rate}%
            </span>{" "}
            ({playDraw.play_stats.wins}W-{playDraw.play_stats.losses}L,{" "}
            {playDraw.play_stats.total} games) |&nbsp; On the Draw:{" "}
            <span
              style={{ color: getWinRateColor(playDraw.draw_stats.win_rate) }}>
              {playDraw.draw_stats.win_rate}%
            </span>{" "}
            ({playDraw.draw_stats.wins}W-{playDraw.draw_stats.losses}L,{" "}
            {playDraw.draw_stats.total} games)
          </p>
        )}
      </section>

      <div className="flex flex-wrap justify-center gap-4 mb-6">
        <div className="flex items-center gap-2">
          <label className="text-sm text-text-muted">Event:</label>
          <select
            value={eventFilter}
            onChange={(e) => setEventFilter(e.target.value)}
            className="bg-bg-surface border border-border rounded px-2 py-1 text-sm">
            <option value="all">All Events</option>
            {(filters.events || []).map((ev) => (
              <option
                key={ev.event_id || "current"}
                value={ev.is_active ? "current" : String(ev.event_id)}>
                {ev.event_name}
              </option>
            ))}
          </select>
        </div>
        <div className="flex items-center gap-2">
          <label className="text-sm text-text-muted">Source:</label>
          <div className="inline-flex bg-bg-surface border border-border rounded-lg overflow-hidden">
            {[
              ["discord", "Online"],
              ["web", "Paper"],
            ].map(([val, label]) => (
              <button
                key={val}
                className={`px-3 py-1 text-xs font-medium transition-colors ${sourceFilter === val ? "bg-primary text-bg" : "text-text-muted hover:text-text"}`}
                onClick={() => setSourceFilter(val)}>
                {label}
              </button>
            ))}
          </div>
        </div>
        <div className="flex items-center gap-2">
          <label className="text-sm text-text-muted">Sort by:</label>
          <select
            value={sortBy}
            onChange={(e) => setSortBy(e.target.value)}
            className="bg-bg-surface border border-border rounded px-2 py-1 text-sm">
            {SORT_OPTIONS.map((o) => (
              <option key={o.value} value={o.value}>
                {o.label}
              </option>
            ))}
          </select>
        </div>
      </div>

      {loading ? (
        <Spinner className="py-20" />
      ) : (
        <>
          <div className="grid grid-cols-2 sm:grid-cols-3 md:grid-cols-4 lg:grid-cols-5 gap-3 mb-8">
            {sorted.map((avatar, i) => {
              const imgFile = getAvatarImagePath(avatar.name, imageFiles);
              const imgSrc = imgFile ? `/avatar-images/${imgFile}` : null;
              const settings = imageSettings[avatar.name] || {};
              const bgPos = `${settings.position_x ?? 50}% ${settings.position_y ?? 25}%`;
              const bgBrightness = settings.brightness ?? 1.0;
              const bgOpacity = settings.opacity ?? 0.5;
              return (
                <Link
                  key={avatar.name}
                  to={`/avatar/${encodeURIComponent(avatar.name)}`}
                  className="relative bg-bg-surface border border-border rounded-soft overflow-hidden hover:border-primary/50 transition-colors group"
                  style={{ minHeight: "140px" }}>
                  {imgSrc && (
                    <>
                      <div
                        className="absolute inset-0 bg-cover bg-center"
                        style={{
                          backgroundImage: `url('${imgSrc}')`,
                          backgroundPosition: bgPos,
                          filter: `brightness(${bgBrightness})`,
                          opacity: bgOpacity,
                        }}
                      />
                      <div className="absolute inset-0 bg-black/20" />
                    </>
                  )}
                  <div
                    className="relative p-3 flex flex-col h-full justify-between"
                    style={{ textShadow: "0 1px 4px rgba(0,0,0,0.8)" }}>
                    <div>
                      <div className="text-xs text-text-muted font-medium">
                        #{i + 1}:
                      </div>
                      <h3
                        className="font-bold leading-tight"
                        style={{ fontSize: "1.25rem" }}>
                        {avatar.name}
                      </h3>
                    </div>
                    <div className="mt-2">
                      <div className="text-xs font-medium">
                        Winrate:{" "}
                        <span
                          className="text-base font-bold"
                          style={{ color: getWinRateColor(avatar.win_rate) }}>
                          {avatar.win_rate}%
                        </span>
                      </div>
                      {avatar.top_player && (
                        <div className="text-xs mt-1 font-medium">
                          <span className="text-text-muted">Top Player:</span>
                          <div className="text-secondary">
                            {avatar.top_player.name}
                          </div>
                        </div>
                      )}
                    </div>
                    {isAdmin && imgSrc && (
                      <div
                        onClick={(e) => {
                          e.preventDefault();
                          e.stopPropagation();
                        }}>
                        <AvatarImageAdmin
                          avatarName={avatar.name}
                          imgSrc={imgSrc}
                          currentSettings={settings}
                          onSaved={handleImageSettingsSaved}
                        />
                      </div>
                    )}
                  </div>
                </Link>
              );
            })}
          </div>

          <section className="mb-8">
            <h2 className="text-center text-text-muted text-sm mb-4">
              Total Decklists Reported: {totalGames}
            </h2>
            <div className="overflow-x-auto">
              <table className="w-full">
                <thead className="border-b border-border">
                  <tr>
                    <th className="px-3 py-2 text-left text-xs font-semibold text-text-muted uppercase">
                      Avatar Name
                    </th>
                    <th className="px-3 py-2 text-center text-xs font-semibold text-text-muted uppercase">
                      Reported Games
                    </th>
                    <th className="px-3 py-2 text-center text-xs font-semibold text-text-muted uppercase">
                      % of All Games
                    </th>
                  </tr>
                </thead>
                <tbody className="divide-y divide-border">
                  {[...avatars]
                    .sort((a, b) => b.total - a.total)
                    .map((avatar) => (
                      <tr
                        key={avatar.name}
                        className="hover:bg-bg-elevated transition-colors">
                        <td className="px-3 py-2 text-sm">
                          <Link
                            to={`/avatar/${encodeURIComponent(avatar.name)}`}
                            className="text-primary hover:underline">
                            {avatar.name}
                          </Link>
                        </td>
                        <td className="px-3 py-2 text-sm text-center">
                          {avatar.total}
                        </td>
                        <td className="px-3 py-2 text-sm text-center">
                          {totalGames > 0
                            ? ((avatar.total / totalGames) * 100).toFixed(1)
                            : 0}
                          %
                        </td>
                      </tr>
                    ))}
                </tbody>
              </table>
            </div>
          </section>

          {isAdmin && (
            <section className="mb-8">
              <h2 className="text-lg font-semibold text-center mb-1">
                Win Rate by ELO Bracket (All Avatars)
              </h2>
              <p className="text-xs text-text-muted text-center mb-4">
                Compares avatar win rates at each skill level. Yellow cells deviate 10%+ from average. Uses current player ratings.
              </p>
              <EloBreakdown sourceFilter={sourceFilter} />
            </section>
          )}
        </>
      )}
    </div>
  );
}
