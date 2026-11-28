import { useEffect } from 'react'
import usePageTitle from '@/hooks/usePageTitle'
import PageTabs from '@/components/ui/PageTabs'
import { HELP_TABS } from '@/utils/pageTabs'

export default function Help() {
  usePageTitle('Help')
  useEffect(() => {
  }, [])

  return (
    <div className="max-w-3xl mx-auto space-y-6">
      <PageTabs tabs={HELP_TABS} label="Help pages" />
      <h1 className="text-2xl font-display text-secondary">Help</h1>

      <div className="bg-bg-surface border border-border rounded-soft p-6 space-y-4">
        <h2 className="text-lg font-semibold">Bot Commands</h2>
        <div className="space-y-3 text-sm">
          <div>
            <p className="font-medium text-primary">!lfg / /lfg</p>
            <p className="text-text-muted">Join the Looking For Game queue to find an opponent.</p>
          </div>
          <div>
            <p className="font-medium text-primary">!stats / /stats</p>
            <p className="text-text-muted">View your rating, win/loss record, and match history.</p>
          </div>
          <div>
            <p className="font-medium text-primary">!leaderboard / /leaderboard</p>
            <p className="text-text-muted">View the current rating leaderboard.</p>
          </div>
          <div>
            <p className="font-medium text-primary">!deck / /deck</p>
            <p className="text-text-muted">Check deck information using a Curiosa deck link.</p>
          </div>
        </div>
      </div>

      <div className="bg-bg-surface border border-border rounded-soft p-6 space-y-4">
        <h2 className="text-lg font-semibold">Website Features</h2>
        <div className="space-y-3 text-sm">
          <div>
            <p className="font-medium">Leaderboard</p>
            <p className="text-text-muted">Browse event and limited leaderboards.</p>
          </div>
          <div>
            <p className="font-medium">Events & Decks</p>
            <p className="text-text-muted">Explore top 8 decks from past tournaments.</p>
          </div>
          <div>
            <p className="font-medium">Player Profiles</p>
            <p className="text-text-muted">View detailed stats and match history for any player.</p>
          </div>
          <div>
            <p className="font-medium">Cards & Avatars</p>
            <p className="text-text-muted">Browse card and avatar performance data across all matches.</p>
          </div>
        </div>
      </div>

      <div id="ai-apps" className="bg-bg-surface border border-border rounded-soft p-6 space-y-4">
        <h2 className="text-lg font-semibold">Use Summit in AI apps</h2>
        <div className="space-y-3 text-sm">
          <p className="text-text-muted">
            Ask Claude, ChatGPT or another AI app about Summit data: matchup prep, deck checks, coaching from your match history, Avatar and
            card win rates, the Meta Report, Top 8 decks, the store and the ranked recap. It's free, read-only
            and needs no login.
          </p>
          <div>
            <p className="font-medium">How to connect</p>
            <ol className="list-decimal pl-5 text-text-muted space-y-1">
              <li>In your AI app, open Settings, then Connectors (sometimes called MCP servers).</li>
              <li>Choose Add custom connector and paste this address:</li>
            </ol>
            <code className="mt-2 inline-block break-all rounded bg-bg-elevated px-2 py-1 text-primary">
              {MCP_URL}
            </code>
          </div>
          <div>
            <p className="font-medium">Things to ask</p>
            <ul className="list-disc pl-5 text-text-muted space-y-1">
              <li>&quot;I&apos;m on Sparkmage against Pathfinder tonight. Prep me.&quot;</li>
              <li>&quot;Review my match history and give me tips. My name is &hellip;&quot;</li>
              <li>&quot;Check my deck&quot; with a Curiosa link or a pasted list (it isn&apos;t saved).</li>
              <li>&quot;Summarize the latest Meta Report in 5 bullets.&quot;</li>
              <li>&quot;What happened in ranked this week?&quot;</li>
            </ul>
          </div>
          <p className="text-text-muted">
            Ranked deck lists are never shared. Use of Summit data follows our{' '}
            <a href="/terms" className="text-primary underline">Terms</a>.
          </p>
        </div>
      </div>
    </div>
  )
}

const MCP_URL = 'https://sorcererssummit.com/mcp'
