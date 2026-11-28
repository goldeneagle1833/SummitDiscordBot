import { useEffect, useState } from 'react'
import { useAuth } from '@/context/AuthContext'
import { getAiConnections, disconnectAiApp } from '@/api/aiApps'
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
            card win rates, the Meta Report, Top 8 decks, the store and the ranked recap. It's free and
            read-only.
          </p>
          <div>
            <p className="font-medium">How to connect</p>
            <ol className="list-decimal pl-5 text-text-muted space-y-1">
              <li>In your AI app, open Settings, then Connectors (sometimes called MCP servers).</li>
              <li>Choose Add custom connector and paste one of these addresses:</li>
            </ol>
            <div className="mt-2 space-y-3">
              <div>
                <code className="inline-block break-all rounded bg-bg-elevated px-2 py-1 text-primary">{MCP_URL}</code>
                <p className="text-text-muted mt-1">Public data, no login.</p>
              </div>
              <div>
                <code className="inline-block break-all rounded bg-bg-elevated px-2 py-1 text-primary">{MCP_ACCOUNT_URL}</code>
                <p className="text-text-muted mt-1">
                  Signed in: everything above plus a deeper review of your own games, including your newest
                  games and your private Card Stats. Your AI app asks you to sign in with Discord, Google or an
                  email code, then to allow it. It can&apos;t change anything or see your ranked deck lists.
                </p>
              </div>
            </div>
          </div>
          <div>
            <p className="font-medium">Things to ask</p>
            <ul className="list-disc pl-5 text-text-muted space-y-1">
              <li>&quot;I&apos;m on Sparkmage against Pathfinder tonight. Prep me.&quot;</li>
              <li>&quot;Review my match history and give me tips. My name is &hellip;&quot;</li>
              <li>Signed in: &quot;Coach me from my games. Which cards are hurting me?&quot;</li>
              <li>&quot;Check my deck&quot; with a Curiosa link or a pasted list (it isn&apos;t saved).</li>
              <li>&quot;Summarize the latest Meta Report in 5 bullets.&quot;</li>
              <li>&quot;What happened in ranked this week?&quot;</li>
            </ul>
          </div>
          <ConnectedAiApps />
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
const MCP_ACCOUNT_URL = 'https://sorcererssummit.com/mcp/account'

// Signed-in players see the AI apps they allowed and can disconnect them
function ConnectedAiApps() {
  const { user } = useAuth()
  const [apps, setApps] = useState(null)
  const [error, setError] = useState('')

  useEffect(() => {
    if (!user) return
    getAiConnections()
      .then((data) => setApps(data.connections || []))
      .catch(() => setApps([]))
  }, [user])

  if (!user || !apps || apps.length === 0) return null

  const disconnect = async (clientId) => {
    setError('')
    try {
      const data = await disconnectAiApp(clientId)
      setApps(data.connections || [])
    } catch {
      setError('Could not disconnect. Try again.')
    }
  }

  return (
    <div>
      <p className="font-medium">Your connected AI apps</p>
      <ul className="mt-1 space-y-2">
        {apps.map((app) => (
          <li key={app.client_id} className="flex items-center justify-between gap-3 rounded bg-bg-elevated px-3 py-2">
            <span>
              {app.name}
              <span className="block text-xs text-text-muted">
                Connected {new Date(app.connected_at * 1000).toLocaleDateString()}
              </span>
            </span>
            <button
              type="button"
              onClick={() => disconnect(app.client_id)}
              className="shrink-0 rounded border border-border px-3 py-1 text-sm hover:border-primary"
            >
              Disconnect
            </button>
          </li>
        ))}
      </ul>
      {error && <p className="text-sm text-red-400 mt-1">{error}</p>}
    </div>
  )
}
