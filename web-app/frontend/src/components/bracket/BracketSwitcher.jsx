import { Link } from 'react-router-dom'

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

function statusLabel(status) {
  if (status === 'published') return 'Live'
  if (status === 'draft') return 'Draft'
  return 'Final'
}

/**
 * A row of tabs across the top of the bracket page, one per bracket, so a
 * viewer can flip from the live top cut to an older one without a detour
 * through a list.
 */
export default function BracketSwitcher({ brackets, currentSlug }) {
  if (!brackets || brackets.length < 2) return null

  return (
    <nav aria-label="Brackets" className="border-b border-border overflow-x-auto">
      <ul className="flex min-w-max">
        {brackets.map((bracket) => {
          const current = bracket.slug === currentSlug
          const live = bracket.status === 'published'
          return (
            <li key={bracket.slug}>
              <Link
                to={`/brackets/${bracket.slug}`}
                aria-current={current ? 'page' : undefined}
                className={`flex items-center gap-2 px-4 py-2.5 text-sm border-b-2 -mb-px transition-colors ${
                  current
                    ? 'border-secondary text-text-primary'
                    : 'border-transparent text-text-muted hover:text-text-primary'
                }`}
              >
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
  )
}
