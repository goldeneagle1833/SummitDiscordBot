import { useCallback, useEffect, useMemo, useState } from 'react'
import { Link } from 'react-router-dom'
import { useAuth } from '@/context/AuthContext'
import Spinner from '@/components/ui/Spinner'
import Avatar from '@/components/ui/Avatar'
import usePageTitle from '@/hooks/usePageTitle'
import HallMap from '@/components/finder/HallMap'
import FinderMapsAdmin from '@/components/finder/FinderMapsAdmin'
import {
  fmtHour, getFinderMaps, getMapPeople, getMyFinder, myFinderQrUrl, newFinderLink,
  timeAgo, updateMyFinder,
} from '@/api/eventFinder'

const AWAY_LABEL = 'Away from the hall'

function eventDays(map) {
  const fmt = (d) => new Date(`${d}T12:00:00`).toLocaleDateString(undefined, { month: 'short', day: 'numeric' })
  return map.start_date === map.end_date ? fmt(map.start_date) : `${fmt(map.start_date)} to ${fmt(map.end_date)}`
}

function windowNote(map, sharing) {
  if (!map) return 'Pick your event first.'
  const hours = `${fmtHour(map.daily_start)} to ${fmtHour(map.daily_end)}`
  if (!sharing) return `Off. Nobody can see your spot.`
  switch (map.reason) {
    case 'open':
      return `On. People with your link can see your spot until ${fmtHour(map.daily_end)}`
    case 'before':
      return `On. Your spot starts showing at ${fmtHour(map.daily_start)} on the first day (${eventDays(map)}).`
    case 'closed_today':
      return `On, but hidden right now. Spots only show ${hours} venue time.`
    case 'after':
      return 'The event is over, so your spot is hidden.'
    default:
      return ''
  }
}

// Find a player at an in-person event: share your own spot on the hall map,
// and see who else is sharing.
export default function FindPlayer() {
  const { user } = useAuth()
  usePageTitle('Find a player')
  const [maps, setMaps] = useState(null)
  const [mine, setMine] = useState(null)
  const [mapId, setMapId] = useState(null)
  const [people, setPeople] = useState([])
  const [error, setError] = useState(null)
  const [saving, setSaving] = useState(false)
  const [labelDraft, setLabelDraft] = useState('')
  const [noteDraft, setNoteDraft] = useState('')
  const [copied, setCopied] = useState(false)
  const [qrBust, setQrBust] = useState('1')

  const applyMine = useCallback((d) => {
    setMine(d)
    setMaps(d.maps)
    setLabelDraft(d.share.label || '')
    setNoteDraft(d.share.note || '')
    setMapId((cur) => d.share.map_id || cur || d.maps.find((m) => m.open)?.id || d.maps[0]?.id || null)
  }, [])

  const loadAll = useCallback(() => {
    if (user) {
      return getMyFinder().then(applyMine).catch((e) => setError(e.message))
    }
    return getFinderMaps()
      .then((d) => {
        setMaps(d.maps)
        setMapId((cur) => cur || d.maps.find((m) => m.open)?.id || d.maps[0]?.id || null)
      })
      .catch((e) => setError(e.message))
  }, [user, applyMine])

  useEffect(() => {
    if (user === null) return // still checking login
    loadAll()
  }, [user, loadAll])

  const loadPeople = useCallback(() => {
    if (!mapId) return
    getMapPeople(mapId).then((d) => setPeople(d.people)).catch(() => setPeople([]))
  }, [mapId])

  useEffect(() => {
    loadPeople()
    const id = setInterval(() => document.visibilityState === 'visible' && loadPeople(), 60 * 1000)
    return () => clearInterval(id)
  }, [loadPeople])

  const map = useMemo(() => maps?.find((m) => m.id === mapId) || null, [maps, mapId])
  const share = mine?.share

  const save = async (fields) => {
    setSaving(true)
    setError(null)
    try {
      applyMine(await updateMyFinder(fields))
      loadPeople()
    } catch (e) {
      setError(e.message)
    } finally {
      setSaving(false)
    }
  }

  const copyLink = async () => {
    try {
      await navigator.clipboard.writeText(share.url)
      setCopied(true)
      setTimeout(() => setCopied(false), 2000)
    } catch {
      window.prompt('Copy your link', share.url)
    }
  }

  const resetLink = async () => {
    if (!window.confirm('Make a new link? Your old link and QR code will stop working.')) return
    try {
      applyMine(await newFinderLink())
      setQrBust(String(Date.now()))
    } catch (e) {
      setError(e.message)
    }
  }

  if (maps === null && !error) return <Spinner className="py-20" />

  const onThisMap = share && share.map_id === mapId
  const myPin = onThisMap && share.x != null ? [{ x: share.x, y: share.y, avatar: null, name: 'You', key: 'me' }] : []
  const card = 'bg-bg-surface border border-border rounded-lg p-4 sm:p-5'
  const chip = 'px-3 py-2 rounded-full border text-sm transition-colors'

  return (
    <div className="max-w-4xl mx-auto space-y-5">
      <div>
        <h1 className="text-3xl font-display text-secondary">Find a player</h1>
        <p className="text-text-muted mt-1">
          At an in-person event, tap where you are on the hall map so friends can find you.
          Your spot only shows during event hours, and you can switch it off any time.
        </p>
      </div>

      {error && <p className="text-accent-red text-sm">{error}</p>}

      {maps?.length > 1 && (
        <div className="flex flex-wrap gap-2">
          {maps.map((m) => (
            <button
              key={m.id}
              type="button"
              onClick={() => setMapId(m.id)}
              className={`${chip} ${m.id === mapId ? 'border-secondary text-secondary' : 'border-border text-text-muted hover:text-text'}`}
            >
              {m.name} <span className="text-xs opacity-75">· {eventDays(m)}</span>
            </button>
          ))}
        </div>
      )}

      {!maps?.length && (
        <div className={card}>
          <p className="text-text-muted">No upcoming events have a hall map yet.</p>
        </div>
      )}

      {/* Your spot */}
      {map && user && share && (
        <section className={card}>
          <div className="flex flex-wrap items-start justify-between gap-3">
            <div>
              <h2 className="text-xl font-display text-secondary">Your spot at {map.name}</h2>
              <p className="text-sm text-text-muted mt-0.5">{windowNote(map, onThisMap && share.sharing)}</p>
            </div>
            <label className="flex items-center gap-3 cursor-pointer">
              <span className="text-sm text-text">Share my spot</span>
              <input
                type="checkbox"
                className="sr-only peer"
                checked={!!(onThisMap && share.sharing)}
                disabled={saving}
                onChange={(e) => save({ map_id: mapId, sharing: e.target.checked })}
              />
              <span className="relative w-12 h-7 rounded-full bg-bg-elevated border border-border peer-checked:bg-accent-green transition-colors after:content-[''] after:absolute after:top-0.5 after:left-0.5 after:h-5 after:w-5 after:rounded-full after:bg-white after:transition-transform peer-checked:after:translate-x-5" />
            </label>
          </div>

          {onThisMap && share.sharing && (
            <>
              {map.spots?.length > 0 && (
                <div className="mt-4">
                  <p className="text-sm text-text-muted mb-2">Quick spots</p>
                  <div className="flex flex-wrap gap-2">
                    {map.spots.map((s) => (
                      <button
                        key={s.label}
                        type="button"
                        disabled={saving}
                        onClick={() => save({ label: s.label, x: s.x, y: s.y })}
                        className={`${chip} ${share.label === s.label ? 'border-secondary text-secondary bg-secondary/10' : 'border-border text-text hover:border-primary'}`}
                      >
                        {s.label}
                      </button>
                    ))}
                    <button
                      type="button"
                      disabled={saving}
                      onClick={() => save({ label: AWAY_LABEL, x: null, y: null })}
                      className={`${chip} ${share.label === AWAY_LABEL ? 'border-secondary text-secondary bg-secondary/10' : 'border-border text-text-muted hover:text-text'}`}
                    >
                      {AWAY_LABEL}
                    </button>
                  </div>
                </div>
              )}

              <p className="text-sm text-text-muted mt-4 mb-2">Or tap the map where you are</p>
              <HallMap
                map={map}
                spots={map.spots}
                pins={myPin}
                onPick={(x, y) => save({ x, y, label: null })}
                onPickSpot={(s) => save({ label: s.label, x: s.x, y: s.y })}
              />

              <form
                className="grid sm:grid-cols-[1fr_1fr_auto] gap-2 mt-3"
                onSubmit={(e) => {
                  e.preventDefault()
                  save({ label: labelDraft, note: noteDraft })
                }}
              >
                <input
                  value={labelDraft}
                  onChange={(e) => setLabelDraft(e.target.value)}
                  maxLength={60}
                  placeholder="Where? e.g. Table 42"
                  className="bg-bg-elevated border border-border rounded px-3 py-2 text-text"
                />
                <input
                  value={noteDraft}
                  onChange={(e) => setNoteDraft(e.target.value)}
                  maxLength={140}
                  placeholder="Note (optional) e.g. Black Summit shirt"
                  className="bg-bg-elevated border border-border rounded px-3 py-2 text-text"
                />
                <button type="submit" disabled={saving} className="px-4 py-2 rounded bg-primary text-bg-dark font-semibold disabled:opacity-50">
                  Save
                </button>
              </form>
              {share.updated_at && (
                <p className="text-xs text-text-muted mt-2">Last updated {timeAgo(share.updated_at)}</p>
              )}

              <label className="flex items-start gap-2 mt-4 text-sm cursor-pointer">
                <input
                  type="checkbox"
                  className="mt-1"
                  checked={!!share.listed}
                  disabled={saving}
                  onChange={(e) => save({ listed: e.target.checked })}
                />
                <span>
                  <span className="text-text">Show me on the event list below</span>
                  <span className="block text-text-muted">Off means only people with your link or QR code can find you.</span>
                </span>
              </label>
            </>
          )}

          {/* Link + QR */}
          <div className="mt-5 pt-4 border-t border-border flex flex-col sm:flex-row gap-4 sm:items-center">
            <img
              src={myFinderQrUrl(qrBust + share.token)}
              alt="QR code for your link"
              className="w-32 h-32 bg-white rounded p-1 self-center sm:self-auto"
            />
            <div className="min-w-0 flex-1">
              <p className="text-sm text-text-muted">Your link (print the QR code or put it on your badge)</p>
              <p className="font-mono text-sm text-text break-all mt-1">{share.url}</p>
              <div className="flex flex-wrap gap-3 mt-2 text-sm">
                <button type="button" onClick={copyLink} className="text-primary hover:underline">{copied ? 'Copied' : 'Copy link'}</button>
                <a href={myFinderQrUrl(qrBust + share.token, true)} className="text-primary hover:underline">Download QR code</a>
                <Link to={`/find/${share.token}`} className="text-primary hover:underline">See what others see</Link>
                <button type="button" onClick={resetLink} className="text-text-muted hover:text-text">New link</button>
              </div>
            </div>
          </div>
        </section>
      )}

      {map && !user && (
        <div className={card}>
          <p className="text-text">
            <Link to={`/login?next=${encodeURIComponent('/find')}`} className="text-primary hover:underline">Log in</Link>
            {' '}to share your own spot at {map.name}.
          </p>
        </div>
      )}

      {/* Who's sharing */}
      {map && (
        <section className={card}>
          <h2 className="text-xl font-display text-secondary">Sharing now at {map.name}</h2>
          {!map.open ? (
            <p className="text-text-muted text-sm mt-1">
              {map.reason === 'before' && `Spots show from ${fmtHour(map.daily_start)} to ${fmtHour(map.daily_end)}, ${eventDays(map)}.`}
              {map.reason === 'closed_today' && `Closed for the night. Spots show ${fmtHour(map.daily_start)} to ${fmtHour(map.daily_end)}.`}
              {map.reason === 'after' && 'This event is over.'}
            </p>
          ) : people.length === 0 ? (
            <p className="text-text-muted text-sm mt-1">Nobody on the list yet. People can also share by link only.</p>
          ) : (
            <>
              <ul className="divide-y divide-border mt-2">
                {people.map((p) => (
                  <li key={p.token}>
                    <Link to={`/find/${p.token}`} className="flex items-center gap-3 py-2.5 hover:bg-bg-elevated rounded px-1">
                      <Avatar src={p.avatar} alt={p.username} size="sm" />
                      <div className="min-w-0 flex-1">
                        <p className="text-text truncate">{p.username}</p>
                        <p className="text-sm text-text-muted truncate">{p.label || 'On the map'}</p>
                      </div>
                      <span className="text-xs text-text-muted whitespace-nowrap">{timeAgo(p.updated_at)}</span>
                    </Link>
                  </li>
                ))}
              </ul>
              <HallMap
                map={map}
                className="mt-3"
                pins={people.map((p) => ({ x: p.x, y: p.y, avatar: p.avatar, name: p.username, key: p.token }))}
              />
            </>
          )}
        </section>
      )}

      {mine?.can_manage_maps && <FinderMapsAdmin maps={maps || []} onChange={loadAll} />}
    </div>
  )
}
