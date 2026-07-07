import { useState } from 'react'
import { Link } from 'react-router-dom'

const ELEMENT_IMG = '/static/images/elements/'
const ELEMENT_FILE = {
  Earth: 'earth.png',
  Fire: 'fire.png',
  Water: 'water.png',
  Air: 'wind.png',
}

function ElementIcons({ elements }) {
  if (!elements?.length) return '-'
  return (
    <span className="flex gap-0.5">
      {elements.map((el) => {
        const file = ELEMENT_FILE[el]
        if (!file) return <span key={el} className="text-xs">{el}</span>
        return <img key={el} src={`${ELEMENT_IMG}${file}`} alt={el} title={el} className="w-5 h-5" />
      })}
    </span>
  )
}

export default function MatchHistoryTable({ title, subtitle, matches, pagination, playerId, isOwner, perPage, perPageOptions, onPageChange, onPerPageChange, onEditDeck }) {
  const [noteModal, setNoteModal] = useState(null)

  if (!matches?.length) {
    return (
      <section>
        <h3 className="text-lg font-semibold text-text-primary mb-3">{title}</h3>
        <p className="text-text-muted text-sm py-4 text-center">No matches recorded.</p>
      </section>
    )
  }

  return (
    <section>
      <h3 className="text-lg font-semibold text-text-primary mb-1">{title}</h3>
      {subtitle && <p className="text-xs text-text-muted mb-3">{subtitle}</p>}
      <div className="overflow-x-auto">
        <table className="w-full text-sm" style={{ minWidth: isOwner ? 900 : 600 }}>
          <thead>
            <tr className="border-b border-border text-left">
              <th className="py-2 px-3 text-text-muted font-semibold">ID</th>
              <th className="py-2 px-3 text-text-muted font-semibold">Result</th>
              {isOwner && <th className="py-2 px-3 text-text-muted font-semibold">Avatar</th>}
              {isOwner && <th className="py-2 px-3 text-text-muted font-semibold">Elements</th>}
              <th className="py-2 px-3 text-text-muted font-semibold">Opponent</th>
              {isOwner && <th className="py-2 px-3 text-text-muted font-semibold">Opp. Avatar</th>}
              {isOwner && <th className="py-2 px-3 text-text-muted font-semibold">Opp. Elements</th>}
              <th className="py-2 px-3 text-text-muted font-semibold">ELO</th>
              <th className="py-2 px-3 text-text-muted font-semibold">Play/Draw</th>
              <th className="py-2 px-3 text-text-muted font-semibold">Time</th>
              <th className="py-2 px-3 text-text-muted font-semibold">Date</th>
              {isOwner && <th className="py-2 px-3 text-text-muted font-semibold">Notes</th>}
              {isOwner && <th className="py-2 px-3 text-text-muted font-semibold">Deck Link</th>}
              {isOwner && <th className="py-2 px-3 text-text-muted font-semibold">Snapshot</th>}
            </tr>
          </thead>
          <tbody>
            {matches.map((m) => {
              const isWin = m.result === 'Win'
              const deckUrl = m.player_deck_url && m.player_deck_url !== 'No URL provided' && m.player_deck_url !== 'Admin reported match'
                ? m.player_deck_url : null
              return (
                <tr key={m.match_id} className="border-b border-border/50 hover:bg-bg-surface/50">
                  <td className="py-2 px-3 text-text-muted">#{m.match_id}</td>
                  <td className="py-2 px-3">
                    <span className={`text-xs font-bold px-1.5 py-0.5 rounded ${isWin ? 'bg-accent-green/20 text-accent-green' : 'bg-accent-red/20 text-accent-red'}`}>
                      {m.result}
                    </span>
                  </td>
                  {isOwner && (
                    <td className="py-2 px-3 text-sm">
                      {m.player_avatar ? (
                        <Link to={`/avatar/${encodeURIComponent(m.player_avatar)}`} className="text-secondary hover:underline">
                          {m.player_avatar}
                        </Link>
                      ) : '-'}
                    </td>
                  )}
                  {isOwner && (
                    <td className="py-2 px-3">
                      <ElementIcons elements={m.deck_elements} />
                    </td>
                  )}
                  <td className="py-2 px-3">
                    <Link to={`/player/${m.opponent_id}`} className="text-secondary hover:underline">
                      {m.opponent}
                    </Link>
                  </td>
                  {isOwner && (
                    <td className="py-2 px-3 text-sm">
                      {m.opponent_avatar ? (
                        <Link to={`/avatar/${encodeURIComponent(m.opponent_avatar)}`} className="text-secondary hover:underline">
                          {m.opponent_avatar}
                        </Link>
                      ) : '-'}
                    </td>
                  )}
                  {isOwner && (
                    <td className="py-2 px-3">
                      <ElementIcons elements={m.opponent_elements} />
                    </td>
                  )}
                  <td className={`py-2 px-3 font-medium ${isWin ? 'text-accent-green' : 'text-accent-red'}`}>
                    {isWin ? '+' : ''}{m.elo_change}
                  </td>
                  <td className="py-2 px-3 text-text-muted">{m.first_player || '-'}</td>
                  <td className="py-2 px-3 text-text-muted">{m.match_time ? `${m.match_time} min` : '-'}</td>
                  <td className="py-2 px-3 text-text-muted whitespace-nowrap">{m.date ? new Date(m.date).toLocaleDateString() : '-'}</td>
                  {isOwner && (
                    <td className="py-2 px-3 text-text-muted max-w-[100px]">
                      {m.match_comment ? (
                        <button
                          onClick={() => setNoteModal({ matchId: m.match_id, comment: m.match_comment })}
                          className="text-left truncate block max-w-[100px] text-secondary hover:underline cursor-pointer bg-transparent border-none p-0 text-sm"
                          title="Click to view full note"
                        >
                          {m.match_comment.split(/\s+/).slice(0, 3).join(' ')}{m.match_comment.split(/\s+/).length > 3 ? '...' : ''}
                        </button>
                      ) : '-'}
                    </td>
                  )}
                  {isOwner && (
                    <td className="py-2 px-3">
                      <span className="flex items-center gap-1">
                        {deckUrl ? (
                          <a href={deckUrl} target="_blank" rel="noopener noreferrer" className="text-secondary hover:underline text-xs">
                            View
                          </a>
                        ) : '-'}
                        {onEditDeck && (
                          <button
                            onClick={() => onEditDeck(m.match_id, deckUrl || '')}
                            className="text-text-muted hover:text-secondary text-xs ml-1"
                            title="Edit deck link"
                          >
                            &#9998;
                          </button>
                        )}
                      </span>
                    </td>
                  )}
                  {isOwner && (
                    <td className="py-2 px-3">
                      {m.has_deck_json ? (
                        <Link
                          to={`/deck-snapshot/${m.match_id}/${playerId}`}
                          className="text-secondary hover:underline text-xs"
                        >
                          View
                        </Link>
                      ) : '-'}
                    </td>
                  )}
                </tr>
              )
            })}
          </tbody>
        </table>
      </div>

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
      {noteModal && (
        <div className="fixed inset-0 z-50 flex items-center justify-center bg-black/60" onClick={() => setNoteModal(null)}>
          <div className="bg-bg-surface border border-border rounded-lg shadow-xl max-w-md w-full mx-4 p-5" onClick={(e) => e.stopPropagation()}>
            <div className="flex items-center justify-between mb-3">
              <h4 className="text-sm font-semibold text-text-primary">Match #{noteModal.matchId} Notes</h4>
              <button onClick={() => setNoteModal(null)} className="text-text-muted hover:text-text-primary text-lg leading-none">&times;</button>
            </div>
            <p className="text-sm text-text-secondary whitespace-pre-wrap break-words">{noteModal.comment}</p>
          </div>
        </div>
      )}
    </section>
  )
}
