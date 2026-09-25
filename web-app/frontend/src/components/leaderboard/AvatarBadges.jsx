import { Link } from 'react-router-dom'

/**
 * Small avatar portraits shown next to a player's name on the home leaderboard,
 * one per avatar they are the current season's top player with.
 */
export default function AvatarBadges({ badges }) {
  if (!badges?.length) return null
  return (
    <span className="inline-flex items-center gap-1 ml-2 align-middle">
      {badges.map((b) => {
        const label = `Top ${b.avatar} player this season (${b.wins}-${b.losses})`
        return (
          <Link
            key={b.avatar}
            to={`/avatar/${encodeURIComponent(b.avatar)}`}
            title={label}
            aria-label={label}
            className="inline-flex shrink-0 rounded-full ring-1 ring-secondary/60 hover:ring-2 hover:ring-secondary transition-shadow"
          >
            {b.imgSrc ? (
              <img
                src={b.imgSrc}
                alt=""
                width={26}
                height={26}
                loading="lazy"
                className="w-[26px] h-[26px] rounded-full object-cover object-top"
              />
            ) : (
              <span className="w-[26px] h-[26px] rounded-full bg-bg-elevated text-[10px] font-bold text-secondary inline-flex items-center justify-center">
                {b.avatar.replace(/^Avatar of /i, '').slice(0, 2)}
              </span>
            )}
          </Link>
        )
      })}
    </span>
  )
}
