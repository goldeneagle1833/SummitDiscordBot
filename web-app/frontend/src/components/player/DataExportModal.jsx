import { useState, useEffect } from 'react'
import { downloadOwnData } from '@/api/players'

const INCLUDED = [
  'Profile and display name',
  'Ratings, season finishes and Limited runs',
  'Full match history with your decks and replays',
  'Saved decks, featured deck and paper results',
  'Applause you gave and received',
  'Articles, feedback, store orders and settings',
]

/** Owner-only: download a zip of everything the site holds for this player. */
export default function DataExportModal({ playerId, onClose }) {
  const [busy, setBusy] = useState(false)
  const [error, setError] = useState(null)
  const [done, setDone] = useState(false)

  useEffect(() => {
    const handler = (e) => { if (e.key === 'Escape') onClose() }
    document.addEventListener('keydown', handler)
    return () => document.removeEventListener('keydown', handler)
  }, [onClose])

  const handleDownload = async () => {
    setBusy(true)
    setError(null)
    try {
      const { blob, filename } = await downloadOwnData(playerId)
      const url = URL.createObjectURL(blob)
      const a = document.createElement('a')
      a.href = url
      a.download = filename || 'sorcerers-summit-data.zip'
      document.body.appendChild(a)
      a.click()
      a.remove()
      setTimeout(() => URL.revokeObjectURL(url), 10000)
      setDone(true)
    } catch (err) {
      setError(err.message || 'Could not build your export')
    } finally {
      setBusy(false)
    }
  }

  return (
    <div className="fixed inset-0 z-50 flex items-center justify-center bg-black/60" onClick={onClose}>
      <div
        role="dialog"
        aria-labelledby="data-export-title"
        className="bg-bg-surface border border-border rounded-lg p-6 w-full max-w-md mx-4"
        onClick={(e) => e.stopPropagation()}
      >
        <h3 id="data-export-title" className="text-lg font-semibold text-text-primary mb-1">Export my data</h3>
        <p className="text-xs text-text-muted mb-4">
          Download a copy of everything Sorcerers Summit holds for you, as a zip file.
        </p>

        <ul className="text-sm text-text-primary space-y-1.5 mb-4">
          {INCLUDED.map((line) => (
            <li key={line} className="flex gap-2">
              <span className="text-secondary" aria-hidden="true">✓</span>
              <span>{line}</span>
            </li>
          ))}
        </ul>

        <p className="text-xs text-text-muted">
          The zip has <code>summit-data.json</code> with everything, and <code>matches.csv</code> you can
          open in a spreadsheet. You get your opponents&apos; avatars and elements, but not their deck lists. Only you can download this.
        </p>

        {error && <p className="text-xs text-accent-red mt-3">{error}</p>}
        {done && !error && <p className="text-xs text-green-400 mt-3">Your download has started.</p>}

        <div className="flex justify-end gap-2 mt-5">
          <button
            onClick={onClose}
            className="px-4 py-2 text-sm rounded border border-border text-text-muted hover:text-text-primary"
          >
            Close
          </button>
          <button
            onClick={handleDownload}
            disabled={busy}
            className="px-4 py-2 text-sm rounded bg-secondary text-black hover:opacity-90 disabled:opacity-50"
          >
            {busy ? 'Preparing...' : 'Download my data'}
          </button>
        </div>
      </div>
    </div>
  )
}
