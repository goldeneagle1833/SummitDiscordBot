import { useState, useMemo } from 'react'

const inputClass = 'w-full px-3 py-1.5 text-sm bg-bg-primary border border-border rounded focus:border-secondary outline-none'

const roleColor = (color) => (color ? `#${color.toString(16).padStart(6, '0')}` : '#99aab5')

export const emojiUrl = (id, animated) =>
  `https://cdn.discordapp.com/emojis/${id}.${animated ? 'gif' : 'png'}?size=48`

/** Searchable list of the server's roles. Roles the bot can't hand out are hidden. */
export function RolePicker({ roles, usedRoleIds, value, onChange }) {
  const [query, setQuery] = useState('')
  const assignable = useMemo(() => roles.filter(r => r.assignable), [roles])
  const hidden = roles.length - assignable.length
  const matches = useMemo(() => {
    const q = query.trim().toLowerCase()
    return q ? assignable.filter(r => r.name.toLowerCase().includes(q)) : assignable
  }, [assignable, query])

  const selected = roles.find(r => r.role_id === value)

  return (
    <div className="space-y-2">
      {selected ? (
        <div className="flex items-center gap-2 px-3 py-1.5 text-sm bg-bg-primary border border-secondary rounded">
          <span className="w-3 h-3 rounded-full shrink-0" style={{ background: roleColor(selected.color) }} />
          <span className="text-text-primary truncate">{selected.name}</span>
          <button type="button" onClick={() => onChange(null)} className="ml-auto text-xs text-text-muted hover:text-text-primary">
            Change
          </button>
        </div>
      ) : (
        <>
          <input
            type="text"
            value={query}
            onChange={e => setQuery(e.target.value)}
            placeholder={`Search ${assignable.length} roles…`}
            className={inputClass}
          />
          <ul className="max-h-48 overflow-y-auto border border-border rounded divide-y divide-border/50 bg-bg-primary">
            {matches.length === 0 && (
              <li className="px-3 py-2 text-xs text-text-muted">No roles match.</li>
            )}
            {matches.map(r => {
              const used = usedRoleIds.has(r.role_id)
              return (
                <li key={r.role_id}>
                  <button
                    type="button"
                    disabled={used}
                    onClick={() => onChange(r)}
                    className="w-full flex items-center gap-2 px-3 py-1.5 text-sm text-left hover:bg-bg-elevated disabled:opacity-40 disabled:cursor-not-allowed"
                  >
                    <span className="w-3 h-3 rounded-full shrink-0" style={{ background: roleColor(r.color) }} />
                    <span className="truncate text-text-primary">{r.name}</span>
                    {used && <span className="ml-auto text-xs text-text-muted shrink-0">already on this message</span>}
                  </button>
                </li>
              )
            })}
          </ul>
          {hidden > 0 && (
            <p className="text-xs text-text-muted">
              {hidden} role{hidden !== 1 ? 's' : ''} hidden: the bot can't give roles that sit above its own role or belong to another bot.
            </p>
          )}
        </>
      )}
    </div>
  )
}

/** Grid of the server's custom emojis. */
export function ServerEmojiPicker({ emojis, value, onChange }) {
  const [query, setQuery] = useState('')
  const matches = useMemo(() => {
    const q = query.trim().toLowerCase()
    return q ? emojis.filter(e => e.name.toLowerCase().includes(q)) : emojis
  }, [emojis, query])

  if (emojis.length === 0) {
    return <p className="text-xs text-text-muted">This server has no custom emojis.</p>
  }

  return (
    <div className="space-y-2">
      <input
        type="text"
        value={query}
        onChange={e => setQuery(e.target.value)}
        placeholder={`Search ${emojis.length} server emojis…`}
        className={inputClass}
      />
      <div className="flex flex-wrap gap-1 max-h-32 overflow-y-auto p-1 border border-border rounded bg-bg-primary">
        {matches.map(e => (
          <button
            key={e.emoji_id}
            type="button"
            title={`:${e.name}:`}
            onClick={() => onChange(e)}
            className={`p-1 rounded hover:bg-bg-elevated ${value === e.emoji_id ? 'ring-2 ring-secondary' : ''}`}
          >
            <img src={emojiUrl(e.emoji_id, e.animated)} alt={e.name} className="w-7 h-7 object-contain" loading="lazy" />
          </button>
        ))}
      </div>
    </div>
  )
}
