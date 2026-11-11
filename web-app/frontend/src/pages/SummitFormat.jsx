import { useEffect, useState } from 'react'
import { Link } from 'react-router-dom'
import { getProducts, formatMoney } from '@/api/store'
import usePageTitle from '@/hooks/usePageTitle'
import PageTabs from '@/components/ui/PageTabs'
import { HELP_TABS } from '@/utils/pageTabs'

// Mirrors the bot: TOP_CUT_SIZE and TOP_CUT_LADDER_SEEDS in
// discord-bot/services/postseason.py. Change both together.
const TOP_CUT_SIZE = 32
const LADDER_SEEDS = 8

// Details Bruce still has to confirm. Anything shown with <Tbc /> is a
// placeholder and must be filled in before this page ships.
function Tbc({ children = 'Details coming soon' }) {
  return (
    <span className="inline-block rounded-soft border border-dashed border-border px-2 py-0.5 text-xs text-text-muted">
      {children}
    </span>
  )
}

function Section({ id, title, children }) {
  return (
    <section id={id} className="bg-bg-surface border border-border rounded-soft p-6 space-y-4 scroll-mt-20">
      <h2 className="text-lg font-semibold">{title}</h2>
      <div className="space-y-3 text-sm leading-relaxed">{children}</div>
    </section>
  )
}

// The season ticket is a Summit Store listing named like "Season 9 Ticket".
// The page shows the newest one (highest season number) that's on sale.
const TICKET_NAME = /season\s*(\d+)\s*ticket/i

export function findSeasonTicket(products) {
  let best = null
  for (const p of products || []) {
    const m = TICKET_NAME.exec(p?.name || '')
    if (!m) continue
    const season = Number(m[1])
    if (!best || season > best.season) best = { season, product: p }
  }
  return best
}

function useSeasonTicket() {
  const [ticket, setTicket] = useState(null)
  useEffect(() => {
    let alive = true
    getProducts()
      .then((data) => { if (alive) setTicket(findSeasonTicket(data?.products)) })
      .catch(() => {})
    return () => { alive = false }
  }, [])
  return ticket
}

function TicketCard({ ticket }) {
  const p = ticket.product
  const soldOut = p.stock_quantity != null && p.stock_quantity <= 0
  return (
    <div className="rounded-soft border border-primary/40 bg-primary/5 p-4 flex flex-col sm:flex-row sm:items-center gap-3">
      <div className="flex-1 min-w-0">
        <p className="font-semibold">{p.name}</p>
        <p className="text-secondary font-semibold">{formatMoney(p.price_cents, p.currency)}</p>
      </div>
      {soldOut ? (
        <span className="text-text-muted text-sm">Sold out</span>
      ) : (
        <Link
          to="/store"
          className="inline-flex justify-center rounded-soft bg-primary px-4 py-2 text-sm font-semibold text-white hover:opacity-90"
        >
          Get a ticket
        </Link>
      )}
    </div>
  )
}

const STEPS = [
  { n: 1, title: 'Get a ticket', text: 'Ticket holders play for a top cut spot. Everyone else can still play ranked as Free Play.' },
  { n: 2, title: 'Climb the ladder', text: 'Play ranked games all season. Every game moves your season ELO.' },
  { n: 3, title: `Make the top ${TOP_CUT_SIZE}`, text: `When the season ends, the top ${TOP_CUT_SIZE} ticket holders on the ladder qualify.` },
  { n: 4, title: 'Win the bracket', text: 'Qualifiers play a single bracket for the season prizes.' },
]

const PRIZE_ROWS = [
  { place: '1st' },
  { place: '2nd' },
  { place: '3rd-4th' },
  { place: '5th-8th' },
  { place: `9th-${TOP_CUT_SIZE}th` },
]

const JUMP_LINKS = [
  { href: '#schedule', label: 'Schedule' },
  { href: '#tickets', label: 'Tickets' },
  { href: '#top-cut', label: 'Top cut' },
  { href: '#prizes', label: 'Prizes' },
  { href: '#faq', label: 'FAQ' },
]

export default function SummitFormat() {
  usePageTitle('Summit Format')
  const ticket = useSeasonTicket()
  const ticketProduct = ticket?.product

  return (
    <div className="max-w-3xl mx-auto space-y-6">
      <PageTabs tabs={HELP_TABS} label="Help pages" />

      <div className="space-y-2">
        <h1 className="text-2xl font-display text-secondary">How the Sorcerers Summit works</h1>
        <p className="text-sm text-text-muted">
          Every season is a ranked ladder that ends in a top {TOP_CUT_SIZE} bracket. Here's how tickets,
          the top cut and prizes fit together.
        </p>
        <nav aria-label="On this page" className="flex flex-wrap gap-2 pt-1">
          {JUMP_LINKS.map((l) => (
            <a
              key={l.href}
              href={l.href}
              className="rounded-soft border border-border px-3 py-1 text-xs text-text-muted hover:text-primary hover:border-primary"
            >
              {l.label}
            </a>
          ))}
        </nav>
      </div>

      <ol className="grid grid-cols-1 sm:grid-cols-2 gap-3">
        {STEPS.map((s) => (
          <li key={s.n} className="bg-bg-surface border border-border rounded-soft p-4 flex gap-3">
            <span className="flex h-7 w-7 shrink-0 items-center justify-center rounded-full bg-primary/15 text-primary text-sm font-semibold">
              {s.n}
            </span>
            <div className="text-sm">
              <p className="font-semibold">{s.title}</p>
              <p className="text-text-muted">{s.text}</p>
            </div>
          </li>
        ))}
      </ol>

      <Section id="schedule" title="Season schedule">
        <ul className="list-disc pl-5 space-y-1">
          <li>Seasons run about 43 days and start on the 1st or the 16th of a month.</li>
          <li>Each season ends at 11:59 PM Eastern on its last day.</li>
          <li>
            There's a 3-day break between seasons for the top cut bracket. No ELO moves during the break, but
            Casual and Limited stay open.
          </li>
        </ul>
        <p className="text-text-muted">
          The exact dates for upcoming seasons are posted in the leaderboard channel on Discord.
        </p>
      </Section>

      <Section id="tickets" title="Tickets">
        <p>
          A season ticket is what puts you in the running for the top cut. Without one you can still play every
          ranked game, and you'll show up in the Free Play section of the leaderboard.
        </p>
        {ticket && <TicketCard ticket={ticket} />}
        {ticketProduct?.description && (
          <p className="whitespace-pre-line text-text-muted">{ticketProduct.description}</p>
        )}
        <dl className="grid grid-cols-1 sm:grid-cols-[10rem_1fr] gap-x-4 gap-y-2">
          <dt className="font-medium">Price</dt>
          <dd>
            {ticketProduct ? formatMoney(ticketProduct.price_cents, ticketProduct.currency) : <Tbc />}
          </dd>
          <dt className="font-medium">Where to buy</dt>
          <dd>
            {ticketProduct ? (
              <Link to="/store" className="text-primary hover:underline">The Summit Store</Link>
            ) : (
              <Tbc />
            )}
          </dd>
          <dt className="font-medium">When sales close</dt>
          <dd>Tickets stay on sale for the whole season, until it ends at 11:59 PM Eastern on its last day.</dd>
          <dt className="font-medium">Buying mid-season</dt>
          <dd>
            You can buy one any time, but any avatar rated above 1500 is reset to 1500 when you do. Anything
            at or below 1500 stays where it is.
          </dd>
        </dl>
      </Section>

      <Section id="top-cut" title="Top cut">
        <p>
          When the season ends, the top {TOP_CUT_SIZE} ticket holders on the season ladder make the top cut.
          Each player counts once, so a second avatar never takes someone else's spot.
        </p>
        <ul className="list-disc pl-5 space-y-1">
          <li>Seeds 1 to {LADDER_SEEDS} keep their ladder order.</li>
          <li>Seeds {LADDER_SEEDS + 1} to {TOP_CUT_SIZE} are drawn at random.</li>
          <li>A full {TOP_CUT_SIZE} means nobody gets a bye. If fewer qualify, byes go to the top seeds.</li>
          <li>Qualifiers get the Top Cut role and access to the Top Cut channel on Discord.</li>
        </ul>
        <dl className="grid grid-cols-1 sm:grid-cols-[10rem_1fr] gap-x-4 gap-y-2">
          <dt className="font-medium">Match format</dt>
          <dd><Tbc /></dd>
          <dt className="font-medium">Where it's played</dt>
          <dd><Tbc /></dd>
          <dt className="font-medium">When it's played</dt>
          <dd>During the 3-day break before the next season starts.</dd>
        </dl>
        <p>
          The bracket goes up on the <Link to="/brackets" className="text-primary hover:underline">Season Top Cut</Link> page
          once it's published.
        </p>
      </Section>

      <Section id="prizes" title="Prizes">
        <div className="overflow-hidden rounded-soft border border-border">
          <table className="w-full text-sm">
            <thead className="bg-bg-elevated text-left">
              <tr>
                <th className="px-4 py-2 font-medium w-32">Place</th>
                <th className="px-4 py-2 font-medium">Prize</th>
              </tr>
            </thead>
            <tbody>
              {PRIZE_ROWS.map((row) => (
                <tr key={row.place} className="border-t border-border">
                  <td className="px-4 py-2 font-medium">{row.place}</td>
                  <td className="px-4 py-2"><Tbc /></td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      </Section>

      <Section id="faq" title="FAQ">
        <div>
          <p className="font-medium">Do I need a ticket to play ranked?</p>
          <p className="text-text-muted">
            No. Anyone can play ranked. The ticket only decides who can qualify for the top cut.
          </p>
        </div>
        <div>
          <p className="font-medium">Where can I see where I stand?</p>
          <p className="text-text-muted">
            The <Link to="/" className="text-primary hover:underline">leaderboard</Link> shows the season ladder,
            and the leaderboard channel on Discord splits it into Ticket Holders and Free Play after every game.
          </p>
        </div>
      </Section>
    </div>
  )
}
