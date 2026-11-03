import { useEffect, useState } from 'react'
import { Link } from 'react-router-dom'
import {
  AreaChart, Area, XAxis, YAxis, Tooltip, ResponsiveContainer, CartesianGrid,
} from 'recharts'
import { get } from '@/api/client'

/**
 * Monthly "% of decks" for one card, from Summit's own deck lists
 * (/api/creator/card-history). Was the Popular Cards row chart.
 */
export default function CardPopularityChart({ cardName }) {
  const [history, setHistory] = useState(null)
  const [histLoading, setHistLoading] = useState(true)
  const card = { name: cardName }

  useEffect(() => {
    let cancelled = false
    setHistLoading(true)
    const params = new URLSearchParams({ card: cardName, source: 'all' })
    get(`/api/creator/card-history?${params}`)
      .then((d) => { if (!cancelled) setHistory(d) })
      .catch(() => { if (!cancelled) setHistory([]) })
      .finally(() => { if (!cancelled) setHistLoading(false) })
    return () => { cancelled = true }
  }, [cardName])

  return (
    <div className="flex flex-col gap-2">
      <div className="flex flex-wrap items-center gap-3">
        <span className="text-sm font-semibold">Popularity over time</span>
        <span className="text-[11px] text-text-muted">% of Summit decks each month</span>
        <Link to={`/card/${encodeURIComponent(cardName)}`} className="text-xs text-primary hover:text-primary-light sm:ml-auto">
          View card page →
        </Link>
      </div>
            {histLoading && <p className="text-xs text-text-muted">Loading chart...</p>}
            {!histLoading && history && history.length === 0 && (
              <p className="text-xs text-text-muted">No monthly data available.</p>
            )}
            {!histLoading && history && history.length > 0 && (
              <div style={{ height: 200 }}>
                <ResponsiveContainer width="100%" height="100%">
                  <AreaChart data={history} margin={{ top: 8, right: 10, left: 0, bottom: 0 }}>
                    <defs>
                      <linearGradient id={`popGrad-${card.name}`} x1="0" y1="0" x2="0" y2="1">
                        <stop offset="5%" stopColor="rgba(77,184,255,0.4)" stopOpacity={0.4} />
                        <stop offset="95%" stopColor="rgba(77,184,255,0.4)" stopOpacity={0.02} />
                      </linearGradient>
                    </defs>
                    <CartesianGrid strokeDasharray="3 3" stroke="rgba(255,255,255,0.05)" />
                    <XAxis
                      dataKey="month"
                      tick={{ fill: 'rgba(255,255,255,0.4)', fontSize: 10 }}
                      tickLine={false}
                      axisLine={false}
                    />
                    <YAxis
                      tick={{ fill: 'rgba(255,255,255,0.4)', fontSize: 10 }}
                      tickLine={false}
                      axisLine={false}
                      width={40}
                      tickFormatter={(v) => `${v}%`}
                    />
                    <Tooltip
                      contentStyle={{
                        background: '#1a1a2e',
                        border: '1px solid rgba(255,255,255,0.1)',
                        borderRadius: 4,
                        fontSize: 11,
                      }}
                      formatter={(value, _name, props) => {
                        const p = props.payload
                        return [`${value}% (${p.decks_with_card}/${p.total_decks} decks)`, '% of Decks']
                      }}
                    />
                    <Area
                      type="monotone"
                      dataKey="percent_of_decks"
                      stroke="rgba(77,184,255,0.85)"
                      fill={`url(#popGrad-${card.name})`}
                      strokeWidth={2}
                      dot={{ fill: 'rgba(77,184,255,0.95)', r: 3 }}
                      activeDot={{ r: 5 }}
                    />
                  </AreaChart>
                </ResponsiveContainer>
              </div>
            )}
    </div>
  )
}
