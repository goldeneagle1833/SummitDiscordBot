import usePageTitle from '@/hooks/usePageTitle'

// Terms for anyone using Summit data: the open APIs (Staples, public match
// history) and anything copied from the site. Bump EFFECTIVE when the text changes.
const EFFECTIVE = 'November 27, 2026'

function Section({ title, children }) {
  return (
    <>
      <h2 className="text-lg font-semibold pt-2">{title}</h2>
      <div className="text-text-muted space-y-2">{children}</div>
    </>
  )
}

export default function DataTerms() {
  usePageTitle('API & Data Terms of Use')

  return (
    <div className="max-w-3xl mx-auto space-y-6">
      <div>
        <h1 className="text-2xl font-display text-secondary">API &amp; Data Terms of Use</h1>
        <p className="text-xs text-text-muted mt-1">Effective {EFFECTIVE}</p>
      </div>
      <div className="bg-bg-surface border border-border rounded-soft p-6 space-y-4 text-sm leading-relaxed">
        <p>
          These terms cover Sorcerers Summit's open APIs (for example <code>/api/staples</code> and{' '}
          <code>/api/public/players/…</code>) and any data you take from sorcererssummit.com. By calling
          an API or using Summit data you agree to them. If you don't agree, don't use the data.
        </p>

        <Section title="1. What you may do">
          <p>
            You may use Summit data, free of charge, for personal and community projects that help Sorcery
            players: bots, overlays, stat sites, articles, videos and tools. Commercial use (selling the data,
            putting it behind a paywall, or using it in a paid product) needs our written permission first.
            Ask us on Discord.
          </p>
        </Section>

        <Section title="2. Credit Sorcerers Summit">
          <p>
            Wherever you show Summit data, say where it came from, for example "Data from Sorcerers Summit"
            with a link to sorcererssummit.com. Don't suggest that Sorcerers Summit endorses, runs or partners
            with your project unless we have agreed to that in writing.
          </p>
        </Section>

        <Section title="3. Respect players">
          <ul className="list-disc pl-5 space-y-1">
            <li>Don't use the data to harass, stalk, shame or target any player.</li>
            <li>
              Don't try to rebuild, guess or publish a player's ranked deck list. The APIs give avatar and deck
              elements only, on purpose.
            </li>
            <li>
              Don't combine Summit data with other sources to work out who a player is outside Summit, or to
              build profiles of players that they haven't chosen to share.
            </li>
            <li>
              Keep copies fresh. If you store player data, refresh or delete it at least every 30 days, so that a
              player who resets their profile or deletes their account drops out of your copy too.
              If a player asks you to remove their data, remove it.
            </li>
          </ul>
        </Section>

        <Section title="4. Use the APIs fairly">
          <ul className="list-disc pl-5 space-y-1">
            <li>Stay within the rate limits. Don't spread calls over many IPs or keys to get around them.</li>
            <li>Cache what you fetch. Data changes slowly; there is no need to call for every page view.</li>
            <li>
              Don't scrape the website's pages or call its private endpoints. Use the documented open APIs only.
            </li>
            <li>
              Don't republish the whole dataset in bulk (for example a full dump of every player's match history)
              or offer it as a download of its own.
            </li>
            <li>Don't try to read held-back data before its release (Meta Report batches come out on the 1st and 15th).</li>
          </ul>
        </Section>

        <Section title="5. Changes and access">
          <p>
            The APIs are a free community service. We may change them, limit them, or stop them at any time, and we may
            block any app, IP or person that breaks these terms or puts load on the site. We may update these terms; the
            date above shows the latest version, and using the data after a change means you accept it.
          </p>
        </Section>

        <Section title="6. No warranty">
          <p>
            The data is provided as-is, without any warranty. It may be incomplete, delayed or wrong (results can be
            corrected after the fact). To the fullest extent the law allows, Sorcerers Summit LLC is not liable for any
            loss that comes from using the APIs or the data.
          </p>
        </Section>

        <Section title="7. Not official">
          <p>
            Sorcerers Summit is a community project and is not affiliated with or endorsed by the creators of Sorcery:
            Contested Realm. Card names and game content belong to their owners. These terms don't give you any rights
            to their art, logos or trademarks.
          </p>
        </Section>

        <Section title="Contact">
          <p>Questions, permission requests or removal requests: reach the Sorcerers Summit team on our Discord.</p>
        </Section>
      </div>
    </div>
  )
}
