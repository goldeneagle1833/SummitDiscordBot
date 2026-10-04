/**
 * Draws a bracket as a shareable image on a <canvas>.
 *
 * The layout is worked out separately from the drawing (`layoutBracket`) so
 * the geometry can be tested without a real canvas. Matches are placed by
 * their `position` within the round, not their index, so a first round with
 * byes keeps every match beside the round-two match it feeds.
 */

export const FORMATS = {
  landscape: { label: 'Landscape 1920×1080', width: 1920, height: 1080 },
  square: { label: 'Square 1080×1080', width: 1080, height: 1080 },
  portrait: { label: 'Portrait 1080×1350', width: 1080, height: 1350 },
  story: { label: 'Story 1080×1920', width: 1080, height: 1920 },
  wide: { label: 'Wide 2560×1440', width: 2560, height: 1440 },
}

export const LAYOUTS = {
  mirrored: 'Mirrored (final in the middle)',
  ltr: 'Left to right',
}

export const THEMES = {
  summit: {
    label: 'Summit night',
    bg: ['#1b2a55', '#0b1124'],
    panel: '#16213f',
    panelBorder: '#2c4790',
    text: '#f0f6fc',
    muted: '#a8bcf0',
    dim: '#5d6b8f',
    accent: '#ffd700',
    winnerBg: 'rgba(255, 215, 0, 0.12)',
    seedBg: '#22326a',
    line: '#4a68b8',
    live: '#58a6ff',
    avatarBg: '#22326a',
  },
  midnight: {
    label: 'Midnight',
    bg: ['#161b22', '#0d1117'],
    panel: '#161b22',
    panelBorder: '#30363d',
    text: '#f0f6fc',
    muted: '#8b949e',
    dim: '#484f58',
    accent: '#2a9c4a',
    winnerBg: 'rgba(42, 156, 74, 0.14)',
    seedBg: '#21262d',
    line: '#484f58',
    live: '#ffd700',
    avatarBg: '#21262d',
  },
  parchment: {
    label: 'Parchment',
    bg: ['#f6ecd2', '#e6d3a8'],
    panel: '#fffaf0',
    panelBorder: '#c9ad74',
    text: '#2b2112',
    muted: '#6e5b3a',
    dim: '#a8977a',
    accent: '#9a6b00',
    winnerBg: 'rgba(154, 107, 0, 0.12)',
    seedBg: '#efe1bf',
    line: '#b8955a',
    live: '#3653a0',
    avatarBg: '#efe1bf',
  },
}

export const DEFAULT_OPTIONS = {
  format: 'landscape',
  layout: 'mirrored',
  theme: 'summit',
  startRound: null,
  title: '',
  subtitle: '',
  showSeeds: true,
  showAvatars: true,
  showChampion: true,
  highlightLive: true,
  showRoundTitles: true,
  footer: 'sorcererssummit.com',
}

/** Padding and title size; the header is sized from them so text never overlaps the tree. */
function frame(width, height) {
  const pad = Math.round(width * 0.035)
  const titleSize = Math.round(Math.min(height * 0.06, width * 0.045))
  return { pad, titleSize, headerH: Math.round(pad + titleSize * 2.3) }
}

const DISPLAY_FONT = 'Almendra, Georgia, "Times New Roman", serif'
const BODY_FONT = 'Figtree, -apple-system, "Segoe UI", sans-serif'

/** "Quarterfinals in progress · 5/7 matches played", or how it ended. */
export function describeProgress(data) {
  const rounds = data?.rounds || []
  const matches = rounds.flatMap((r) => r.matches)
  const players = data?.entrants?.length || 0
  const parts = []
  if (players) parts.push(`${players} players`)

  if (data?.bracket?.status === 'draft') {
    parts.push('draft seeding')
  } else if (data?.champion || data?.bracket?.status === 'complete') {
    parts.push('final results')
  } else {
    const live = rounds.find((r) =>
      r.matches.some((m) => m.playable && m.state !== 'complete'),
    )
    if (live) parts.push(`${live.title} in progress`)
    const played = matches.filter((m) => m.state === 'complete').length
    if (matches.length) parts.push(`${played}/${matches.length} matches played`)
  }
  return parts.join(' · ')
}

/** The rounds the graphic shows, from `startRound` (a round number) on. */
export function visibleRounds(rounds = [], startRound = null) {
  if (!startRound) return rounds
  const kept = rounds.filter((r) => r.round >= startRound)
  return kept.length ? kept : rounds
}

/**
 * Where every match card, connector and label goes, in canvas pixels.
 *
 * Returns `{ cards, lines, labels, champion, card }`: `cards` carry the match
 * they draw, `lines` are polylines from a match to the one it feeds.
 */
export function layoutBracket(rounds, options = {}) {
  const opts = { ...DEFAULT_OPTIONS, ...options }
  const { width, height } = FORMATS[opts.format] || FORMATS.landscape
  const shown = visibleRounds(rounds, opts.startRound)
  const result = { width, height, cards: [], lines: [], labels: [], champion: null, card: null }
  if (!shown.length) return result

  const first = shown[0].round
  const last = shown[shown.length - 1].round
  const roundCount = last - first + 1
  // Slots in a round of the shown tree: the last one has a single match.
  const slotsIn = (round) => 2 ** (last - round)

  const mirrored = opts.layout === 'mirrored' && roundCount > 1
  const withChampionColumn = opts.showChampion && !mirrored
  const columns = mirrored
    ? roundCount * 2 - 1
    : roundCount + (withChampionColumn ? 1 : 0)

  const { pad, headerH } = frame(width, height)
  const footerH = opts.footer ? Math.round(height * 0.05) : Math.round(pad / 2)
  const roundLabelH = opts.showRoundTitles ? Math.round(height * 0.04) : 0
  const top = headerH + roundLabelH
  const areaH = height - top - footerH
  const areaW = width - pad * 2

  const gapX = Math.max(16, Math.round((areaW / columns) * 0.16))
  const cardW = Math.floor((areaW - gapX * (columns - 1)) / columns)

  // The tallest column sets the card height: in the mirrored layout each side
  // holds half the first round.
  const tallest = mirrored ? slotsIn(first) / 2 : slotsIn(first)
  const slotH = areaH / tallest
  const cardH = Math.max(28, Math.min(Math.round(slotH * 0.82), Math.round(height * 0.12), Math.round(cardW * 0.42)))

  result.card = { width: cardW, height: cardH, rowHeight: cardH / 2 }

  const columnX = (index) => pad + index * (cardW + gapX)

  /** Column index and side for a match, and its vertical slot. */
  const place = (round, position) => {
    const k = round - first
    const slots = slotsIn(round)
    if (!mirrored) {
      return { column: k, side: 'left', slot: position - 1, slots }
    }
    if (round === last) {
      return { column: roundCount - 1, side: 'center', slot: 0, slots: 1 }
    }
    const half = slots / 2
    if (position <= half) {
      return { column: k, side: 'left', slot: position - 1, slots: half }
    }
    return { column: columns - 1 - k, side: 'right', slot: position - 1 - half, slots: half }
  }

  const centerY = (slot, slots) => top + areaH * ((slot + 0.5) / slots)

  const byKey = new Map()
  for (const round of shown) {
    for (const match of round.matches) {
      const where = place(round.round, match.position || 1)
      const x = columnX(where.column)
      const cy = centerY(where.slot, where.slots)
      const card = {
        x,
        y: Math.round(cy - cardH / 2),
        width: cardW,
        height: cardH,
        side: where.side,
        round: round.round,
        match,
      }
      result.cards.push(card)
      byKey.set(`${round.round}:${match.position || 1}`, card)
    }
  }

  // Connectors: each card to the one its winner moves into.
  for (const card of result.cards) {
    if (card.round === last) continue
    const parent = byKey.get(`${card.round + 1}:${Math.ceil((card.match.position || 1) / 2)}`)
    if (!parent) continue
    const fromY = card.y + card.height / 2
    const toY =
      parent.side === 'center'
        ? parent.y + (card.side === 'left' ? cardH * 0.25 : cardH * 0.75)
        : parent.y + parent.height / 2
    if (card.side === 'right') {
      const fromX = card.x
      const toX = parent.x + parent.width
      const midX = Math.round((fromX + toX) / 2)
      result.lines.push([[fromX, fromY], [midX, fromY], [midX, toY], [toX, toY]])
    } else {
      const fromX = card.x + card.width
      const toX = parent.x
      const midX = Math.round((fromX + toX) / 2)
      result.lines.push([[fromX, fromY], [midX, fromY], [midX, toY], [toX, toY]])
    }
  }

  if (opts.showRoundTitles) {
    const labelY = headerH + roundLabelH / 2
    for (const round of shown) {
      const k = round.round - first
      const columnsFor = mirrored && round.round !== last ? [k, columns - 1 - k] : [mirrored ? roundCount - 1 : k]
      for (const column of columnsFor) {
        result.labels.push({ x: columnX(column) + cardW / 2, y: labelY, text: round.title })
      }
    }
    if (withChampionColumn) {
      result.labels.push({ x: columnX(columns - 1) + cardW / 2, y: labelY, text: 'Champion' })
    }
  }

  if (opts.showChampion) {
    const final = byKey.get(`${last}:1`)
    if (final) {
      if (withChampionColumn) {
        const x = columnX(columns - 1)
        const h = Math.round(cardH * 1.1)
        result.champion = { x, y: Math.round(final.y + cardH / 2 - h / 2), width: cardW, height: h }
        result.lines.push([
          [final.x + final.width, final.y + cardH / 2],
          [x, final.y + cardH / 2],
        ])
      } else {
        // Above the final there is only open space, so the box can run wider
        // than a column and keep the winner's name readable.
        const w = Math.round(cardW * 1.8)
        const h = Math.round(cardH * 1.3)
        const y = Math.max(top, final.y - h - Math.round(cardH * 0.5))
        result.champion = { x: Math.round(final.x + cardW / 2 - w / 2), y, width: w, height: h }
      }
    }
  }

  return result
}

function roundRect(ctx, x, y, w, h, r) {
  ctx.beginPath()
  ctx.moveTo(x + r, y)
  ctx.arcTo(x + w, y, x + w, y + h, r)
  ctx.arcTo(x + w, y + h, x, y + h, r)
  ctx.arcTo(x, y + h, x, y, r)
  ctx.arcTo(x, y, x + w, y, r)
  ctx.closePath()
}

function fitText(ctx, text, maxWidth) {
  if (!text) return ''
  if (ctx.measureText(text).width <= maxWidth) return text
  let cut = text
  while (cut.length > 1 && ctx.measureText(`${cut}…`).width > maxWidth) {
    cut = cut.slice(0, -1)
  }
  return `${cut}…`
}

function drawAvatar(ctx, image, cx, cy, r, theme, faded) {
  ctx.save()
  ctx.beginPath()
  ctx.arc(cx, cy, r, 0, Math.PI * 2)
  ctx.closePath()
  ctx.fillStyle = theme.avatarBg
  ctx.fill()
  if (image) {
    ctx.clip()
    if (faded) ctx.globalAlpha = 0.45
    ctx.drawImage(image, cx - r, cy - r, r * 2, r * 2)
  }
  ctx.restore()
}

function drawSide(ctx, { x, y, width, height }, side, theme, opts, avatars) {
  const { name, seed, userId, winner, loser, fromBye } = side
  const pad = Math.round(height * 0.32)
  const fontSize = Math.max(11, Math.round(height * 0.46))
  let cursor = x + pad
  const cy = y + height / 2

  if (winner) {
    ctx.fillStyle = theme.winnerBg
    ctx.fillRect(x, y, width, height)
    ctx.fillStyle = theme.accent
    ctx.fillRect(x, y, Math.max(3, Math.round(height * 0.08)), height)
  }

  if (opts.showAvatars) {
    const r = Math.round(height * 0.32)
    drawAvatar(ctx, name ? avatars?.get(String(userId || '')) : null, cursor + r, cy, r, theme, loser)
    cursor += r * 2 + Math.round(pad * 0.6)
  }

  if (opts.showSeeds && seed != null && name) {
    ctx.font = `600 ${Math.round(fontSize * 0.72)}px ${BODY_FONT}`
    const label = String(seed)
    const w = Math.max(Math.round(height * 0.62), ctx.measureText(label).width + 10)
    const h = Math.round(height * 0.56)
    ctx.fillStyle = theme.seedBg
    roundRect(ctx, cursor, cy - h / 2, w, h, Math.round(h * 0.25))
    ctx.fill()
    ctx.fillStyle = winner ? theme.text : theme.muted
    ctx.textAlign = 'center'
    ctx.textBaseline = 'middle'
    ctx.fillText(label, cursor + w / 2, cy + 1)
    cursor += w + Math.round(pad * 0.6)
  }

  const markW = winner ? Math.round(fontSize * 1.4) : fromBye ? Math.round(fontSize * 2.2) : 0
  ctx.textAlign = 'left'
  ctx.textBaseline = 'middle'
  ctx.font = `${winner ? 700 : 500} ${fontSize}px ${BODY_FONT}`
  ctx.fillStyle = name ? (loser ? theme.dim : theme.text) : theme.dim
  const text = fitText(ctx, name || 'TBD', x + width - pad - markW - cursor)
  ctx.fillText(text, cursor, cy + 1)

  if (loser && name) {
    const w = ctx.measureText(text).width
    ctx.strokeStyle = theme.dim
    ctx.lineWidth = Math.max(1, Math.round(height * 0.03))
    ctx.beginPath()
    ctx.moveTo(cursor, cy + 1)
    ctx.lineTo(cursor + w, cy + 1)
    ctx.stroke()
  }

  ctx.textAlign = 'right'
  if (winner) {
    ctx.font = `700 ${Math.round(fontSize * 0.8)}px ${BODY_FONT}`
    ctx.fillStyle = theme.accent
    ctx.fillText('W', x + width - pad, cy + 1)
  } else if (fromBye && name) {
    ctx.font = `600 ${Math.round(fontSize * 0.62)}px ${BODY_FONT}`
    ctx.fillStyle = theme.muted
    ctx.fillText('BYE', x + width - pad, cy + 1)
  }
}

function drawCard(ctx, card, theme, opts, avatars) {
  const { x, y, width, height, match } = card
  const radius = Math.round(height * 0.12)
  const complete = match.state === 'complete' || match.state === 'bye'
  const live = opts.highlightLive && match.playable && !complete && match.p1_name && match.p2_name

  ctx.save()
  ctx.shadowColor = 'rgba(0, 0, 0, 0.25)'
  ctx.shadowBlur = Math.round(height * 0.15)
  ctx.shadowOffsetY = Math.round(height * 0.04)
  roundRect(ctx, x, y, width, height, radius)
  ctx.fillStyle = theme.panel
  ctx.fill()
  ctx.restore()

  ctx.save()
  roundRect(ctx, x, y, width, height, radius)
  ctx.clip()
  const row = height / 2
  const p1Wins = complete && String(match.winner_seed) === String(match.p1_seed)
  const p2Wins = complete && String(match.winner_seed) === String(match.p2_seed)
  drawSide(ctx, { x, y, width, height: row }, {
    name: match.p1_name,
    seed: match.p1_seed,
    userId: match.p1_user_id,
    winner: p1Wins,
    loser: p2Wins,
    fromBye: match.p1_from_bye,
  }, theme, opts, avatars)
  drawSide(ctx, { x, y: y + row, width, height: row }, {
    name: match.p2_name,
    seed: match.p2_seed,
    userId: match.p2_user_id,
    winner: p2Wins,
    loser: p1Wins,
    fromBye: match.p2_from_bye,
  }, theme, opts, avatars)
  ctx.restore()

  ctx.strokeStyle = theme.panelBorder
  ctx.lineWidth = 1
  ctx.beginPath()
  ctx.moveTo(x + 1, y + row)
  ctx.lineTo(x + width - 1, y + row)
  ctx.stroke()

  roundRect(ctx, x + 0.5, y + 0.5, width - 1, height - 1, radius)
  ctx.strokeStyle = live ? theme.live : theme.panelBorder
  ctx.lineWidth = live ? Math.max(2, Math.round(height * 0.04)) : 1
  ctx.stroke()

  if (live) {
    const size = Math.max(9, Math.round(height * 0.17))
    ctx.font = `700 ${size}px ${BODY_FONT}`
    const label = 'LIVE'
    const w = ctx.measureText(label).width + size
    const h = Math.round(size * 1.5)
    const lx = x + width - w - Math.round(height * 0.1)
    const ly = y - h / 2
    roundRect(ctx, lx, ly, w, h, h / 2)
    ctx.fillStyle = theme.live
    ctx.fill()
    ctx.fillStyle = theme.panel
    ctx.textAlign = 'center'
    ctx.textBaseline = 'middle'
    ctx.fillText(label, lx + w / 2, ly + h / 2 + 1)
  }
}

function drawChampion(ctx, box, champion, theme, avatars) {
  const { x, y, width, height } = box
  const radius = Math.round(height * 0.12)
  roundRect(ctx, x, y, width, height, radius)
  ctx.fillStyle = theme.panel
  ctx.fill()
  ctx.lineWidth = Math.max(2, Math.round(height * 0.035))
  ctx.strokeStyle = theme.accent
  ctx.stroke()

  const pad = Math.round(height * 0.16)
  const r = Math.round(height * 0.3)
  const cy = y + height / 2
  let cursor = x + pad
  drawAvatar(ctx, champion ? avatars?.get(String(champion.user_id || '')) : null, cursor + r, cy, r, theme)
  ctx.strokeStyle = theme.accent
  ctx.lineWidth = Math.max(2, Math.round(r * 0.1))
  ctx.beginPath()
  ctx.arc(cursor + r, cy, r, 0, Math.PI * 2)
  ctx.stroke()
  cursor += r * 2 + pad

  const maxW = x + width - pad - cursor
  ctx.textAlign = 'left'
  ctx.textBaseline = 'alphabetic'
  ctx.fillStyle = theme.muted
  ctx.font = `700 ${Math.round(height * 0.16)}px ${BODY_FONT}`
  ctx.fillText(fitText(ctx, '🏆 CHAMPION', maxW), cursor, cy - Math.round(height * 0.06))
  ctx.fillStyle = champion ? theme.accent : theme.dim
  ctx.font = `700 ${Math.round(height * 0.24)}px ${DISPLAY_FONT}`
  ctx.textBaseline = 'top'
  ctx.fillText(fitText(ctx, champion?.display_name || 'To be decided', maxW), cursor, cy + Math.round(height * 0.02))
}

/**
 * Paint the whole graphic. `avatars` maps user_id to a loaded image; players
 * without one get a plain circle.
 */
export function drawBracket(ctx, data, options = {}, avatars = new Map()) {
  const opts = { ...DEFAULT_OPTIONS, ...options }
  const theme = THEMES[opts.theme] || THEMES.summit
  const layout = layoutBracket(data?.rounds || [], opts)
  const { width, height } = layout

  const gradient = ctx.createLinearGradient(0, 0, width * 0.4, height)
  gradient.addColorStop(0, theme.bg[0])
  gradient.addColorStop(1, theme.bg[1])
  ctx.fillStyle = gradient
  ctx.fillRect(0, 0, width, height)

  const { pad, titleSize } = frame(width, height)
  const title = opts.title || data?.bracket?.name || 'Bracket'
  // A blank subtitle means "say how far along it is".
  const subtitle = opts.subtitle || describeProgress(data)
  ctx.textAlign = 'left'
  ctx.textBaseline = 'alphabetic'
  ctx.fillStyle = theme.text
  ctx.font = `700 ${titleSize}px ${DISPLAY_FONT}`
  ctx.fillText(fitText(ctx, title, width - pad * 2), pad, pad + titleSize * 0.9)

  ctx.fillStyle = theme.accent
  ctx.fillRect(pad, pad + titleSize * 1.2, Math.round(titleSize * 2.2), Math.max(3, Math.round(titleSize * 0.07)))

  if (subtitle) {
    ctx.fillStyle = theme.muted
    ctx.font = `500 ${Math.round(titleSize * 0.42)}px ${BODY_FONT}`
    ctx.fillText(fitText(ctx, subtitle, width - pad * 2), pad, pad + titleSize * 1.85)
  }

  if (!layout.cards.length) {
    ctx.fillStyle = theme.muted
    ctx.textAlign = 'center'
    ctx.font = `500 ${Math.round(titleSize * 0.5)}px ${BODY_FONT}`
    ctx.fillText('This bracket has no matches yet.', width / 2, height / 2)
    return layout
  }

  ctx.strokeStyle = theme.line
  ctx.lineWidth = Math.max(2, Math.round(layout.card.height * 0.03))
  ctx.lineJoin = 'round'
  for (const line of layout.lines) {
    ctx.beginPath()
    line.forEach(([x, y], i) => (i ? ctx.lineTo(x, y) : ctx.moveTo(x, y)))
    ctx.stroke()
  }

  ctx.fillStyle = theme.muted
  ctx.textAlign = 'center'
  ctx.textBaseline = 'middle'
  ctx.font = `700 ${Math.max(10, Math.round(Math.min(height * 0.016, layout.card.width * 0.08)))}px ${BODY_FONT}`
  for (const label of layout.labels) {
    ctx.fillText(fitText(ctx, label.text.toUpperCase(), layout.card.width), label.x, label.y)
  }

  for (const card of layout.cards) drawCard(ctx, card, theme, opts, avatars)

  if (layout.champion) drawChampion(ctx, layout.champion, data?.champion, theme, avatars)

  if (opts.footer) {
    ctx.fillStyle = theme.dim
    ctx.textAlign = 'right'
    ctx.textBaseline = 'middle'
    ctx.font = `600 ${Math.max(12, Math.round(height * 0.018))}px ${BODY_FONT}`
    ctx.fillText(opts.footer, width - pad, height - Math.round(height * 0.025))
  }

  return layout
}
