import { useState } from 'react'
import { Link } from 'react-router-dom'
import { editMatchComment, editMatchTime, requestMatchCorrection } from '@/api/games'
import { HiddenChange } from '@/components/common/Provisional'
import { isHidden, isNum } from '@/utils/provisional'
import useMediaQuery from '@/hooks/useMediaQuery'

// Bot matches from this season can be corrected; archived ones show as rowid + this
const ARCHIVED_MATCH_OFFSET = 1000000000
const canCorrect = (m) => m.match_source === 'bot' && Number(m.match_id) > 0 && Number(m.match_id) < ARCHIVED_MATCH_OFFSET

const ELEMENT_IMG = '/static/images/elements/'
const ELEMENT_FILE = {
  Earth: 'earth.png',
  Fire: 'fire.png',
  Water: 'water.png',
  Air: 'wind.png',
}

function ElementIcons({ elements, small = false }) {
  if (!elements?.length) return '-'
  return (
    <span className="inline-flex gap-0.5 align-middle">
      {elements.map((el) => {
        const file = ELEMENT_FILE[el]
        if (!file) return <span key={el} className="text-xs">{el}</span>
        return <img key={el} src={`${ELEMENT_IMG}${file}`} alt={el} title={el} className={small ? 'w-4 h-4' : 'w-5 h-5'} />
      })}
    </span>
  )
}

export default function MatchHistoryTable({ title, subtitle, matches, pagination, playerId, isOwner, profileVisibility, perPage, perPageOptions, onPageChange, onPerPageChange, onEditDeck, onMatchUpdate, emptyText = 'No matches recorded.' }) {
  const showDeckUrls = isOwner || profileVisibility?.deck_urls
  const showSnapshots = isOwner || profileVisibility?.deck_snapshots
  const [noteModal, setNoteModal] = useState(null)
  const [editingNote, setEditingNote] = useState(false)
  const [editText, setEditText] = useState('')
  const [editSaving, setEditSaving] = useState(false)
  const [editError, setEditError] = useState(null)
  const [editingTimeId, setEditingTimeId] = useState(null)
  const [editTimeValue, setEditTimeValue] = useState('')
  const [editTimeSaving, setEditTimeSaving] = useState(false)
  const [correctModal, setCorrectModal] = useState(null)
  const [correctSending, setCorrectSending] = useState(false)
  const [correctError, setCorrectError] = useState(null)
  const [correctionsSent, setCorrectionsSent] = useState({})
  // Below Tailwind's lg breakpoint (phones, small tablets) the table becomes a list of cards
  const isPhone = useMediaQuery('(max-width: 1023px)')

  if (!matches?.length) {
    return (
      <section>
        <h3 className="text-lg font-semibold text-text-primary mb-3">{title}</h3>
        <p className="text-text-muted text-sm py-4 text-center">{emptyText}</p>
      </section>
    )
  }

  const th = 'py-2 px-1.5 text-text-muted font-semibold text-xs'
  const td = 'py-1.5 px-1.5 align-middle'
  const shortDate = (d) => (d ? new Date(d).toLocaleDateString(undefined, { month: 'numeric', day: 'numeric', year: '2-digit' }) : '-')
  const deckUrlOf = (m) => (m.player_deck_url && m.player_deck_url !== 'No URL provided' && m.player_deck_url !== 'Admin reported match'
    ? m.player_deck_url : null)

  const resultBadge = (m) => (
    <span className={`text-xs font-bold px-1.5 py-0.5 rounded ${m.result === 'Win' ? 'bg-accent-green/20 text-accent-green' : 'bg-accent-red/20 text-accent-red'}`}>
      {m.result}
    </span>
  )
  const matchId = (m) => (
    <span className="block max-w-[4.5rem] truncate text-[11px] text-text-muted" title={`#${m.match_id}`}>#{m.match_id}</span>
  )
  const typeLabel = (m) => (
    m.match_type === 'points' ? (
      <span className="text-xs font-medium px-1.5 py-0.5 rounded bg-purple-500/20 text-purple-400">Omens</span>
    ) : m.match_type === 'casual' || m.match_type === 'testing' ? (
      // 'testing' is the bot's internal name for casual games
      <span className="text-xs text-text-muted">Casual</span>
    ) : (
      <span className="text-xs text-text-muted">Ranked</span>
    )
  )
  const voiceIcon = (m) => (
    m.voice === true ? (
      <span role="img" aria-label="Voice" title="Voice">🔊</span>
    ) : m.voice === false ? (
      <span role="img" aria-label="No voice" title="No voice">🔇</span>
    ) : (
      <span className="text-text-muted">-</span>
    )
  )
  const avatarLink = (name) => (
    name ? (
      <Link to={`/avatar/${encodeURIComponent(name)}`} className="text-secondary hover:underline">{name}</Link>
    ) : <span className="text-text-muted">-</span>
  )
  const ratingChange = (m) => (
    isHidden(m, 'elo_change') ? <HiddenChange /> : (
      <span className={m.result === 'Win' ? 'text-accent-green' : 'text-accent-red'}>
        {isNum(m.elo_change) ? <>{m.result === 'Win' ? '+' : ''}{m.elo_change}</> : '-'}
      </span>
    )
  )
  const replayLink = (m) => (
    m.replay_url ? (
      <a href={m.replay_url} target="_blank" rel="noopener noreferrer" className="text-secondary hover:underline text-xs">Watch</a>
    ) : <span className="text-text-muted">-</span>
  )
  const matchTime = (m) => (
    isOwner && editingTimeId === m.match_id ? (
      <form
        className="flex items-center gap-1"
        onSubmit={async (e) => {
          e.preventDefault()
          const val = parseInt(editTimeValue, 10)
          if (isNaN(val) || val < 0 || val > 999) return
          setEditTimeSaving(true)
          try {
            await editMatchTime(m.match_id, m.match_source, val)
            onMatchUpdate?.()
          } catch { /* ignore */ }
          setEditTimeSaving(false)
          setEditingTimeId(null)
        }}
      >
        <input
          type="number"
          min="0"
          max="999"
          value={editTimeValue}
          onChange={(e) => setEditTimeValue(e.target.value)}
          className="w-14 text-xs bg-bg-raised border border-border rounded px-1 py-0.5 text-text-primary"
          autoFocus
          disabled={editTimeSaving}
          onKeyDown={(e) => { if (e.key === 'Escape') setEditingTimeId(null) }}
        />
        <button type="submit" disabled={editTimeSaving} className="text-xs text-accent-green hover:opacity-80">&#10003;</button>
        <button type="button" onClick={() => setEditingTimeId(null)} className="text-xs text-text-muted hover:text-text-primary">&times;</button>
      </form>
    ) : isOwner ? (
      <button
        onClick={() => { setEditingTimeId(m.match_id); setEditTimeValue(m.match_time || '') }}
        className="text-text-muted hover:text-secondary bg-transparent border-none p-0 cursor-pointer text-xs whitespace-nowrap"
        title="Click to edit match time"
      >
        {m.match_time ? `${m.match_time} min` : '+ Time'}
      </button>
    ) : (
      <span className="text-xs whitespace-nowrap">{m.match_time ? `${m.match_time} min` : '-'}</span>
    )
  )
  const deckLink = (m) => {
    const deckUrl = deckUrlOf(m)
    return (
      <span className="inline-flex items-center gap-1 whitespace-nowrap">
        {deckUrl ? (
          <a href={deckUrl} target="_blank" rel="noopener noreferrer" className="text-secondary hover:underline text-xs">Deck</a>
        ) : <span className="text-text-muted text-xs">No deck</span>}
        {onEditDeck && (
          <button
            onClick={() => onEditDeck(m.match_id, deckUrl || '')}
            className="text-text-muted hover:text-secondary text-xs"
            title="Edit deck link"
            aria-label="Edit deck link"
          >
            &#9998;
          </button>
        )}
      </span>
    )
  }
  const snapshotLink = (m) => (
    m.has_deck_json ? (
      <Link to={`/deck-snapshot/${m.match_id}/${playerId}`} className="text-secondary hover:underline text-xs">Snapshot</Link>
    ) : null
  )
  const noteButton = (m) => (
    m.match_comment ? (
      <button
        onClick={() => { setNoteModal({ matchId: m.match_id, comment: m.match_comment, matchSource: m.match_source }); setEditingNote(false); setEditError(null) }}
        className="text-left truncate block max-w-[90px] text-secondary hover:underline cursor-pointer bg-transparent border-none p-0 text-xs"
        title="Click to view/edit note"
      >
        {m.match_comment.split(/\s+/).slice(0, 3).join(' ')}{m.match_comment.split(/\s+/).length > 3 ? '...' : ''}
      </button>
    ) : (
      <button
        onClick={() => { setNoteModal({ matchId: m.match_id, comment: '', matchSource: m.match_source }); setEditingNote(true); setEditText(''); setEditError(null) }}
        className="text-text-muted hover:text-secondary text-xs bg-transparent border-none p-0 cursor-pointer whitespace-nowrap"
        title="Add a note"
      >
        + Note
      </button>
    )
  )
  const changeResult = (m) => (
    correctionsSent[m.match_id] ? (
      <span className="text-xs text-text-muted" title="Waiting for your opponent to confirm">Sent</span>
    ) : canCorrect(m) ? (
      <button
        onClick={() => { setCorrectModal(m); setCorrectError(null) }}
        className="text-xs px-1.5 py-0.5 rounded border border-border text-text-muted hover:text-secondary hover:border-secondary/50 bg-transparent cursor-pointer whitespace-nowrap"
        title="Ask your opponent to switch who won"
      >
        Change Result
      </button>
    ) : null
  )

  return (
    <section>
      <h3 className="text-lg font-semibold text-text-primary mb-1">{title}</h3>
      {subtitle && <p className="text-xs text-text-muted mb-3">{subtitle}</p>}
      {isPhone ? (
        // Phone: one card per match, so nothing needs sideways scrolling
        <ul className="divide-y divide-border/50 border-y border-border/50" data-testid="match-cards">
          {matches.map((m) => {
            const snap = showSnapshots && snapshotLink(m)
            const change = isOwner && changeResult(m)
            return (
              <li key={m.match_id} className="py-2.5 space-y-1 text-sm">
                <div className="flex items-center gap-2">
                  {resultBadge(m)}
                  {typeLabel(m)}
                  {voiceIcon(m)}
                  <span className="ml-auto font-medium">{ratingChange(m)}</span>
                </div>
                <div className="flex flex-wrap items-center gap-x-1.5 gap-y-0.5">
                  <span className="text-text-muted text-xs">vs</span>
                  <Link to={`/player/${m.opponent_id}`} className="text-secondary hover:underline font-medium">{m.opponent}</Link>
                  {isOwner && m.opponent_avatar && <span className="text-xs">({avatarLink(m.opponent_avatar)})</span>}
                  {isOwner && <ElementIcons elements={m.opponent_elements} small />}
                </div>
                {isOwner && (
                  <div className="flex flex-wrap items-center gap-x-1.5 text-xs">
                    <span className="text-text-muted">You:</span>
                    {avatarLink(m.player_avatar)}
                    <ElementIcons elements={m.deck_elements} small />
                  </div>
                )}
                <div className="flex flex-wrap items-center gap-x-3 gap-y-1 text-xs text-text-muted">
                  <span>{shortDate(m.date)}</span>
                  {matchTime(m)}
                  {m.first_player && <span>{m.first_player}</span>}
                  {m.replay_url && replayLink(m)}
                  <span>#{m.match_id}</span>
                </div>
                {(showDeckUrls || snap || isOwner) && (
                  <div className="flex flex-wrap items-center gap-x-3 gap-y-1">
                    {showDeckUrls && deckLink(m)}
                    {snap}
                    {isOwner && noteButton(m)}
                    {change}
                  </div>
                )}
              </li>
            )
          })}
        </ul>
      ) : (
        <div className="overflow-x-auto">
          <table className="w-full text-sm">
            <thead>
              <tr className="border-b border-border text-left">
                <th className={th}>Result</th>
                <th className={th}>Type</th>
                {isOwner && <th className={th}>Avatar</th>}
                <th className={th}>Opponent</th>
                <th className={th}>Rating</th>
                <th className={th}>Replay</th>
                <th className={th}>Play/Draw</th>
                <th className={th}>Date</th>
                {(showDeckUrls || showSnapshots) && <th className={th}>Deck</th>}
                {isOwner && <th className={th}>Notes</th>}
                {isOwner && <th className={`${th} whitespace-nowrap`}>Change Result</th>}
              </tr>
            </thead>
            <tbody>
              {matches.map((m) => (
                <tr key={m.match_id} className="border-b border-border/50 hover:bg-bg-surface/50">
                  <td className={td}>
                    {resultBadge(m)}
                    {matchId(m)}
                  </td>
                  <td className={td}>
                    <span className="inline-flex items-center gap-1 whitespace-nowrap">
                      {typeLabel(m)}
                      {voiceIcon(m)}
                    </span>
                  </td>
                  {isOwner && (
                    <td className={`${td} text-xs`}>
                      <div>{avatarLink(m.player_avatar)}</div>
                      <ElementIcons elements={m.deck_elements} small />
                    </td>
                  )}
                  <td className={td}>
                    <Link to={`/player/${m.opponent_id}`} className="text-secondary hover:underline break-words">
                      {m.opponent}
                    </Link>
                    {isOwner && (
                      <div className="flex flex-wrap items-center gap-x-1 text-xs">
                        {m.opponent_avatar && avatarLink(m.opponent_avatar)}
                        <ElementIcons elements={m.opponent_elements} small />
                      </div>
                    )}
                  </td>
                  <td className={`${td} font-medium`}>{ratingChange(m)}</td>
                  <td className={`${td} text-text-muted`}>{replayLink(m)}</td>
                  <td className={`${td} text-text-muted text-xs`}>{m.first_player || '-'}</td>
                  <td className={`${td} text-text-muted`}>
                    <div className="text-xs whitespace-nowrap">{shortDate(m.date)}</div>
                    {matchTime(m)}
                  </td>
                  {(showDeckUrls || showSnapshots) && (
                    <td className={td}>
                      {showDeckUrls && <div>{deckLink(m)}</div>}
                      {showSnapshots && <div>{snapshotLink(m) || (!showDeckUrls && <span className="text-text-muted">-</span>)}</div>}
                    </td>
                  )}
                  {isOwner && <td className={`${td} text-text-muted`}>{noteButton(m)}</td>}
                  {isOwner && <td className={td}>{changeResult(m) || <span className="text-text-muted">-</span>}</td>}
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      )}

      {perPageOptions && onPerPageChange && (
        <div className="flex items-center gap-2 mt-3 text-xs text-text-muted">
          <span>Show:</span>
          {perPageOptions.map((n) => (
            <button
              key={n}
              onClick={() => onPerPageChange(n)}
              className={`px-2 py-1 rounded border ${perPage === n ? 'border-secondary text-secondary' : 'border-border hover:border-secondary'}`}
            >
              {n}
            </button>
          ))}
        </div>
      )}

      {pagination && pagination.total_pages > 1 && (
        <div className="flex items-center justify-center gap-3 mt-4">
          <button
            disabled={!pagination.has_previous}
            onClick={() => onPageChange(1)}
            className="px-3 py-1.5 text-sm bg-bg-raised border border-border rounded hover:border-secondary disabled:opacity-40 disabled:cursor-not-allowed"
          >
            First
          </button>
          <button
            disabled={!pagination.has_previous}
            onClick={() => onPageChange(pagination.current_page - 1)}
            className="px-3 py-1.5 text-sm bg-bg-raised border border-border rounded hover:border-secondary disabled:opacity-40 disabled:cursor-not-allowed"
          >
            &larr; Prev
          </button>
          <span className="text-sm font-medium">
            Page {pagination.current_page} of {pagination.total_pages}
          </span>
          <button
            disabled={!pagination.has_next}
            onClick={() => onPageChange(pagination.current_page + 1)}
            className="px-3 py-1.5 text-sm bg-bg-raised border border-border rounded hover:border-secondary disabled:opacity-40 disabled:cursor-not-allowed"
          >
            Next &rarr;
          </button>
          <button
            disabled={!pagination.has_next}
            onClick={() => onPageChange(pagination.total_pages)}
            className="px-3 py-1.5 text-sm bg-bg-raised border border-border rounded hover:border-secondary disabled:opacity-40 disabled:cursor-not-allowed"
          >
            Last
          </button>
          <span className="text-xs text-text-muted ml-2">
            {((pagination.current_page - 1) * pagination.per_page) + 1}-{Math.min(pagination.current_page * pagination.per_page, pagination.total_matches)} of {pagination.total_matches}
          </span>
        </div>
      )}
      {correctModal && (
        <div className="fixed inset-0 z-50 flex items-center justify-center bg-black/60" onClick={() => !correctSending && setCorrectModal(null)}>
          <div role="dialog" aria-label="Change result" className="bg-bg-surface border border-border rounded-lg shadow-xl max-w-md w-full mx-4 p-5" onClick={(e) => e.stopPropagation()}>
            <div className="flex items-center justify-between mb-3">
              <h4 className="text-sm font-semibold text-text-primary">Change Result: Match #{correctModal.match_id}</h4>
              <button onClick={() => setCorrectModal(null)} disabled={correctSending} className="text-text-muted hover:text-text-primary text-lg leading-none">&times;</button>
            </div>
            {correctModal.sentMessage ? (
              <>
                <p className="text-sm text-text-secondary">{correctModal.sentMessage}</p>
                <div className="flex justify-end mt-4">
                  <button onClick={() => setCorrectModal(null)} className="px-3 py-1 text-xs rounded bg-secondary text-black hover:opacity-90">OK</button>
                </div>
              </>
            ) : (
              <>
                <p className="text-sm text-text-secondary">
                  This is recorded as a <strong>{correctModal.result === 'Win' ? 'win' : 'loss'}</strong> for you against <strong>{correctModal.opponent || 'your opponent'}</strong>.
                  {' '}Switch it to a <strong>{correctModal.result === 'Win' ? 'loss' : 'win'}</strong>?
                </p>
                <p className="text-xs text-text-muted mt-2">
                  {correctModal.opponent || 'Your opponent'} gets a Discord DM to confirm. Nothing changes until they confirm. Then ratings are recalculated.
                </p>
                {correctError && <p className="text-xs text-accent-red mt-2">{correctError}</p>}
                <div className="flex justify-end gap-2 mt-4">
                  <button
                    onClick={() => setCorrectModal(null)}
                    disabled={correctSending}
                    className="px-3 py-1 text-xs rounded border border-border text-text-muted hover:text-text-primary"
                  >
                    Cancel
                  </button>
                  <button
                    onClick={async () => {
                      setCorrectSending(true)
                      setCorrectError(null)
                      try {
                        const res = await requestMatchCorrection(correctModal.match_id)
                        setCorrectionsSent((s) => ({ ...s, [correctModal.match_id]: true }))
                        setCorrectModal({ ...correctModal, sentMessage: res?.message || 'Sent. The result switches once your opponent confirms.' })
                      } catch (err) {
                        setCorrectError(err.message || 'Could not send the request')
                      } finally {
                        setCorrectSending(false)
                      }
                    }}
                    disabled={correctSending}
                    className="px-3 py-1 text-xs rounded bg-secondary text-black hover:opacity-90 disabled:opacity-50"
                  >
                    {correctSending ? 'Sending...' : 'Send request'}
                  </button>
                </div>
              </>
            )}
          </div>
        </div>
      )}
      {noteModal && (
        <div className="fixed inset-0 z-50 flex items-center justify-center bg-black/60" onClick={() => setNoteModal(null)}>
          <div className="bg-bg-surface border border-border rounded-lg shadow-xl max-w-md w-full mx-4 p-5" onClick={(e) => e.stopPropagation()}>
            <div className="flex items-center justify-between mb-3">
              <h4 className="text-sm font-semibold text-text-primary">Match #{noteModal.matchId} Notes</h4>
              <button onClick={() => setNoteModal(null)} className="text-text-muted hover:text-text-primary text-lg leading-none">&times;</button>
            </div>
            {editingNote ? (
              <>
                <textarea
                  value={editText}
                  onChange={(e) => setEditText(e.target.value)}
                  maxLength={500}
                  rows={4}
                  className="w-full text-sm bg-bg-raised border border-border rounded p-2 text-text-primary resize-y"
                  placeholder="Enter your match notes..."
                />
                <div className="flex items-center justify-between mt-2">
                  <span className="text-xs text-text-muted">{editText.length}/500</span>
                  <div className="flex gap-2">
                    <button
                      onClick={() => { setEditingNote(false); setEditError(null) }}
                      className="px-3 py-1 text-xs rounded border border-border text-text-muted hover:text-text-primary"
                    >
                      Cancel
                    </button>
                    <button
                      onClick={async () => {
                        setEditSaving(true)
                        setEditError(null)
                        try {
                          await editMatchComment(noteModal.matchId, noteModal.matchSource, editText)
                          setNoteModal({ ...noteModal, comment: editText })
                          setEditingNote(false)
                          onMatchUpdate?.()
                        } catch (err) {
                          setEditError(err.message || 'Failed to save')
                        } finally {
                          setEditSaving(false)
                        }
                      }}
                      disabled={editSaving}
                      className="px-3 py-1 text-xs rounded bg-secondary text-black hover:opacity-90 disabled:opacity-50"
                    >
                      {editSaving ? 'Saving...' : 'Save'}
                    </button>
                  </div>
                </div>
                {editError && <p className="text-xs text-accent-red mt-1">{editError}</p>}
              </>
            ) : (
              <>
                <p className="text-sm text-text-secondary whitespace-pre-wrap break-words">{noteModal.comment || <span className="text-text-muted italic">No notes</span>}</p>
                <div className="flex justify-end mt-3">
                  <button
                    onClick={() => { setEditingNote(true); setEditText(noteModal.comment || ''); setEditError(null) }}
                    className="px-3 py-1 text-xs rounded border border-border text-text-muted hover:text-text-primary hover:border-secondary/50"
                  >
                    Edit
                  </button>
                </div>
              </>
            )}
          </div>
        </div>
      )}
    </section>
  )
}
