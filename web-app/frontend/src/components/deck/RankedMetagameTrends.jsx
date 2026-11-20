import { useEffect, useMemo, useState } from 'react'
import { get } from '@/api/client'
import DataReleaseNote from '@/components/ui/DataReleaseNote'

// Monthly percentages are based on classified match-time deck appearances, not
// the merged deck list shown on the archetype cards. Missing deck data is
// disclosed as coverage instead of being guessed or silently counted as zero.
const MIN_MONTHLY_APPEARANCES = 100
const THRESHOLDS = [1, 2, 3, 5, 7, 10]
const COLORS = [
  '#78c4f5', '#efb34c', '#b8a3ef', '#62c6a3', '#ef7896',
  '#dfb876', '#6fb9bf', '#c58dd6', '#a0c274', '#f0916a',
  '#7aa7ed', '#e3a5bb', '#b1bbff', '#b7d976', '#cda576',
]

function monthLabel(month) {
  const [year, part] = month.split('-').map(Number)
  return new Date(Date.UTC(year, part - 1, 1)).toLocaleString('en-US', {
    month: 'short', year: '2-digit', timeZone: 'UTC',
  })
}

function percentage(month, id) {
  if (!month || month.classifiedAppearances < MIN_MONTHLY_APPEARANCES) return null
  return (month.counts[id] || 0) * 100 / month.classifiedAppearances
}

function TrendPlot({ months, lines, hidden, colorById }) {
  const visible = lines.filter((line) => !hidden.includes(line.id))
  const allValues = visible.flatMap((line) => months.map((month) => percentage(month, line.id)))
    .filter((value) => value !== null)
  const yMax = Math.min(100, Math.max(10, Math.ceil(Math.max(0, ...allValues) * 1.12 / 5) * 5))
  const W = 920, H = 340, left = 44, right = 14, top = 22, bottom = 46
  const x = (i) => left + i * (W - left - right) / Math.max(1, months.length - 1)
  const y = (n) => top + (yMax - n) * (H - top - bottom) / yMax
  const ticks = [0, 1, 2, 3, 4].map((i) => (yMax * i / 4))
  const linePath = (id) => {
    let drawing = false
    return months.map((month, i) => {
      const value = percentage(month, id)
      if (value == null) { drawing = false; return '' }
      const command = drawing ? 'L' : 'M'
      drawing = true
      return `${command}${x(i).toFixed(1)},${y(value).toFixed(1)}`
    }).join(' ')
  }

  if (months.length === 0) return <p className="text-sm text-text-muted">No ranked matches found for the Gothic era.</p>
  return (
    <div className="overflow-x-auto" role="region" aria-label="Ranked archetype popularity over time" tabIndex={0}>
      <svg viewBox={`0 0 ${W} ${H}`} className="block w-full min-w-[560px] h-auto" role="img"
        aria-label="Monthly percentage of classified ranked deck appearances for selected archetypes">
        {ticks.map((tick) => (
          <g key={tick}>
            <line x1={left} x2={W - right} y1={y(tick)} y2={y(tick)} stroke="#424957" strokeOpacity="0.75" />
            <text x={left - 9} y={y(tick) + 4} fill="#abb2bd" textAnchor="end" fontSize="12">
              {Number.isInteger(tick) ? tick : tick.toFixed(1)}%
            </text>
          </g>
        ))}
        {months.map((month, index) => (
          <text key={month.month} x={x(index)} y={H - 15} fill="#abb2bd" fontSize="12"
            textAnchor={index === 0 ? 'start' : index === months.length - 1 ? 'end' : 'middle'}>
            {monthLabel(month.month)}
          </text>
        ))}
        {visible.map((line) => (
          <g key={line.id}>
            <path d={linePath(line.id)} stroke={colorById[line.id]} fill="none" strokeWidth="2.5"
              strokeLinejoin="round" strokeLinecap="round" />
            {months.map((month, i) => {
              const share = percentage(month, line.id)
              if (share === null) return null
              return (
                <circle key={month.month} cx={x(i)} cy={y(share)} r="3" fill={colorById[line.id]}>
                  <title>{`${line.name} · ${monthLabel(month.month)}: ${share.toFixed(1)}% (${month.counts[line.id] || 0} of ${month.classifiedAppearances} classified appearances)`}</title>
                </circle>
              )
            })}
          </g>
        ))}
      </svg>
    </div>
  )
}

export default function RankedMetagameTrends({ tournamentGroups = [] }) {
  const [expanded, setExpanded] = useState(false)
  const [report, setReport] = useState(null)
  const [loading, setLoading] = useState(false)
  const [error, setError] = useState('')
  const [threshold, setThreshold] = useState(5)
  const [added, setAdded] = useState([])
  const [hidden, setHidden] = useState([])

  useEffect(() => {
    if (!expanded || report || loading || error) return undefined
    let active = true
    setLoading(true)
    get('/api/deck-archetypes/trends')
      .then((value) => { if (active) setReport(value) })
      .catch((err) => { if (active) setError(err.message || 'Trend data is unavailable') })
      .finally(() => { if (active) setLoading(false) })
    return () => { active = false; setLoading(false) }
  }, [expanded, report, error])

  const months = report?.months || []
  const allArchetypes = report?.archetypes || []
  const eligible = useMemo(() => allArchetypes.filter((archetype) => months.some((month) => {
    const share = percentage(month, archetype.id)
    return share !== null && share >= threshold
  })), [allArchetypes, months, threshold])
  const qualifiedIds = new Set(eligible.map((arch) => arch.id))
  const lines = allArchetypes.filter((arch) => qualifiedIds.has(arch.id) || added.includes(arch.id))
  const colorById = Object.fromEntries(allArchetypes.map((arch, i) => [arch.id, COLORS[i % COLORS.length]]))
  const prizes = Object.fromEntries(tournamentGroups.map((group) => [group.id, group]))
  const selectionOptions = allArchetypes.filter((arch) => !lines.some((line) => line.id === arch.id))

  return (
    <section className="rounded-lg border border-border bg-bg-surface mb-5" aria-label="Metagame Evolution">
      <button type="button" aria-expanded={expanded} aria-controls="metagame-evolution-body"
        className="w-full flex items-center justify-between gap-3 p-4 text-left hover:bg-bg-raised/40 transition-colors"
        onClick={() => setExpanded((current) => !current)}>
        <span>
          <span className="block text-lg font-semibold text-text-primary">Metagame Evolution</span>
          <span className="block text-xs text-text-muted mt-1">Monthly ranked-play popularity throughout the Gothic era</span>
        </span>
        <span className="text-secondary text-lg shrink-0" aria-hidden="true">{expanded ? '−' : '+'}</span>
      </button>
      {expanded && (
        <div id="metagame-evolution-body" className="border-t border-border p-4">
          {loading && <p className="text-sm text-text-muted">Loading monthly ranked statistics…</p>}
          {error && (
            <div className="flex flex-wrap gap-3 items-center">
              <p className="text-sm text-red-400">{error}</p>
              <button className="text-sm text-secondary underline" onClick={() => setError('')}>Try again</button>
            </div>
          )}
          {report && (
            <>
              <div className="flex flex-wrap items-end gap-4 mb-4">
                <label className="text-xs text-text-muted flex flex-col gap-1">
                  Minimum peak monthly share
                  <select className="bg-bg-raised text-sm border border-border rounded px-3 py-2 text-text-primary"
                    value={threshold} onChange={(event) => setThreshold(Number(event.target.value))}>
                    {THRESHOLDS.map((value) => <option key={value} value={value}>{value}%</option>)}
                  </select>
                </label>
                <label className="text-xs text-text-muted flex flex-col gap-1 flex-1 min-w-[200px] max-w-xs">
                  Add an archetype manually
                  <select className="bg-bg-raised text-sm border border-border rounded px-3 py-2 text-text-primary"
                    value="" onChange={(event) => {
                      if (event.target.value) setAdded((old) => [...new Set([...old, event.target.value])])
                    }}>
                    <option value="">Choose archetype…</option>
                    {selectionOptions.map((arch) => (
                      <option key={arch.id} value={arch.id}>{arch.name}</option>
                    ))}
                  </select>
                </label>
                <span className="text-xs text-text-muted pb-2">{lines.length} qualifying or selected archetypes</span>
              </div>
              {lines.length ? (
                <>
                  <TrendPlot months={months} lines={lines} hidden={hidden} colorById={colorById} />
                  <div className="flex flex-wrap gap-2 mt-3" aria-label="Show or hide archetype lines">
                    {lines.map((arch) => {
                      const isHidden = hidden.includes(arch.id)
                      const prize = prizes[arch.id]
                      return (
                        <button key={arch.id} type="button" aria-pressed={!isHidden}
                          className={`text-xs rounded border px-2.5 py-1.5 ${isHidden ? 'opacity-40 border-border' : 'border-border bg-bg-raised'}`}
                          onClick={() => setHidden((old) => isHidden ? old.filter((id) => id !== arch.id) : [...old, arch.id])}>
                          <span style={{ color: colorById[arch.id] }} aria-hidden="true">●</span>{' '}
                          {arch.name}
                          {prize?.wins > 0 ? <span title="Tournament winner" className="text-yellow-400"> ★</span>
                            : prize?.top8 > 0 ? <span title="Top 8 finisher" className="text-gray-300"> ★</span> : null}
                        </button>
                      )
                    })}
                  </div>
                </>
              ) : <p className="text-sm text-text-muted">No archetype reaches the selected threshold in a month with enough known deck appearances. Lower the threshold or add one manually.</p>}
              <p className="mt-4 text-xs text-text-muted leading-relaxed">
                Each line shows an archetype's share of ranked deck appearances with a known Avatar and element combination.
                An archetype is shown across its full history once it crosses the threshold in any eligible month.
                Months with fewer than {MIN_MONTHLY_APPEARANCES} classified appearances are left blank rather than treated as zero.
                Tournament stars indicate historical results in the page's current tournament data.
              </p>
              <div className="mt-3 border-t border-border pt-3 text-xs text-text-muted">
                <DataReleaseNote className="mb-2" />
                <p>
                  <strong className="text-text-primary">Data coverage:</strong>{' '}
                  {report.classifiedAppearances.toLocaleString()} of {report.possibleAppearances.toLocaleString()} possible ranked deck appearances classified ({report.coverage}%).
                  Missing or incomplete historical deck data is excluded from the percentage denominator.
                </p>
                <div className="mt-2 flex flex-wrap gap-x-4 gap-y-1">
                  {months.map((month) => (
                    <span key={month.month} title={`${month.matches.toLocaleString()} matches; ${month.classifiedAppearances.toLocaleString()} classified of ${month.possibleAppearances.toLocaleString()} possible deck appearances`}>
                      {monthLabel(month.month)}: {month.coverage}% known
                      {month.classifiedAppearances < MIN_MONTHLY_APPEARANCES ? ' (small sample)' : ''}
                    </span>
                  ))}
                </div>
                {months.some((month) => month.coverage < 70) && (
                  <p className="mt-2">Some months have low classification coverage. Their percentages describe the available deck data, not all players.</p>
                )}
              </div>
            </>
          )}
        </div>
      )}
    </section>
  )
}
