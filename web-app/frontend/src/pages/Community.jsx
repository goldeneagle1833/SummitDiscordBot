import { useState, useEffect } from 'react'
import { getCommunity } from '@/api/community'
import Spinner from '@/components/ui/Spinner'
import usePageTitle from '@/hooks/usePageTitle'

export default function Community() {
  usePageTitle('Community')
  const [data, setData] = useState(null)
  const [loading, setLoading] = useState(true)
  const [error, setError] = useState(null)

  useEffect(() => {
    getCommunity()
      .then(setData)
      .catch((err) => setError(err.message))
      .finally(() => setLoading(false))
  }, [])

  if (loading) return <Spinner className="py-20" />
  if (error) return <p className="text-center text-accent-red py-8">{error}</p>
  if (!data) return null

  return (
    <div>
      <h1 className="text-2xl font-display text-secondary mb-4">Community</h1>

      {data.servers?.length > 0 && (
        <div className="mb-6">
          <h2 className="text-lg font-semibold mb-3">Discord Servers</h2>
          <div className="grid grid-cols-1 sm:grid-cols-2 lg:grid-cols-3 gap-4">
            {data.servers.map((server) => (
              <a
                key={server.name}
                href={server.invite_url}
                target="_blank"
                rel="noopener noreferrer"
                className="bg-bg-surface border border-border rounded-soft p-4 hover:border-primary/50 transition-colors"
              >
                <h3 className="font-semibold mb-1">{server.name}</h3>
                {server.description && (
                  <p className="text-sm text-text-muted">{server.description}</p>
                )}
                {server.member_count != null && (
                  <p className="text-xs text-text-muted mt-2">{server.member_count} members</p>
                )}
              </a>
            ))}
          </div>
        </div>
      )}

      {data.links?.length > 0 && (
        <div>
          <h2 className="text-lg font-semibold mb-3">Useful Links</h2>
          <div className="grid grid-cols-1 sm:grid-cols-2 lg:grid-cols-3 gap-4">
            {data.links.map((link) => (
              <a
                key={link.url}
                href={link.url}
                target="_blank"
                rel="noopener noreferrer"
                className="bg-bg-surface border border-border rounded-soft p-4 hover:border-primary/50 transition-colors"
              >
                <h3 className="font-semibold mb-1">{link.title}</h3>
                {link.description && (
                  <p className="text-sm text-text-muted">{link.description}</p>
                )}
              </a>
            ))}
          </div>
        </div>
      )}
    </div>
  )
}
