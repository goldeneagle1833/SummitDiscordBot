import { useEffect, useState } from 'react'
import { fetchSiteContent } from '@/api/explorer'

// Same wording the server falls back to, so the page reads right while the
// request is in flight or if it fails.
export const DEFAULT_SITE_CONTENT = {
  announcement: '',
  kicker: '',
  title: 'The Explorer Series',
  intro:
    'A player-run annual circuit for Sorcery TCG. The Series promotes a diverse range of local events, rewards players who travel to play the game, and builds relationships across our communities.',
  discord_url: '',
  member_url: '',
  show_points_guide: true,
  host_title: 'Bring the Series to your store',
  host_text: 'Each Explorer Series event is run by a local tournament organizer with their community of Sorcery players.',
  sections: [],
}

export default function useSiteContent() {
  const [content, setContent] = useState(DEFAULT_SITE_CONTENT)
  const [loaded, setLoaded] = useState(false)
  useEffect(() => {
    let alive = true
    fetchSiteContent()
      .then((data) => { if (alive && data) setContent({ ...DEFAULT_SITE_CONTENT, ...data }) })
      .catch(() => {})
      .finally(() => { if (alive) setLoaded(true) })
    return () => { alive = false }
  }, [])
  return { content, setContent, loaded }
}
