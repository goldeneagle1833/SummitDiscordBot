import { Link } from 'react-router-dom'
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
  { href: '#tickets', label: 'Tickets' },
  { href: '#top-cut', label: 'Top cut' },
  { href: '#prizes', label: 'Prizes' },
  { href: '#faq', label: 'FAQ' },
]

export default function SummitFormat() {
  usePageTitle('Summit Format')

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

      <Section id="tickets" title="Tickets">
        <p>
          A season ticket is what puts you in the running for the top cut. Without one you can still play every
          ranked game, and you'll show up in the Free Play section of the leaderboard.
        </p>
        <dl className="grid grid-cols-1 sm:grid-cols-[10rem_1fr] gap-x-4 gap-y-2">
          <dt className="font-medium">Price</dt>
          <dd><Tbc /></dd>
          <dt className="font-medium">Where to buy</dt>
          <dd><Tbc /></dd>
          <dt className="font-medium">When sales close</dt>
          <dd><Tbc /></dd>
          <dt className="font-medium">Buying mid-season</dt>
          <dd><Tbc /></dd>
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
          <dt className="font-medium">Round deadlines</dt>
          <dd><Tbc /></dd>
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
