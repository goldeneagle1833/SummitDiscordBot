import { useState } from 'react'
import { Link, useNavigate } from 'react-router-dom'

/**
 * The bracket to open on: the newest one being played, else the most recently
 * finished one, else whatever is first. Lists come newest first.
 */
export function pickActiveBracket(brackets = []) {
  return (
    brackets.find((b) => b.status === 'published') ||
    brackets.find((b) => b.status === 'complete') ||
    brackets[0] ||
    null
  )
}

const setKey = (bracket) => (bracket?.set_name || '').trim().toLowerCase()

/**
 * Brackets grouped by card set, in the order each set was last played (lists
 * come newest first). Brackets with no set land in "Other". Groups come from
 * the data, so a new set shows up as soon as a bracket is tagged with it.
 */
export function groupBrackets(brackets = []) {
  const groups = new Map()
  for (const bracket of brackets) {
    const key = setKey(bracket)
    if (!groups.has(key)) {
      groups.set(key, { key, label: bracket.set_name?.trim() || 'Other', brackets: [] })
    }
    groups.get(key).brackets.push(bracket)
  }
  // "Other" goes last whatever its age, so the named sets lead.
  const ordered = [...groups.values()]
  return [...ordered.filter((g) => g.key), ...ordered.filter((g) => !g.key)]
}

function statusLabel(status) {
  if (status === 'published') return 'Live'
  if (status === 'draft') return 'Draft'
  return 'Final'
}

const CHIP =
  'px-3 py-1 text-[11px] font-semibold uppercase tracking-wider border rounded-sm transition-colors'

/**
 * Across the top of the bracket page: a filter by card set, then a tab per
 * bracket in that set, so a viewer can flip from the live top cut to an
 * older one without a detour through a list.
 */
export default function BracketSwitcher({ brackets, currentSlug }) {
  const navigate = useNavigate()
  const [showAll, setShowAll] = useState(false)

  if (!brackets || brackets.length < 2) return null

  const groups = groupBrackets(brackets)
  const current = brackets.find((b) => b.slug === currentSlug)
  const currentKey = setKey(current)
  const hasSets = groups.some((g) => g.key)
  const selectedKey = showAll || !hasSets ? null : currentKey
  const visible = selectedKey === null
    ? brackets
    : groups.find((g) => g.key === selectedKey)?.brackets || brackets

  function chooseSet(group) {
    setShowAll(false)
    if (group.key === currentKey) return
    const target = pickActiveBracket(group.brackets)
    if (target) navigate(`/brackets/${target.slug}`)
  }

  return (
    <div className="space-y-3">
      {hasSets && (
        <div role="group" aria-label="Filter by set" className="flex flex-wrap items-center gap-2">
          <span className="text-[11px] font-semibold uppercase tracking-wider text-text-muted mr-1">
            Set
          </span>
          {groups.map((group) => {
            const selected = selectedKey === group.key
            return (
              <button
                key={group.key || 'other'}
                type="button"
                aria-pressed={selected}
                onClick={() => chooseSet(group)}
                className={`${CHIP} ${
                  selected
                    ? 'border-secondary bg-secondary/10 text-secondary'
                    : 'border-border text-text-muted hover:text-text-primary hover:border-text-muted'
                }`}
              >
                {group.label}
                <span className="ml-1.5 font-mono font-normal opacity-70">{group.brackets.length}</span>
              </button>
            )
          })}
          <button
            type="button"
            aria-pressed={selectedKey === null}
            onClick={() => setShowAll(true)}
            className={`${CHIP} ${
              selectedKey === null
                ? 'border-secondary bg-secondary/10 text-secondary'
                : 'border-border text-text-muted hover:text-text-primary hover:border-text-muted'
            }`}
          >
            All
          </button>
        </div>
      )}

      <nav aria-label="Brackets" className="border-b border-border overflow-x-auto">
        <ul className="flex min-w-max">
          {visible.map((bracket) => {
            const isCurrent = bracket.slug === currentSlug
            const live = bracket.status === 'published'
            return (
              <li key={bracket.slug}>
                <Link
                  to={`/brackets/${bracket.slug}`}
                  aria-current={isCurrent ? 'page' : undefined}
                  className={`flex items-center gap-2 px-4 py-2.5 text-sm border-b-2 -mb-px transition-colors ${
                    isCurrent
                      ? 'border-secondary text-text-primary'
                      : 'border-transparent text-text-muted hover:text-text-primary'
                  }`}
                >
                  {selectedKey === null && hasSets && bracket.set_name && (
                    <span className="text-[10px] uppercase tracking-wider text-text-muted/70">
                      {bracket.set_name}
                    </span>
                  )}
                  <span className="whitespace-nowrap">{bracket.name}</span>
                  <span
                    className={`text-[10px] font-semibold uppercase tracking-wider ${
                      live ? 'text-accent-green' : 'text-text-muted/70'
                    }`}
                  >
                    {live && (
                      <span
                        aria-hidden="true"
                        className="inline-block w-1.5 h-1.5 mr-1 align-middle bg-accent-green"
                      />
                    )}
                    {statusLabel(bracket.status)}
                  </span>
                </Link>
              </li>
            )
          })}
        </ul>
      </nav>
    </div>
  )
}
