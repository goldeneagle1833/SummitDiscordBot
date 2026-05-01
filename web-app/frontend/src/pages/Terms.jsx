import { useEffect } from 'react'
import usePageTitle from '@/hooks/usePageTitle'

export default function Terms() {
  usePageTitle('Terms of Service')
  useEffect(() => {
  }, [])

  return (
    <div className="max-w-3xl mx-auto space-y-6">
      <h1 className="text-2xl font-display text-secondary">Terms of Service</h1>
      <div className="bg-bg-surface border border-border rounded-soft p-6 space-y-4 text-sm leading-relaxed">
        <p>
          By using Sorcerers Summit, you agree to the following terms.
        </p>
        <h2 className="text-lg font-semibold pt-2">Use of Service</h2>
        <p className="text-text-muted">
          Sorcerers Summit is a free community platform for Sorcery: Contested Realm players. You agree
          to use the service in good faith and not abuse matchmaking, reporting, or any other features.
        </p>
        <h2 className="text-lg font-semibold pt-2">Fair Play</h2>
        <p className="text-text-muted">
          Match results must be reported honestly. Falsifying match outcomes, manipulating ELO ratings,
          or engaging in any form of cheating may result in removal from the platform.
        </p>
        <h2 className="text-lg font-semibold pt-2">Community Conduct</h2>
        <p className="text-text-muted">
          Be respectful to other players. Harassment, hate speech, and abusive behavior will not be
          tolerated and may result in a ban.
        </p>
        <h2 className="text-lg font-semibold pt-2">Disclaimer</h2>
        <p className="text-text-muted">
          Sorcerers Summit is a community project and is not affiliated with or endorsed by the creators
          of Sorcery: Contested Realm. The service is provided as-is without warranty.
        </p>
      </div>
    </div>
  )
}
