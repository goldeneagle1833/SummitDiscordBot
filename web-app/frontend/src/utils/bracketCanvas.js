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
    winnerBg: 'rgba(255, 215, 0, 0.06)',
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
    line: '#b8955a',
    live: '#3653a0',
    avatarBg: '#efe1bf',
  },
}

export const DEFAULT_OPTIONS = {
  format: 'landscape',
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
const MONO_FONT = '"Fira Code", ui-monospace, "Courier New", monospace'

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

  const columns = roundCount + (opts.showChampion ? 1 : 0)

  const { pad, headerH } = frame(width, height)
  const footerH = opts.footer ? Math.round(height * 0.05) : Math.round(pad / 2)
  const roundLabelH = opts.showRoundTitles ? Math.round(height * 0.04) : 0
  const top = headerH + roundLabelH
  const areaH = height - top - footerH
  const areaW = width - pad * 2

  const gapX = Math.max(16, Math.round((areaW / columns) * 0.16))
  const cardW = Math.floor((areaW - gapX * (columns - 1)) / columns)

  // The first round is the tallest column, so it sets the card height.
  const slotH = areaH / slotsIn(first)
  const cardH = Math.max(28, Math.min(Math.round(slotH * 0.82), Math.round(height * 0.12), Math.round(cardW * 0.42)))

  result.card = { width: cardW, height: cardH, rowHeight: cardH / 2 }

  const columnX = (index) => pad + index * (cardW + gapX)
  const centerY = (slot, slots) => top + areaH * ((slot + 0.5) / slots)

  const byKey = new Map()
  for (const round of shown) {
    const slots = slotsIn(round.round)
    for (const match of round.matches) {
      const position = match.position || 1
      const card = {
        x: columnX(round.round - first),
        y: Math.round(centerY(position - 1, slots) - cardH / 2),
        width: cardW,
        height: cardH,
        round: round.round,
        match,
      }
      result.cards.push(card)
      byKey.set(`${round.round}:${position}`, card)
    }
  }

  // Connectors: each card to the one its winner moves into.
  for (const card of result.cards) {
    if (card.round === last) continue
    const parent = byKey.get(`${card.round + 1}:${Math.ceil((card.match.position || 1) / 2)}`)
    if (!parent) continue
    const fromX = card.x + card.width
    const fromY = card.y + card.height / 2
    const toX = parent.x
    const toY = parent.y + parent.height / 2
    const midX = Math.round((fromX + toX) / 2)
    result.lines.push([[fromX, fromY], [midX, fromY], [midX, toY], [toX, toY]])
  }

  if (opts.showRoundTitles) {
    const labelY = headerH + roundLabelH / 2
    for (const round of shown) {
      result.labels.push({ x: columnX(round.round - first) + cardW / 2, y: labelY, text: round.title })
    }
    if (opts.showChampion) {
      result.labels.push({ x: columnX(columns - 1) + cardW / 2, y: labelY, text: 'Champion' })
    }
  }

  if (opts.showChampion) {
    const final = byKey.get(`${last}:1`)
    if (final) {
      const x = columnX(columns - 1)
      const h = Math.round(cardH * 1.1)
      const midY = final.y + cardH / 2
      result.champion = { x, y: Math.round(midY - h / 2), width: cardW, height: h }
      result.lines.push([[final.x + final.width, midY], [x, midY]])
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

/** Corners stay crisp: just enough rounding to take the edge off. */
const CORNER = 2

function drawAvatar(ctx, image, cx, cy, r, theme, faded) {
  ctx.save()
  roundRect(ctx, cx - r, cy - r, r * 2, r * 2, CORNER)
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

  if (opts.showSeeds) {
    // Seeds sit in a fixed, right-aligned column so the names line up.
    ctx.font = `600 ${Math.round(fontSize * 0.72)}px ${MONO_FONT}`
    const w = Math.round(fontSize * 1.3)
    ctx.fillStyle = winner ? theme.accent : theme.muted
    ctx.textAlign = 'right'
    ctx.textBaseline = 'middle'
    ctx.fillText(name && seed != null ? String(seed) : '–', cursor + w, cy + 1)
    cursor += w + Math.round(pad * 0.7)
  }

  if (opts.showAvatars) {
    const r = Math.round(height * 0.3)
    drawAvatar(ctx, name ? avatars?.get(String(userId || '')) : null, cursor + r, cy, r, theme, loser)
    cursor += r * 2 + Math.round(pad * 0.6)
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
  const radius = CORNER
  const complete = match.state === 'complete' || match.state === 'bye'
  const live = opts.highlightLive && match.playable && !complete && match.p1_name && match.p2_name

  ctx.save()
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
    ctx.fillStyle = theme.live
    ctx.fillRect(lx, ly, w, h)
    ctx.fillStyle = theme.panel
    ctx.textAlign = 'center'
    ctx.textBaseline = 'middle'
    ctx.fillText(label, lx + w / 2, ly + h / 2 + 1)
  }
}

function drawChampion(ctx, box, champion, theme, avatars) {
  const { x, y, width, height } = box
  roundRect(ctx, x, y, width, height, CORNER)
  ctx.fillStyle = theme.panel
  ctx.fill()
  ctx.strokeStyle = theme.panelBorder
  ctx.lineWidth = 1
  ctx.stroke()
  // A heavy gold rule down the left edge marks the winner, as on the site.
  ctx.fillStyle = theme.accent
  ctx.fillRect(x, y, Math.max(4, Math.round(height * 0.06)), height)

  const pad = Math.round(height * 0.16)
  const r = Math.round(height * 0.3)
  const cy = y + height / 2
  let cursor = x + pad
  drawAvatar(ctx, champion ? avatars?.get(String(champion.user_id || '')) : null, cursor + r, cy, r, theme)
  cursor += r * 2 + pad

  const maxW = x + width - pad - cursor
  ctx.textAlign = 'left'
  ctx.textBaseline = 'alphabetic'
  ctx.fillStyle = theme.muted
  ctx.font = `700 ${Math.round(height * 0.16)}px ${BODY_FONT}`
  ctx.fillText(fitText(ctx, 'CHAMPION', maxW), cursor, cy - Math.round(height * 0.06))
  ctx.fillStyle = champion ? theme.accent : theme.dim
  ctx.font = `700 ${Math.round(height * 0.24)}px ${BODY_FONT}`
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
  ctx.fillRect(pad, pad + titleSize * 1.2, Math.round(titleSize * 1.2), Math.max(3, Math.round(titleSize * 0.06)))

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
