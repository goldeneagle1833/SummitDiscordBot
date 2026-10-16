import { useEffect, useState } from 'react'
import { Link } from 'react-router-dom'
import { getAvatars, getAvatarImageFiles } from '@/api/cards'
import { getAvatarImagePath } from '@/utils/avatarBadges'

/**
 * Avatar art and community win rates for a period ('lifetime', 'current' or an
 * event id), shared by the Avatars and Matchups tabs.
 * Both requests are optional: cards fall back to a plain panel without art.
 */
export function useAvatarArt(period = 'lifetime') {
  const [imageFiles, setImageFiles] = useState([])
  const [community, setCommunity] = useState({})
  useEffect(() => {
    let active = true
    getAvatarImageFiles().then((files) => active && setImageFiles(files || [])).catch(() => {})
    return () => {
      active = false
    }
  }, [])
  useEffect(() => {
    let active = true
    setCommunity({})
    const params = { source: 'discord' }
    if (period && period !== 'lifetime') params.event = period
    getAvatars(params)
      .then((list) => {
        if (!active) return
        const map = {}
        for (const a of list || []) map[a.name] = a
        setCommunity(map)
      })
      .catch(() => {})
    return () => {
      active = false
    }
  }, [period])
  return { imageFiles, community }
}

/** A card with the avatar's art behind it, darkened so the text stays readable. */
export default function AvatarArtCard({ name, imageFiles = [], to, className = '', children }) {
  const file = getAvatarImagePath(name, imageFiles)
  const body = (
    <>
      {file && (
        <>
          <div
            aria-hidden="true"
            className="absolute inset-0 bg-cover opacity-60 transition-transform duration-300 group-hover:scale-105"
            style={{ backgroundImage: `url('/avatar-images/${file}')`, backgroundPosition: '50% 25%' }}
          />
          <div aria-hidden="true" className="absolute inset-0 bg-gradient-to-t from-black/90 via-black/60 to-black/30" />
        </>
      )}
      <div className="relative h-full p-4 flex flex-col" style={{ textShadow: '0 1px 4px rgba(0,0,0,0.9)' }}>
        {children}
      </div>
    </>
  )
  const frame = `group relative block overflow-hidden rounded-xl border border-border bg-bg-surface ${className}`
  return to ? (
    <Link to={to} className={`${frame} hover:border-secondary/60 transition-colors`}>{body}</Link>
  ) : (
    <div className={frame}>{body}</div>
  )
}
