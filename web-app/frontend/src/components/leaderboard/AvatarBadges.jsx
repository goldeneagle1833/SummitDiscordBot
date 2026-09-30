import { Link } from 'react-router-dom'

/** The season's Top Players page, opened on this avatar. */
export function topPlayersLink(avatar) {
  return `/avatars/top-players?avatar=${encodeURIComponent(avatar)}&event=current`
}

/**
 * Small avatar portraits for the current season's top player with each avatar.
 * `withLabel` prints "Top <avatar> this season" beside each portrait (the home
 * leaderboard's Badge column); otherwise the text is only a tooltip.
 */
export default function AvatarBadges({ badges, withLabel = false }) {
  if (!badges?.length) return null
  if (withLabel) {
    return (
      <span className="flex flex-col gap-1">
        {badges.map((b) => (
          <Link
            key={b.avatar}
            to={topPlayersLink(b.avatar)}
            title={`Top ${b.avatar} player this season (${b.wins}-${b.losses})`}
            className="inline-flex items-center gap-2 text-xs text-text-muted hover:text-secondary transition-colors"
          >
            <BadgeImage badge={b} />
            <span>Top {b.avatar} this season</span>
          </Link>
        ))}
      </span>
    )
  }
  return (
    <span className="inline-flex items-center gap-1 ml-2 align-middle">
      {badges.map((b) => {
        const label = `Top ${b.avatar} player this season (${b.wins}-${b.losses})`
        return (
          <Link
            key={b.avatar}
            to={topPlayersLink(b.avatar)}
            title={label}
            aria-label={label}
            className="inline-flex shrink-0 rounded-full ring-1 ring-secondary/60 hover:ring-2 hover:ring-secondary transition-shadow"
          >
            <BadgeImage badge={b} />
          </Link>
        )
      })}
    </span>
  )
}

/**
 * Avatar-mode leaderboard cell: the avatar name, and under it the entry's
 * place among everyone on that avatar this season (left-aligned), with the
 * avatar's portrait to the right of both lines. Links to that avatar's Top
 * Players page.
 */
export function AvatarCell({ avatar, rank, imgSrc = null }) {
  const place = rank ? `#${rank.place} of ${rank.of} ${avatar} player${rank.of === 1 ? '' : 's'}` : null
  return (
    <Link
      to={topPlayersLink(avatar)}
      title={place ? `${place} this season` : avatar}
      className="group inline-flex items-center gap-3"
    >
      <span className="text-left min-w-[12rem]">
        <span className="block text-text-muted group-hover:text-secondary transition-colors">{avatar}</span>
        {place && (
          <span className={`block text-xs ${rank.place === 1 ? 'text-secondary' : 'text-text-muted'}`}>
            {place}
          </span>
        )}
      </span>
      <BadgeImage badge={{ avatar, imgSrc }} />
    </Link>
  )
}

function BadgeImage({ badge }) {
  return badge.imgSrc ? (
    <img
      src={badge.imgSrc}
      alt=""
      width={26}
      height={26}
      loading="lazy"
      className="w-[26px] h-[26px] shrink-0 rounded-full object-cover object-top ring-1 ring-secondary/60"
    />
  ) : (
    <span className="w-[26px] h-[26px] shrink-0 rounded-full bg-bg-elevated text-[10px] font-bold text-secondary inline-flex items-center justify-center ring-1 ring-secondary/60">
      {badge.avatar.replace(/^Avatar of /i, '').slice(0, 2)}
    </span>
  )
}
