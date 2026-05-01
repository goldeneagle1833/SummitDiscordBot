import { useState, useEffect, useMemo } from 'react'
import { get } from '@/api/client'
import Spinner from '@/components/ui/Spinner'
import usePageTitle from '@/hooks/usePageTitle'

export default function Community() {
  usePageTitle('Community Links')
  const [data, setData] = useState(null)
  const [youtubeVideos, setYoutubeVideos] = useState(null)
  const [loading, setLoading] = useState(true)
  const [error, setError] = useState(null)
  const [stateFilter, setStateFilter] = useState('')

  useEffect(() => {
    Promise.all([
      get('/api/community'),
      get('/api/youtube-videos').catch(() => ({})),
    ])
      .then(([communityData, videos]) => {
        setData(communityData)
        setYoutubeVideos(videos)
      })
      .catch((err) => setError(err.message))
      .finally(() => setLoading(false))
  }, [])

  const servers = data?.discord_servers || []
  const websites = data?.websites || []

  const filteredServers = useMemo(() => {
    if (!stateFilter.trim()) return servers
    const q = stateFilter.toLowerCase().trim()
    return servers.filter((s) => (s.state || '').toLowerCase().includes(q))
  }, [servers, stateFilter])

  const videoList = useMemo(() => {
    if (!youtubeVideos) return []
    return Object.values(youtubeVideos).filter(Boolean)
  }, [youtubeVideos])

  if (loading) return <Spinner className="py-20" />
  if (error) return <p className="text-center text-accent-red py-8">{error}</p>

  return (
    <div>
      {/* Hero */}
      <section className="text-center mb-8">
        <h1 className="text-2xl font-display text-secondary mb-2">Community Links</h1>
        <p className="text-text-muted text-sm">Connect with the Sorcery community</p>
      </section>

      {/* YouTube Channels */}
      <section className="mb-8">
        <h2 className="font-display text-secondary text-lg mb-3">YouTube Channels</h2>
        {videoList.length > 0 ? (
          <div className="grid grid-cols-1 sm:grid-cols-2 lg:grid-cols-3 gap-4">
            {videoList.map((video) => (
              <div key={video.channel_url || video.url} className="bg-bg-surface border border-border rounded-lg overflow-hidden">
                {video.thumbnail && (
                  <a href={video.url} target="_blank" rel="noopener noreferrer">
                    <img
                      src={video.thumbnail}
                      alt={video.title}
                      className="w-full h-36 object-cover"
                      loading="lazy"
                    />
                  </a>
                )}
                <div className="p-4">
                  <h3 className="font-semibold text-text-primary mb-1">{video.channel_display_name}</h3>
                  <p className="text-xs text-text-muted truncate mb-2">Latest: {video.title}</p>
                  <a
                    href={video.channel_url}
                    target="_blank"
                    rel="noopener noreferrer"
                    className="text-sm text-secondary hover:underline"
                  >
                    Visit Channel →
                  </a>
                </div>
              </div>
            ))}
          </div>
        ) : (
          <p className="text-text-muted text-sm">No channels available.</p>
        )}
      </section>

      {/* Discord Servers */}
      <section className="mb-8">
        <h2 className="font-display text-secondary text-lg mb-3">Discord Servers</h2>
        {servers.length > 0 ? (
          <>
            <input
              type="text"
              className="bg-bg-raised border border-border rounded px-3 py-2 text-sm mb-4 w-full max-w-xs"
              placeholder="Filter by state..."
              value={stateFilter}
              onChange={(e) => setStateFilter(e.target.value)}
            />
            {filteredServers.length > 0 ? (
              <div className="grid grid-cols-1 sm:grid-cols-2 lg:grid-cols-3 gap-4">
                {filteredServers.map((server) => (
                  <div key={server.id || server.name} className="bg-bg-surface border border-border rounded-lg p-4">
                    {server.state && (
                      <span className="text-xs bg-secondary/20 text-secondary px-2 py-0.5 rounded mb-2 inline-block">
                        {server.state}
                      </span>
                    )}
                    <h3 className="font-semibold text-text-primary mb-1">{server.name}</h3>
                    {server.description && (
                      <p className="text-sm text-text-muted mb-2">{server.description}</p>
                    )}
                    <a
                      href={server.invite_url}
                      target="_blank"
                      rel="noopener noreferrer"
                      className="text-sm text-secondary hover:underline"
                    >
                      Join Server →
                    </a>
                  </div>
                ))}
              </div>
            ) : (
              <p className="text-text-muted text-sm">No servers match your filter.</p>
            )}
          </>
        ) : (
          <p className="text-text-muted text-sm">No Discord servers added yet.</p>
        )}
      </section>

      {/* Websites & Resources */}
      <section className="mb-8">
        <h2 className="font-display text-secondary text-lg mb-3">Websites &amp; Resources</h2>
        {websites.length > 0 ? (
          <div className="grid grid-cols-1 sm:grid-cols-2 lg:grid-cols-3 gap-4">
            {websites.map((site) => (
              <div key={site.id || site.url} className="bg-bg-surface border border-border rounded-lg p-4">
                <h3 className="font-semibold text-text-primary mb-1">{site.name}</h3>
                {site.description && (
                  <p className="text-sm text-text-muted mb-2">{site.description}</p>
                )}
                <a
                  href={site.url}
                  target="_blank"
                  rel="noopener noreferrer"
                  className="text-sm text-secondary hover:underline"
                >
                  Visit Site →
                </a>
              </div>
            ))}
          </div>
        ) : (
          <p className="text-text-muted text-sm">No websites added yet.</p>
        )}
      </section>
    </div>
  )
}
