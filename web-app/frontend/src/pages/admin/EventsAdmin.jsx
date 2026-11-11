import { useCallback, useEffect, useState } from 'react'
import { Link } from 'react-router-dom'
import usePageTitle from '@/hooks/usePageTitle'
import PlayerPicker from '@/components/admin/PlayerPicker'
import { preconSeasonText } from '@/components/leaderboard/PreconLadderContent'
import {
  getPreconAdmin,
  updatePreconSettings,
  startPreconSeason,
  updatePreconSeason,
  endPreconSeason,
  reportPreconMatch,
  removePreconMatch,
} from '@/api/preconAdmin'

/**
 * Admin > Events: start, change and end the automatic event ladders from one
 * page instead of remembering bot commands. The Lavamancer vs Frostmage
 * precon ladder lives here; the other event tools are linked below it.
 */

const PRECONS = [
  { key: 'lavamancer', label: 'Lavamancer (LM)' },
  { key: 'frostmage', label: 'Frostmage (FM)' },
]
const SHORT = { lavamancer: 'LM', frostmage: 'FM' }
const TINT = { lavamancer: 'text-orange-300', frostmage: 'text-sky-300' }

const OTHER_TOOLS = [
  { to: '/admin/brackets', label: 'Manage Top Cut', blurb: 'Season top cut, Underdog and Limited brackets.' },
  { to: '/admin/explorer-calendar', label: 'Explorer events calendar', blurb: 'Community Series event dates and clashes.' },
  { to: '/admin/paper-badges', label: 'Paper Tournament Badges', blurb: 'Top 8 finishes on player profiles.' },
  { to: '/standings', label: 'Event Standings', blurb: 'What players see: every ladder and bracket.' },
]

const inputClass = 'h-9 rounded-lg border border-border bg-bg-raised px-3 text-sm text-text-primary w-full'
const buttonClass = 'px-3 py-1.5 rounded-lg text-sm font-semibold disabled:opacity-50'

/** A Date as the value a datetime-local input wants (browser time). */
function toLocalInput(iso) {
  if (!iso) return ''
  const d = new Date(iso)
  if (Number.isNaN(d.getTime())) return ''
  const pad = (n) => String(n).padStart(2, '0')
  return `${d.getFullYear()}-${pad(d.getMonth() + 1)}-${pad(d.getDate())}T${pad(d.getHours())}:${pad(d.getMinutes())}`
}

/** A datetime-local value (browser time) as an ISO time with offset. */
function fromLocalInput(value) {
  if (!value) return null
  const d = new Date(value)
  return Number.isNaN(d.getTime()) ? null : d.toISOString()
}

function formatWhen(iso) {
  if (!iso) return ''
  const d = new Date(iso)
  if (Number.isNaN(d.getTime())) return ''
  return d.toLocaleString(undefined, { month: 'short', day: 'numeric', hour: 'numeric', minute: '2-digit' })
}

function Card({ title, children, aside = null }) {
  return (
    <section className="bg-bg-surface border border-border rounded-soft p-4 sm:p-5">
      <div className="flex items-start justify-between gap-3 mb-3">
        <h3 className="font-semibold text-text-primary">{title}</h3>
        {aside}
      </div>
      {children}
    </section>
  )
}

function Switch({ on, onChange, disabled, label }) {
  return (
    <button
      type="button"
      role="switch"
      aria-checked={on}
      aria-label={label}
      disabled={disabled}
      onClick={() => onChange(!on)}
      className={`relative inline-flex h-6 w-11 shrink-0 items-center rounded-full transition-colors disabled:opacity-50 ${on ? 'bg-accent-green' : 'bg-bg-elevated border border-border'}`}
    >
      <span className={`inline-block h-5 w-5 rounded-full bg-white shadow transition-transform ${on ? 'translate-x-5' : 'translate-x-0.5'}`} />
    </button>
  )
}

function QueueCard({ state, busy, save }) {
  const on = state.settings.queue_enabled
  const running = state.open_season_id != null
  let note
  if (on && running) note = 'Players can join the 🧙 Precon (LM/FM) queue in Discord and on Play Sorcery Online.'
  else if (on) note = 'Switched on, but no ladder is running, so players don\'t see the queue yet. It opens when a ladder starts.'
  else if (running) note = 'Switched off: the ladder is running but nobody can queue. Turn it on to open the queue.'
  else note = 'Switched off. Players don\'t see the precon queue.'
  return (
    <Card
      title="Precon queue"
      aside={<Switch on={on} disabled={busy} label="Precon queue on or off" onChange={(v) => save(() => updatePreconSettings({ queue_enabled: v }), v ? 'Queue switched on.' : 'Queue switched off.')} />}
    >
      <p className={`text-sm ${on && running ? 'text-accent-green' : 'text-text-muted'}`}>{note}</p>
    </Card>
  )
}

function TestModeCard({ state, busy, save }) {
  const on = state.settings.pso_test_mode
  const live = state.settings.queue_enabled && state.open_season_id != null
  return (
    <Card
      title="Play Sorcery Online test mode"
      aside={<Switch on={on} disabled={busy} label="PSO test mode on or off" onChange={(v) => save(() => updatePreconSettings({ pso_test_mode: v }), v ? 'Test mode on.' : 'Test mode off.')} />}
    >
      <p className="text-sm text-text-muted">
        {on && live
          ? 'On, but the real queue is open, so PSO gets real answers. Test mode only answers while the queue is closed.'
          : on
            ? 'On: PSO can call the precon status, join and result endpoints and get 200 answers with sample data. Nobody is queued, nothing is recorded, and no ladder starts.'
            : 'Off. Turn it on so PSO can test the precon endpoints before a ladder starts.'}
      </p>
    </Card>
  )
}

function StartSeasonForm({ state, busy, save }) {
  const [name, setName] = useState('')
  const [days, setDays] = useState(state.settings.season_days)
  const [later, setLater] = useState(false)
  const [startsAt, setStartsAt] = useState('')
  const [openQueue, setOpenQueue] = useState(true)
  const limits = state.limits.season_days || { min: 1, max: 120 }

  const submit = (e) => {
    e.preventDefault()
    save(
      () => startPreconSeason({
        name,
        days: Number(days),
        starts_at: later ? fromLocalInput(startsAt) : null,
        open_queue: openQueue,
      }),
      `${name} started.`,
    ).then((ok) => ok && setName(''))
  }

  return (
    <Card title="Start a ladder">
      <form onSubmit={submit} className="space-y-3">
        <label className="block text-sm">
          <span className="text-text-muted">Name</span>
          <input value={name} onChange={(e) => setName(e.target.value)} placeholder="LM vs FM Ladder 1" maxLength={80} required className={`${inputClass} mt-1`} />
        </label>
        <div className="grid grid-cols-1 sm:grid-cols-2 gap-3">
          <label className="block text-sm">
            <span className="text-text-muted">Length (days)</span>
            <input type="number" min={limits.min} max={limits.max} value={days} onChange={(e) => setDays(e.target.value)} required className={`${inputClass} mt-1`} />
          </label>
          <div className="text-sm">
            <span className="text-text-muted">Starts</span>
            <div className="flex gap-3 mt-2">
              <label className="flex items-center gap-1.5"><input type="radio" checked={!later} onChange={() => setLater(false)} /> Now</label>
              <label className="flex items-center gap-1.5"><input type="radio" checked={later} onChange={() => setLater(true)} /> Later</label>
            </div>
          </div>
        </div>
        {later && (
          <label className="block text-sm">
            <span className="text-text-muted">Start date and time (your time)</span>
            <input type="datetime-local" value={startsAt} onChange={(e) => setStartsAt(e.target.value)} required className={`${inputClass} mt-1`} />
          </label>
        )}
        <label className="flex items-center gap-2 text-sm">
          <input type="checkbox" checked={openQueue} onChange={(e) => setOpenQueue(e.target.checked)} />
          Switch the precon queue on too
        </label>
        <button type="submit" disabled={busy || !name.trim()} className={`${buttonClass} bg-primary text-white`}>Start ladder</button>
      </form>
    </Card>
  )
}

function CurrentSeasonCard({ season, isOpen, busy, save }) {
  const [name, setName] = useState(season.name)
  const [startsAt, setStartsAt] = useState(toLocalInput(season.starts_at_iso))
  const [endsAt, setEndsAt] = useState(toLocalInput(season.ends_at_iso))

  useEffect(() => {
    setName(season.name)
    setStartsAt(toLocalInput(season.starts_at_iso))
    setEndsAt(toLocalInput(season.ends_at_iso))
  }, [season.season_id, season.name, season.starts_at_iso, season.ends_at_iso])

  const changed = name.trim() !== season.name
    || startsAt !== toLocalInput(season.starts_at_iso)
    || endsAt !== toLocalInput(season.ends_at_iso)

  const saveEdits = (e) => {
    e.preventDefault()
    const body = { name: name.trim() }
    if (startsAt !== toLocalInput(season.starts_at_iso)) body.starts_at = fromLocalInput(startsAt)
    if (endsAt !== toLocalInput(season.ends_at_iso)) body.ends_at = fromLocalInput(endsAt)
    save(() => updatePreconSeason(season.season_id, body), 'Ladder updated.')
  }

  const endNow = () => {
    if (!window.confirm(`End ${season.name} now? Final standings get posted in the LFG channel and the queue closes.`)) return
    save(() => endPreconSeason(), `${season.name} ended. Final standings are being posted.`)
  }

  return (
    <Card
      title={isOpen ? 'Running now' : 'Scheduled'}
      aside={<span className={`text-xs font-semibold px-2 py-0.5 rounded-full ${isOpen ? 'bg-accent-green/15 text-accent-green' : 'bg-secondary/15 text-secondary'}`}>{isOpen ? 'Live' : 'Not started'}</span>}
    >
      <p className="text-lg font-display text-white">{season.name}</p>
      <p className="text-sm text-text-muted mb-1">{preconSeasonText(season)}</p>
      <p className="text-sm text-text-muted mb-4">
        {season.games} game{season.games === 1 ? '' : 's'} · {season.players} player{season.players === 1 ? '' : 's'} ·{' '}
        <Link to={`/elo?board=precon:${season.season_id}`} className="text-primary hover:underline">Standings</Link>
      </p>
      <form onSubmit={saveEdits} className="space-y-3">
        <label className="block text-sm">
          <span className="text-text-muted">Name</span>
          <input value={name} onChange={(e) => setName(e.target.value)} maxLength={80} required className={`${inputClass} mt-1`} />
        </label>
        <div className="grid grid-cols-1 sm:grid-cols-2 gap-3">
          <label className="block text-sm">
            <span className="text-text-muted">Starts (your time)</span>
            <input type="datetime-local" value={startsAt} onChange={(e) => setStartsAt(e.target.value)} required className={`${inputClass} mt-1`} />
          </label>
          <label className="block text-sm">
            <span className="text-text-muted">Ends (your time)</span>
            <input type="datetime-local" value={endsAt} onChange={(e) => setEndsAt(e.target.value)} required className={`${inputClass} mt-1`} />
          </label>
        </div>
        <p className="text-xs text-text-muted">Moving the dates re-rates the ladder: only games between the start and end count.</p>
        <div className="flex flex-wrap gap-2">
          <button type="submit" disabled={busy || !changed} className={`${buttonClass} bg-primary text-white`}>Save changes</button>
          {isOpen && (
            <button type="button" onClick={endNow} disabled={busy} className={`${buttonClass} border border-accent-red/60 text-accent-red hover:bg-accent-red/10`}>
              End ladder now
            </button>
          )}
        </div>
      </form>
    </Card>
  )
}

function RulesCard({ state, busy, save }) {
  const [rules, setRules] = useState(state.settings)
  useEffect(() => setRules(state.settings), [state.settings])
  const lim = state.limits
  const changed = ['min_ranked_games', 'block_rematch', 'season_days'].some((k) => String(rules[k]) !== String(state.settings[k]))

  const submit = (e) => {
    e.preventDefault()
    save(() => updatePreconSettings({
      min_ranked_games: Number(rules.min_ranked_games),
      block_rematch: rules.block_rematch,
      season_days: Number(rules.season_days),
    }), 'Rules saved.')
  }

  return (
    <Card title="Rules">
      <form onSubmit={submit} className="space-y-3">
        <div className="grid grid-cols-1 sm:grid-cols-2 gap-3">
          <label className="block text-sm">
            <span className="text-text-muted">Games to be ranked</span>
            <input type="number" min={lim.min_ranked_games?.min} max={lim.min_ranked_games?.max} value={rules.min_ranked_games} onChange={(e) => setRules({ ...rules, min_ranked_games: e.target.value })} required className={`${inputClass} mt-1`} />
          </label>
          <label className="block text-sm">
            <span className="text-text-muted">New ladder length (days)</span>
            <input type="number" min={lim.season_days?.min} max={lim.season_days?.max} value={rules.season_days} onChange={(e) => setRules({ ...rules, season_days: e.target.value })} required className={`${inputClass} mt-1`} />
          </label>
        </div>
        <label className="flex items-start gap-2 text-sm">
          <input type="checkbox" className="mt-0.5" checked={rules.block_rematch} onChange={(e) => setRules({ ...rules, block_rematch: e.target.checked })} />
          <span>
            No back-to-back rematches
            <span className="block text-xs text-text-muted">Two players whose last precon game was against each other aren't paired again straight away.</span>
          </span>
        </label>
        <p className="text-xs text-text-muted">
          Games to be ranked applies to every ladder straight away, including past ones. Length is used for the next ladder you start.
          Ratings are Glicko-2, everyone starts at 1500.
        </p>
        <button type="submit" disabled={busy || !changed} className={`${buttonClass} bg-primary text-white`}>Save rules</button>
      </form>
    </Card>
  )
}

function PlayerSlot({ label, player, precon, onPlayer, onPrecon }) {
  return (
    <div className="space-y-2">
      <span className="block text-sm text-text-muted">{label}</span>
      <div className="flex items-center gap-2 flex-wrap">
        {player && <span className="text-sm font-semibold text-white">{player.display_name}</span>}
        <PlayerPicker onPick={onPlayer} label={player ? 'Change' : 'Pick player'} />
      </div>
      <select value={precon} onChange={(e) => onPrecon(e.target.value)} className={inputClass} aria-label={`${label} precon`}>
        <option value="">Precon…</option>
        {PRECONS.map((p) => <option key={p.key} value={p.key}>{p.label}</option>)}
      </select>
    </div>
  )
}

function ReportCard({ state, busy, save }) {
  const [winner, setWinner] = useState(null)
  const [loser, setLoser] = useState(null)
  const [wp, setWp] = useState('')
  const [lp, setLp] = useState('')
  const ready = winner && loser && wp && lp && winner.user_id !== loser.user_id

  const submit = (e) => {
    e.preventDefault()
    save(() => reportPreconMatch({
      winner_id: winner.user_id, winner_name: winner.display_name, winner_precon: wp,
      loser_id: loser.user_id, loser_name: loser.display_name, loser_precon: lp,
    }), `Recorded: ${winner.display_name} beat ${loser.display_name}.`).then((ok) => {
      if (ok) { setWinner(null); setLoser(null); setWp(''); setLp('') }
    })
  }

  return (
    <Card title="Report a game by hand">
      <form onSubmit={submit} className="space-y-3">
        <div className="grid grid-cols-1 sm:grid-cols-2 gap-4">
          <PlayerSlot label="Winner" player={winner} precon={wp} onPlayer={setWinner} onPrecon={setWp} />
          <PlayerSlot label="Loser" player={loser} precon={lp} onPlayer={setLoser} onPrecon={setLp} />
        </div>
        {state.open_season_id == null && (
          <p className="text-xs text-text-muted">No ladder is running, so the game is saved but doesn't move ratings.</p>
        )}
        <button type="submit" disabled={busy || !ready} className={`${buttonClass} bg-primary text-white`}>Record game</button>
      </form>
    </Card>
  )
}

function RecentGamesCard({ games, busy, save }) {
  const [all, setAll] = useState(false)
  const shown = all ? games : games.slice(0, 10)
  const remove = (g) => {
    if (!window.confirm(`Remove game P${g.match_id} (${g.winner_display_name} beat ${g.loser_display_name})? The ladder gets re-rated.`)) return
    save(() => removePreconMatch(g.match_id), `Game P${g.match_id} removed and the ladder re-rated.`)
  }
  return (
    <Card title="Latest games">
      {games.length === 0 ? (
        <p className="text-sm text-text-muted">No games on this ladder yet.</p>
      ) : (
        <ul className="divide-y divide-border -mx-1">
          {shown.map((g) => (
            <li key={g.match_id} className="px-1 py-2 text-sm flex flex-wrap items-center gap-x-2 gap-y-1">
              <span className="text-xs text-text-muted w-12">P{g.match_id}</span>
              <span className="font-medium text-white">{g.winner_display_name}</span>
              <span className={`text-xs font-semibold ${TINT[g.winner_precon] || ''}`}>{SHORT[g.winner_precon]}</span>
              <span className="text-text-muted">beat</span>
              <span className="font-medium">{g.loser_display_name}</span>
              <span className={`text-xs font-semibold ${TINT[g.loser_precon] || ''}`}>{SHORT[g.loser_precon]}</span>
              <span className="text-xs text-text-muted">{formatWhen(g.timestamp)}</span>
              <button type="button" onClick={() => remove(g)} disabled={busy} className="ml-auto text-xs text-accent-red hover:underline disabled:opacity-50">Remove</button>
            </li>
          ))}
        </ul>
      )}
      {games.length > 10 && (
        <button type="button" onClick={() => setAll(!all)} className="mt-2 text-sm text-primary hover:underline">
          {all ? 'Show fewer' : `Show all ${games.length}`}
        </button>
      )}
    </Card>
  )
}

function PastSeasons({ seasons, currentId }) {
  const past = seasons.filter((s) => s.season_id !== currentId)
  if (!past.length) return null
  return (
    <Card title="Past ladders">
      <ul className="divide-y divide-border">
        {past.map((s) => (
          <li key={s.season_id} className="py-2 text-sm flex flex-wrap items-center gap-x-3 gap-y-1">
            <Link to={`/elo?board=precon:${s.season_id}`} className="font-medium text-white hover:text-primary">{s.name}</Link>
            <span className="text-text-muted">{preconSeasonText(s)}</span>
            <span className="text-text-muted ml-auto">{s.games} games · {s.players} players</span>
          </li>
        ))}
      </ul>
    </Card>
  )
}

export default function EventsAdmin() {
  usePageTitle('Events admin')
  const [state, setState] = useState(null)
  const [error, setError] = useState('')
  const [notice, setNotice] = useState('')
  const [busy, setBusy] = useState(false)

  const load = useCallback(() => {
    getPreconAdmin().then(setState).catch((e) => setError(e.message))
  }, [])
  useEffect(load, [load])

  /** Run one change; the response is the page's new state. Resolves true on success. */
  const save = useCallback(async (call, message) => {
    setBusy(true)
    setError('')
    setNotice('')
    try {
      const next = await call()
      setState(next)
      setNotice(next.bot_refreshed === false
        ? `${message} Discord picks it up within a minute.`
        : message)
      return true
    } catch (e) {
      setError(e.message)
      return false
    } finally {
      setBusy(false)
    }
  }, [])

  const current = state?.seasons.find((s) => s.season_id === state.current_season_id)
  const showCurrent = current && (current.is_open || new Date(current.starts_at_iso).getTime() > Date.now())

  return (
    <div className="max-w-4xl mx-auto space-y-6">
      <div>
        <Link to="/admin" className="text-sm text-text-muted hover:text-primary">← Admin</Link>
        <h1 className="text-2xl font-display text-secondary mt-1">Events</h1>
        <p className="text-sm text-text-muted mt-1">Start, change and end event ladders here instead of with bot commands.</p>
      </div>

      <div className="space-y-4">
        <div>
          <h2 className="text-xl font-display text-white">
            <span className="text-orange-300">Lavamancer</span> vs <span className="text-sky-300">Frostmage</span> ladder
          </h2>
          <p className="text-sm text-text-muted">Precon queue with its own Glicko-2 ladder. Players see it on the home page LM / FM tab.</p>
        </div>

        {error && <p role="alert" className="text-sm text-accent-red bg-accent-red/10 border border-accent-red/40 rounded-lg px-3 py-2">{error}</p>}
        {notice && <p role="status" className="text-sm text-accent-green bg-accent-green/10 border border-accent-green/40 rounded-lg px-3 py-2">{notice}</p>}

        {!state ? (
          !error && <p className="text-sm text-text-muted">Loading…</p>
        ) : (
          <>
            <div className="grid grid-cols-1 lg:grid-cols-2 gap-4 items-start">
              <QueueCard state={state} busy={busy} save={save} />
              <TestModeCard state={state} busy={busy} save={save} />
            </div>
            <div className="grid grid-cols-1 lg:grid-cols-2 gap-4 items-start">
              {showCurrent
                ? <CurrentSeasonCard season={current} isOpen={current.is_open} busy={busy} save={save} />
                : <StartSeasonForm state={state} busy={busy} save={save} />}
              <RulesCard state={state} busy={busy} save={save} />
            </div>
            <ReportCard state={state} busy={busy} save={save} />
            <RecentGamesCard games={state.recent} busy={busy} save={save} />
            <PastSeasons seasons={state.seasons} currentId={showCurrent ? current.season_id : null} />
          </>
        )}
      </div>

      <section>
        <h2 className="text-xs font-bold text-text-muted uppercase tracking-wider mb-2">Other event tools</h2>
        <div className="grid grid-cols-1 sm:grid-cols-2 gap-3">
          {OTHER_TOOLS.map(({ to, label, blurb }) => (
            <Link key={to} to={to} className="block bg-bg-surface border border-border rounded-soft p-4 hover:border-accent-red/60 transition-colors">
              <span className="block font-semibold text-text-primary">{label}</span>
              <span className="block text-sm text-text-muted mt-0.5">{blurb}</span>
            </Link>
          ))}
        </div>
      </section>
    </div>
  )
}
