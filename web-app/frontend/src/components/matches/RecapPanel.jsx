import { Link } from 'react-router-dom'

// Mirrors the recap embed the Discord bot posts (discord-bot/cogs/daily_summary.py).
const MATCH_TYPES = [
  ['total_matches', 'Ranked'],
  ['casual_matches', 'Casual'],
  ['limited_matches', 'Limited'],
  ['rumble_matches', 'Rumble'],
]

const total = (counts = {}) => MATCH_TYPES.reduce((sum, [key]) => sum + (counts[key] || 0), 0)

function delta(current, previous) {
  const diff = (current || 0) - (previous || 0)
  if (diff > 0) return `▲ ${diff}`
  if (diff < 0) return `▼ ${-diff}`
  return '±0'
}

function Section({ title, children }) {
  return (
    <div className="mt-4">
      <h4 className="font-semibold text-text-primary mb-1">{title}</h4>
      <ul className="space-y-1">{children}</ul>
    </div>
  )
}

const Code = ({ children }) => (
  <code className="bg-bg-raised rounded px-1 text-xs text-text-primary">{children}</code>
)

export default function RecapPanel({ recap }) {
  const { stats = {}, previous = {}, names = {} } = recap
  const compare = recap.compare_label

  const P = ({ id, name }) => (
    <Link to={`/player/${id}`} className="text-secondary font-semibold hover:underline">
      {names[String(id)] || name || 'Unknown'}
    </Link>
  )

  const matchTotal = total(stats)
  const prevTotal = total(previous)

  const extras = []
  if (stats.unique_players) {
    extras.push(`👥 ${stats.unique_players} players (${delta(stats.unique_players, previous.unique_players)})`)
  }
  if (stats.ironman) extras.push(`🕒 ${stats.ironman} hrs played`)
  if (stats.avg_duration != null) extras.push(`⏱️ ${Math.round(stats.avg_duration)} min avg`)

  let busiest = null
  if (recap.kind === 'weekly' && stats.busiest_day) {
    const [day, count] = stats.busiest_day
    const weekday = new Date(`${day}T00:00:00`).toLocaleDateString(undefined, { weekday: 'long' })
    busiest = `📆 Busiest day: ${weekday} (${count} ranked matches)`
  }

  const performers = []
  if (stats.top_gainer && stats.top_gainer[2] > 0) {
    const [id, name, change] = stats.top_gainer
    performers.push(<li key="gain">📈 <b>Top Gainer:</b> <P id={id} name={name} /> <Code>+{change}</Code></li>)
  }
  if (stats.biggest_loser) {
    const [id, name, change] = stats.biggest_loser
    performers.push(<li key="drop">📉 <b>Biggest Drop:</b> <P id={id} name={name} /> <Code>{change}</Code></li>)
  }
  if (stats.most_active) {
    const [id, name, count] = stats.most_active
    performers.push(<li key="active">👑 <b>Most Active:</b> <P id={id} name={name} /> — {count} matches</li>)
  }
  if (stats.deck_variety) {
    const [id, name, count] = stats.deck_variety
    performers.push(<li key="decks">🎴 <b>Deck Variety:</b> <P id={id} name={name} /> — {count} decks</li>)
  }

  const highlights = []
  if (stats.biggest_upset) {
    const [wId, wName, lId, lName, change] = stats.biggest_upset
    highlights.push(
      <li key="upset">🎯 <b>Biggest Upset:</b> <P id={wId} name={wName} /> beat <P id={lId} name={lName} /> <Code>+{change}</Code></li>
    )
  }
  if (stats.highest_rated) {
    const [wId, wName, lId, lName, wElo, lElo] = stats.highest_rated
    highlights.push(
      <li key="rated">🏆 <b>Highest Rated:</b> <P id={wId} name={wName} /> <Code>{wElo}</Code> vs <P id={lId} name={lName} /> <Code>{lElo}</Code></li>
    )
  }
  if (stats.rivalry) {
    const [p1Id, p1, p2Id, p2, p1w, p2w, games] = stats.rivalry
    highlights.push(
      <li key="rivalry">⚔️ <b>Rivalry:</b> <P id={p1Id} name={p1} /> vs <P id={p2Id} name={p2} /> — <Code>{p1w}-{p2w}</Code> ({games} games)</li>
    )
  }

  const hot = stats.hot_streaks || []
  const streaks = hot.slice(0, 5).map(([id, name, streak]) => (
    <li key={`hot-${id}`}>🔥 <P id={id} name={name} /> — <b>{streak}</b> wins in a row</li>
  ))
  if (hot.length > 5) streaks.push(<li key="hot-more">…and {hot.length - 5} more</li>)
  ;(stats.broken_streaks || []).slice(0, 5).forEach((e) => {
    streaks.push(
      <li key={`broken-${e.player_id}`}>
        💔 <P id={e.player_id} name={e.player} />'s <b>{e.streak}</b>-win streak ended by <P id={e.broken_by_id} name={e.broken_by} />
      </li>
    )
  })

  return (
    <section
      aria-label="Recap"
      className="mb-8 rounded-lg border border-border border-l-4 border-l-[#FFD700] bg-bg-surface p-4 sm:p-5 text-sm text-text-primary"
    >
      <h2 className="text-lg font-semibold text-text-primary">{recap.title}</h2>

      {matchTotal === 0 ? (
        <p className="mt-2 text-text-muted">
          No matches were played {recap.kind === 'weekly' ? 'this week' : 'today'} ({prevTotal} {compare}).
        </p>
      ) : (
        <>
          <div className="mt-2 space-y-1">
            <p>
              {MATCH_TYPES.filter(([key]) => stats[key]).map(([key, label], i) => (
                <span key={key}>{i > 0 && ' • '}<b>{stats[key]}</b> {label}</span>
              ))}
            </p>
            <p>📅 <b>{matchTotal}</b> matches total — {delta(matchTotal, prevTotal)} vs {compare} ({prevTotal})</p>
            {extras.length > 0 && <p>{extras.join(' • ')}</p>}
            {busiest && <p>{busiest}</p>}
          </div>
          {performers.length > 0 && <Section title="🏅 Top Performers">{performers}</Section>}
          {highlights.length > 0 && <Section title="✨ Match Highlights">{highlights}</Section>}
          {streaks.length > 0 && <Section title="🔥 Streaks">{streaks}</Section>}
        </>
      )}

      <p className="mt-4 text-xs text-text-muted">{recap.footer}</p>
    </section>
  )
}
