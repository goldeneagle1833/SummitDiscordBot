import { useEffect } from 'react'
import usePageTitle from '@/hooks/usePageTitle'

export default function Privacy() {
  usePageTitle('Privacy Policy')
  useEffect(() => {
  }, [])

  return (
    <div className="max-w-3xl mx-auto space-y-6">
      <h1 className="text-2xl font-display text-secondary">Privacy Policy</h1>
      <div className="bg-bg-surface border border-border rounded-soft p-6 space-y-4 text-sm leading-relaxed">
        <p>
          Sorcerers Summit respects your privacy. This policy outlines how we collect, use, and protect
          your information.
        </p>
        <h2 className="text-lg font-semibold pt-2">Information We Collect</h2>
        <p className="text-text-muted">
          We collect your Discord user ID and display name when you interact with our bot or log in
          via Discord OAuth. Match results, ELO ratings, and deck submissions are stored to provide
          leaderboard and stats features.
        </p>
        <h2 className="text-lg font-semibold pt-2">How We Use Your Information</h2>
        <p className="text-text-muted">
          Your data is used solely to power the Summit platform features: matchmaking, leaderboards,
          player profiles, and deck statistics. We do not sell or share your data with third parties.
        </p>
        <h2 className="text-lg font-semibold pt-2">Data Retention</h2>
        <p className="text-text-muted">
          Match records and ELO data are retained indefinitely to maintain historical leaderboards.
          You may request deletion of your data by contacting us through our Discord server.
        </p>
        <h2 className="text-lg font-semibold pt-2">Contact</h2>
        <p className="text-text-muted">
          If you have questions about this policy, please reach out through our Discord community.
        </p>
      </div>
    </div>
  )
}
