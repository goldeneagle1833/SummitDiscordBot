import { useState, useEffect } from 'react'
import usePageTitle from '@/hooks/usePageTitle'

export default function LifeCounter() {
  usePageTitle('Life Counter')
  const [player1, setPlayer1] = useState(20)
  const [player2, setPlayer2] = useState(20)

  useEffect(() => {
  }, [])

  const reset = () => {
    setPlayer1(20)
    setPlayer2(20)
  }

  const adjustButtons = [
    { label: '-5', delta: -5 },
    { label: '-1', delta: -1 },
    { label: '+1', delta: 1 },
    { label: '+5', delta: 5 },
  ]

  return (
    <div className="max-w-2xl mx-auto space-y-6">
      <h1 className="text-2xl font-display text-secondary text-center">Life Counter</h1>

      <div className="grid grid-cols-2 gap-6">
        {/* Player 1 */}
        <div className="bg-bg-surface border border-border rounded-soft p-6 text-center">
          <h2 className="text-sm font-semibold text-text-muted mb-2">Player 1</h2>
          <p className="text-5xl font-display text-secondary mb-4">{player1}</p>
          <div className="flex justify-center gap-2">
            {adjustButtons.map(({ label, delta }) => (
              <button
                key={label}
                onClick={() => setPlayer1((v) => v + delta)}
                className="px-3 py-1.5 text-sm font-medium bg-bg-surface border border-border rounded-soft hover:border-primary/50 transition-colors"
              >
                {label}
              </button>
            ))}
          </div>
        </div>

        {/* Player 2 */}
        <div className="bg-bg-surface border border-border rounded-soft p-6 text-center">
          <h2 className="text-sm font-semibold text-text-muted mb-2">Player 2</h2>
          <p className="text-5xl font-display text-secondary mb-4">{player2}</p>
          <div className="flex justify-center gap-2">
            {adjustButtons.map(({ label, delta }) => (
              <button
                key={label}
                onClick={() => setPlayer2((v) => v + delta)}
                className="px-3 py-1.5 text-sm font-medium bg-bg-surface border border-border rounded-soft hover:border-primary/50 transition-colors"
              >
                {label}
              </button>
            ))}
          </div>
        </div>
      </div>

      <div className="text-center">
        <button
          onClick={reset}
          className="px-5 py-2 bg-primary text-white rounded-soft font-medium hover:bg-primary-light transition-colors"
        >
          Reset
        </button>
      </div>
    </div>
  )
}
