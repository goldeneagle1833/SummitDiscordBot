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

/** Constructed (the season top cut) or Limited (a Limited season's top 8). */
export const formatOf = (bracket) => (bracket?.format === 'limited' ? 'limited' : 'constructed')

export const FORMATS = [
  { key: 'constructed', label: 'Constructed' },
  { key: 'limited', label: 'Limited' },
]

/** The Summit's own top cuts, or brackets players run for their own events. */
export const kindOf = (bracket) => (bracket?.kind === 'community' ? 'community' : 'official')

export const KINDS = [
  { key: 'official', label: 'Season top cut' },
  { key: 'community', label: 'Community' },
]

/**
 * Where to land for a format: its live or latest top cut, else its newest
 * community bracket - so a player's event never displaces the season's.
 */
export function pickBracketFor(brackets = [], format, kind = null) {
  const inFormat = brackets.filter((b) => formatOf(b) === format)
  if (kind) return pickActiveBracket(inFormat.filter((b) => kindOf(b) === kind))
  return (
    pickActiveBracket(inFormat.filter((b) => kindOf(b) === 'official')) ||
    pickActiveBracket(inFormat)
  )
}

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
 * Across the top of the bracket page: Constructed or Limited, then - when
 * players have run brackets of their own - the season top cut or the
 * community ones, a filter by card set, and a tab per bracket, so a viewer
 * can flip from the live top cut to an older one without a detour through a
 * list. `openFormat` says which tab is open when no bracket is on screen.
 */
export default function BracketSwitcher({
  brackets,
  currentSlug,
  openFormat = null,
  canOrganize = false,
}) {
  const navigate = useNavigate()
  const [showAll, setShowAll] = useState(false)

  if (!brackets) return null

  const current = brackets.find((b) => b.slug === currentSlug)
  const currentFormat = current ? formatOf(current) : openFormat || 'constructed'
  const inFormat = brackets.filter((b) => formatOf(b) === currentFormat)
  const hasCommunity = inFormat.some((b) => kindOf(b) === 'community')
  const currentKind = current ? kindOf(current) : 'official'
  const pool = hasCommunity ? inFormat.filter((b) => kindOf(b) === currentKind) : inFormat

  const groups = groupBrackets(pool)
  const currentKey = setKey(current)
  const hasSets = groups.some((g) => g.key)
  const selectedKey = showAll || !hasSets ? null : currentKey
  const visible = selectedKey === null
    ? pool
    : groups.find((g) => g.key === selectedKey)?.brackets || pool

  function chooseFormat(next) {
    setShowAll(false)
    if (next === currentFormat) return
    const target = pickBracketFor(brackets, next)
    navigate(target ? `/brackets/${target.slug}` : `/brackets?format=${next}`)
  }

  function chooseKind(kind) {
    setShowAll(false)
    if (kind === currentKind) return
    const target = pickBracketFor(brackets, currentFormat, kind)
    if (target) navigate(`/brackets/${target.slug}`)
  }

  function chooseSet(group) {
    setShowAll(false)
    if (group.key === currentKey) return
    const target = pickActiveBracket(group.brackets)
    if (target) navigate(`/brackets/${target.slug}`)
  }

  return (
    <div className="space-y-3">
      <div className="flex flex-wrap items-center justify-between gap-3">
        <div role="group" aria-label="Format" className="inline-flex border border-border rounded-sm overflow-hidden">
          {FORMATS.map((format) => {
            const selected = format.key === currentFormat
            const live = brackets.some((b) => formatOf(b) === format.key && b.status === 'published')
            return (
              <button
                key={format.key}
                type="button"
                aria-pressed={selected}
                onClick={() => chooseFormat(format.key)}
                className={`px-4 py-1.5 text-xs font-semibold uppercase tracking-wider transition-colors ${
                  selected ? 'bg-secondary text-black' : 'text-text-muted hover:text-text-primary'
                }`}
              >
                {format.label}
                {live && (
                  <span
                    aria-label="live"
                    className={`inline-block w-1.5 h-1.5 ml-2 align-middle ${
                      selected ? 'bg-black' : 'bg-accent-green'
                    }`}
                  />
                )}
              </button>
            )
          })}
        </div>
        {canOrganize && (
          <Link
            to="/brackets/manage"
            className="px-3 py-1.5 text-xs font-semibold uppercase tracking-wider border border-secondary text-secondary rounded-sm hover:bg-secondary/10"
          >
            + Create a bracket
          </Link>
        )}
      </div>

      {hasCommunity && (
        <div role="group" aria-label="Bracket type" className="flex flex-wrap items-center gap-2">
          {KINDS.map((kind) => {
            const selected = kind.key === currentKind
            const count = inFormat.filter((b) => kindOf(b) === kind.key).length
            return (
              <button
                key={kind.key}
                type="button"
                aria-pressed={selected}
                disabled={!count}
                onClick={() => chooseKind(kind.key)}
                className={`${CHIP} disabled:opacity-40 ${
                  selected
                    ? 'border-secondary bg-secondary/10 text-secondary'
                    : 'border-border text-text-muted hover:text-text-primary hover:border-text-muted'
                }`}
              >
                {kind.label}
                <span className="ml-1.5 font-mono font-normal opacity-70">{count}</span>
              </button>
            )
          })}
        </div>
      )}

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

      {visible.length > 1 && (
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
      )}
    </div>
  )
}
