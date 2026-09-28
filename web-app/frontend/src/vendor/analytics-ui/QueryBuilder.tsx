import { Fragment, memo, useCallback, useEffect, useId, useMemo, useRef, useState } from 'react'
import type { CardMetadata, Rate } from './cardTable'
import type { NameOption, QueryField, QueryNode, RecordedName } from './queryModel'
import type { AnalyticsPopulation } from './population'
import { FIELD_LABELS, MAX_QUERY_NODES, buildNameOptions, describeQuery, nameKey, newGroup, newRule, queryFilter, queryNodeCount, queryProblem, removeQueryNode, searchNames, updateQueryNode } from './queryModel'
import './query.css'

interface NamePickerProps {
  label: string; value: string; search: string; kind: 'card' | 'avatar'; options: readonly NameOption[]
  onSearch: (value: string) => void; onSelect: (value: string) => void
}
function NamePickerInner({ label, value, search, kind, options, onSearch, onSelect }: NamePickerProps) {
  const id = useId()
  const [open, setOpen] = useState(false)
  const [active, setActive] = useState(0)
  const inputRef = useRef<HTMLInputElement>(null)
  const listRef = useRef<HTMLDivElement>(null)
  const suggestions = useMemo(() => searchNames(options, search, kind), [options, search, kind])
  const exact = options.find(option => option.kind === kind && nameKey(option.name) === nameKey(search))
  const custom = Boolean(search.trim() && !exact)
  const count = suggestions.length + Number(custom)
  useEffect(() => { setActive(0) }, [search, kind, options])
  useEffect(() => { if (open) listRef.current?.children[active]?.scrollIntoView({ block: 'nearest' }) }, [active, open])
  const choose = (index: number) => {
    const name = suggestions[index]?.name ?? (custom ? search.trim() : '')
    if (name) { onSelect(name); setOpen(false) }
  }
  return <div className="analytics-name" onBlur={event => { if (!event.currentTarget.contains(event.relatedTarget)) setOpen(false) }}>
    <label htmlFor={id}>{label}</label>
    <div className="analytics-name__input">
      <input ref={inputRef} id={id} role="combobox" aria-autocomplete="list" aria-expanded={open} aria-controls={`${id}-list`}
        aria-activedescendant={open && count ? `${id}-option-${active}` : undefined} autoComplete="off" spellCheck={false}
        placeholder={`Search ${kind === 'avatar' ? 'avatars' : 'cards'}…`} maxLength={120} value={search}
        onFocus={() => setOpen(true)} onChange={event => { onSearch(event.target.value); setOpen(true); setActive(0) }}
        onKeyDown={event => {
          if (event.key === 'Escape') { setOpen(false); event.stopPropagation() }
          if (event.key === 'ArrowDown' || event.key === 'ArrowUp') {
            event.preventDefault(); setOpen(true)
            setActive(current => !open ? 0 : Math.max(0, Math.min(count - 1, current + (event.key === 'ArrowDown' ? 1 : -1))))
          }
          if (event.key === 'Enter' && open) { event.preventDefault(); choose(active) }
        }} />
      {search ? <button type="button" aria-label={`Clear ${label.toLowerCase()}`} onClick={() => { onSearch(''); setOpen(true); inputRef.current?.focus() }}>×</button> : <span aria-hidden="true">⌕</span>}
    </div>
    {open ? <div className="analytics-name__menu">
      <div className="analytics-name__menu-label">{search ? 'Choose a match' : `Search by part of a ${kind} name`}</div>
      <div role="listbox" aria-label={`${label} suggestions`} id={`${id}-list`} ref={listRef}>
        {suggestions.map((option, index) => <button type="button" role="option" aria-selected={active === index}
          id={`${id}-option-${index}`} key={`${option.kind}:${option.name}`} tabIndex={-1}
          onPointerDown={event => event.preventDefault()} onClick={() => choose(index)} onMouseEnter={() => setActive(index)}>
          {option.imageUrl ? <img src={option.imageUrl} alt="" loading="lazy" /> : <span className="analytics-name__placeholder" aria-hidden="true">◇</span>}
          <span>{option.name}<small>{option.source === 'catalog' ? `Catalog · ${option.type}` : 'Custom / recorded name'}</small></span>
          {option.name === value ? <span aria-hidden="true">✓</span> : null}
        </button>)}
        {custom ? <button type="button" role="option" aria-selected={active === suggestions.length} tabIndex={-1}
          id={`${id}-option-${suggestions.length}`} onPointerDown={event => event.preventDefault()} onClick={() => choose(suggestions.length)}>
          <span className="analytics-name__placeholder" aria-hidden="true">＋</span><span>Use “{search.trim()}”<small>Exact custom name</small></span>
        </button> : null}
      </div>
      {!count ? <p>No matches. Type a custom name to use it.</p> : null}
    </div> : null}
    {value ? <small className="analytics-name__selected">✓ {exact?.source === 'catalog' ? 'Catalog name selected' : 'Custom / recorded name selected'}</small> : null}
  </div>
}
const NamePicker = memo(NamePickerInner)

interface RuleEditorProps {
  node: QueryNode; depth: number; number: string; admin: boolean; options: readonly NameOption[]; totalNodes: number
  onChange: (id: string, update: (node: QueryNode) => QueryNode) => void; onRemove: (id: string) => void
}
function RuleEditorInner({ node, depth, number, admin, options, totalNodes, onChange, onRemove }: RuleEditorProps) {
  if (node.kind === 'group') {
    const mode = node.negate ? node.operator === 'or' ? 'none' : 'not_all' : node.operator
    const canAdd = node.children.length < 10 && totalNodes < MAX_QUERY_NODES && depth < 4
    const canGroup = canAdd && depth < 3 && totalNodes + 2 <= MAX_QUERY_NODES
    return <div className={`analytics-query-group${depth ? ' analytics-query-group--nested' : ''}`} role="group" aria-label={depth ? `Rule group ${number}` : 'Query rules'}>
      <div className="analytics-query-group__header">
        <label>{depth ? 'Within this group' : 'Find player-games matching'}
          <select aria-label={depth ? `Match rules in group ${number}` : 'Match rules'} value={mode}
            onChange={event => onChange(node.id, current => current.kind !== 'group' ? current : { ...current,
              operator: event.target.value === 'or' || event.target.value === 'none' ? 'or' : 'and',
              negate: event.target.value === 'none' || event.target.value === 'not_all' })}>
            <option value="and">All rules (AND)</option><option value="or">Any rule (OR)</option><option value="none">None of these rules</option>
            {mode === 'not_all' ? <option value="not_all">Not all of these rules</option> : null}
          </select>
        </label>
        {depth ? <button type="button" className="analytics-query__quiet" aria-label={`Remove group ${number}`} onClick={() => onRemove(node.id)}>Remove group</button> : null}
      </div>
      <p className="analytics-query__note">{mode === 'and' ? 'Every rule must match the same player’s game.' : mode === 'or'
        ? 'At least one rule must match.' : mode === 'none' ? 'Only include games where none of these rules match.' : 'Exclude games where every rule matches.'}</p>
      {!node.children.length ? <p className="analytics-query__empty">Add a rule below to describe the games you want.</p> : null}
      {node.children.map((child, index) => <Fragment key={child.id}>
        {index > 0 ? <div className="analytics-query__join" aria-hidden="true">{node.operator === 'and' ? 'AND' : 'OR'}</div> : null}
        <RuleEditor node={child} depth={depth + 1} number={number ? `${number}.${index + 1}` : String(index + 1)} admin={admin}
          options={options} totalNodes={totalNodes} onChange={onChange} onRemove={onRemove} />
      </Fragment>)}
      <div className="analytics-query-group__actions">
        <button type="button" disabled={!canAdd} onClick={() => onChange(node.id, current => current.kind !== 'group' ? current
          : { ...current, children: [...current.children, newRule()] })}>＋ Add rule</button>
        <button type="button" disabled={!canGroup} title="Combine alternatives, such as either of two opponent avatars"
          onClick={() => onChange(node.id, current => current.kind !== 'group' ? current
            : { ...current, children: [...current.children, newGroup([newRule('opponent_avatar')], 'or')] })}>＋ Add OR group</button>
        {!canAdd ? <small>Group or query limit reached.</small> : null}
      </div>
    </div>
  }
  const field = node.field
  const change = (patch: Partial<Extract<QueryNode, { kind: 'condition' }>>) => onChange(node.id, current => current.kind === 'condition' ? { ...current, ...patch } : current)
  const positive = field === 'deck_card' || field === 'opening_card' ? 'Contains' : field === 'played_card' ? 'Was played' : field === 'mulligan_count' ? 'Exactly' : 'Is'
  const negative = field === 'deck_card' || field === 'opening_card' ? 'Does not contain' : field === 'played_card' ? 'Was not played' : field === 'mulligan_count' ? 'Not exactly' : 'Is not'
  return <div className="analytics-query-rule" role="group" aria-label={`Rule ${number}`}>
    <div className="analytics-query-rule__header"><span>Rule {number}</span>
      <button type="button" className="analytics-query__quiet" aria-label={`Remove rule ${number}`} onClick={() => onRemove(node.id)}>Remove</button>
    </div>
    <div className="analytics-query-rule__fields">
      <label>Condition<select aria-label={`Condition for rule ${number}`} value={field} onChange={event => {
        const next = event.target.value as QueryField
        onChange(node.id, () => ({ ...newRule(next, next === 'went_first' ? true : next === 'mulligan_count' ? 0 : ''), id: node.id }))
      }}>{(Object.keys(FIELD_LABELS) as QueryField[]).filter(key => admin || key !== 'queue_type').map(key => <option key={key} value={key}>{FIELD_LABELS[key]}</option>)}</select></label>
      {field !== 'went_first' ? <label>Match<select aria-label={`Match for rule ${number}`} value={node.negate ? 'not' : 'is'}
        onChange={event => change({ negate: event.target.value === 'not' })}><option value="is">{positive}</option><option value="not">{negative}</option></select></label> : null}
      {field === 'went_first' ? <label>You went<select aria-label={`You went for rule ${number}`} value={String(node.value)} onChange={event => change({ value: event.target.value === 'true' })}>
        <option value="true">First</option><option value="false">Second</option></select></label>
        : field === 'mulligan_count' ? <label>Number of cards<input aria-label="Cards mulliganed" type="number" min="0" max="20" step="1" value={String(node.value)}
          onChange={event => change({ value: event.target.value === '' ? '' : Number(event.target.value) })} /></label>
          : field === 'queue_type' ? <label>Game type<select aria-label="Query game type" value={String(node.value)} onChange={event => change({ value: event.target.value })}>
            <option value="">Choose a type</option><option value="all">All</option><option value="casual">Casual</option><option value="summit_ranked">Summit Ranked</option></select></label>
            : <NamePicker label={FIELD_LABELS[field]} kind={field === 'avatar' || field === 'opponent_avatar' ? 'avatar' : 'card'}
              options={options} value={String(node.value)} search={node.search ?? String(node.value)}
              onSearch={search => change({ search, value: '' })} onSelect={value => change({ value, search: value })} />}
    </div>
    {field === 'played_card' ? <div className="analytics-query-rule__timing">
      <label>When<select aria-label={`Play timing for rule ${number}`} value={node.byPlayerTurn === undefined ? 'any' : 'by'}
        onChange={event => change({ byPlayerTurn: event.target.value === 'any' ? undefined : 7 })}>
        <option value="any">Any time in the game</option><option value="by">By your turn…</option></select></label>
      {node.byPlayerTurn !== undefined ? <label>Turn<input aria-label="By your turn" type="number" min="1" max="100" step="1"
        value={Number.isNaN(node.byPlayerTurn) ? '' : node.byPlayerTurn} onChange={event => change({ byPlayerTurn: event.target.value === '' ? NaN : Number(event.target.value) })} /></label> : null}
      <small>{node.byPlayerTurn === undefined ? 'Counts a confirmed play at any point.' : 'Includes that turn. Uses your own turns, not the combined turn count.'}</small>
    </div> : field === 'opening_card' ? <p className="analytics-query__note">Opening hand means the cards kept after mulligans.</p>
      : field === 'mulligan_count' ? <p className="analytics-query__note">How many cards you returned during the mulligan.</p> : null}
  </div>
}
const RuleEditor = memo(RuleEditorInner)

interface QueryBuilderProps {
  endpoint: string; query: string; admin: boolean; active: boolean; catalog: readonly CardMetadata[]; catalogError?: string | null
  onPopulation: (key: string, population: AnalyticsPopulation | null) => void
}
function QueryBuilderInner({ endpoint, query, admin, active, catalog, catalogError, onPopulation }: QueryBuilderProps) {
  const [root, setRoot] = useState<QueryNode>(() => newGroup([newRule()]))
  const [recorded, setRecorded] = useState<{ key: string; names: RecordedName[]; population: AnalyticsPopulation } | null>(null)
  const [namesError, setNamesError] = useState(false)
  const [result, setResult] = useState<{ dataAvailable: boolean; cohort: Rate } | null>(null)
  const [error, setError] = useState<string | null>(null)
  const [running, setRunning] = useState(false)
  const request = useRef<AbortController | null>(null)
  const namesKey = `${endpoint}?${query}`
  const options = useMemo(() => buildNameOptions(catalog, recorded?.key === namesKey ? recorded.names : []), [catalog, recorded, namesKey])
  const clearResult = useCallback(() => { request.current?.abort(); setResult(null); setError(null); setRunning(false) }, [])
  useEffect(() => {
    if (active && recorded?.key === namesKey) onPopulation(namesKey, recorded.population)
  }, [active, namesKey, recorded, onPopulation])
  useEffect(() => {
    clearResult()
    setNamesError(false)
    return () => request.current?.abort()
  }, [endpoint, query, clearResult])
  useEffect(() => {
    if (!active || recorded?.key === namesKey) return
    const controller = new AbortController()
    setNamesError(false)
    const load = async () => {
      try {
        const response = await fetch(`${endpoint}/query-options?${query}`, { signal: controller.signal })
        if (!response.ok) throw new Error('Names unavailable')
        const body = await response.json() as AnalyticsPopulation & { options: RecordedName[] }
        if (!controller.signal.aborted) setRecorded({ key: namesKey, names: body.options, population: body })
      } catch {
        if (!controller.signal.aborted) { setNamesError(true); onPopulation(namesKey, null) }
      }
    }
    void load()
    return () => controller.abort()
  }, [active, endpoint, query, namesKey, recorded?.key, onPopulation])
  const change = useCallback((id: string, update: (node: QueryNode) => QueryNode) => {
    clearResult(); setRoot(current => updateQueryNode(current, id, update))
  }, [clearResult])
  const remove = useCallback((id: string) => { clearResult(); setRoot(current => removeQueryNode(current, id)) }, [clearResult])
  const replace = (node: QueryNode) => { clearResult(); setRoot(node) }
  const selection = Object.fromEntries(new URLSearchParams(query))
  const problem = selection.from && selection.through && selection.from > selection.through
    ? 'The From date must be on or before the Through date.' : queryProblem(root)
  const population = [selection.format === 'limited' ? 'Limited' : 'Constructed', admin
    ? selection.queueType === 'summit_ranked' ? 'Summit Ranked · first games' : selection.queueType === 'casual' ? 'Casual' : 'All game types' : 'Released games',
  selection.from || selection.through ? `${selection.from || 'Beginning'} to ${selection.through || 'latest available'}` : 'All available dates'].join(' · ')
  const run = async () => {
    if (problem) return
    clearResult()
    const controller = new AbortController()
    request.current = controller
    setRunning(true)
    try {
      const response = await fetch(`${endpoint}/cohort`, { method: 'POST', headers: { 'content-type': 'application/json' },
        body: JSON.stringify({ selection, filter: queryFilter(root) }), signal: controller.signal })
      if (!response.ok) throw new Error('Could not run this query. Try again.')
      const body = await response.json() as { dataAvailable: boolean; cohort: Rate }
      if (!controller.signal.aborted) setResult(body)
    } catch (cause) { if (!controller.signal.aborted) setError(cause instanceof Error ? cause.message : 'Query failed. Try again.') }
    finally { if (!controller.signal.aborted) setRunning(false) }
  }
  return <section className="game-analytics__panel analytics-query" aria-labelledby="combo-analysis-title">
    <div className="analytics-query__heading"><div><p className="game-analytics__eyebrow">Explore combinations</p><h2 id="combo-analysis-title">Build a query</h2></div>
      <button type="button" className="analytics-query__quiet" onClick={() => replace(newGroup([newRule()]))}>Clear query</button></div>
    <p className="analytics-query__population"><span>Searching</span> {population}</p>
    <div className="analytics-query__examples" aria-label="Example queries"><span>Try an example</span>
      <button type="button" onClick={() => replace(newGroup([newRule('avatar', 'Imposter'), { ...newRule('played_card', 'Whirling Blades'), byPlayerTurn: 7 }]))}>Avatar + card by turn</button>
      <button type="button" onClick={() => replace(newGroup([newRule('opening_card', 'Temple of Moloch')]))}>Opening hand</button>
      <button type="button" onClick={() => replace(newGroup([newRule('went_first', true)]))}>Going first / second</button>
      <button type="button" onClick={() => replace(newGroup([newRule('avatar', 'Imposter'), newGroup([newRule('opponent_avatar', 'Battlemage'), newRule('opponent_avatar', 'Avatar of Earth')], 'or')]))}>Either opponent avatar</button>
    </div>
    {namesError ? <p className="analytics-query__note">Recorded-name suggestions are unavailable. You can still search the catalog or enter a custom name.</p> : null}
    {catalogError ? <p className="analytics-query__note">The catalog could not be loaded. Recorded-name suggestions and custom entry are still available.</p> : null}
    <RuleEditor node={root} depth={0} number="" admin={admin} options={options} totalNodes={queryNodeCount(root)} onChange={change} onRemove={remove} />
    <div className="analytics-query__summary"><span>Your query</span><p>{describeQuery(root)}.</p></div>
    <div className="analytics-query__submit"><button type="button" className="game-analytics__run" disabled={Boolean(problem) || running} onClick={() => void run()}>
      {running ? 'Finding games…' : 'Show win rate'}</button>{problem ? <p>{problem}</p> : null}</div>
    {error ? <p role="alert" className="game-analytics__error">{error}</p> : null}
    {result ? <div className="analytics-query__result" role="status">
      {!result.dataAvailable ? <p>Analytics data has not been loaded yet.</p> : result.cohort.playerGames === 0 ? <p>No matching player-games. Try fewer rules or a wider date range.</p>
        : result.cohort.winRate === null ? <p>A win rate is unavailable for this query.</p>
          : <><div><strong>{(result.cohort.winRate * 100).toFixed(1)}%</strong><span>win rate</span></div>
            <p>{result.cohort.playerGames?.toLocaleString()} {result.cohort.playerGames === 1 ? 'player-game' : 'player-games'} and {result.cohort.matches?.toLocaleString()} {result.cohort.matches === 1 ? 'match' : 'matches'}<br />{result.cohort.wins?.toLocaleString()} {result.cohort.wins === 1 ? 'win' : 'wins'} · one observation per player per game</p></>}
    </div> : null}
    <details className="analytics-query__help"><summary>How these rules work</summary>
      <ul><li>All rules must match the same player’s game. Use an OR group for alternatives, such as either of two opponent avatars.</li>
        <li>Query results show counts and win rates for any sample size. They include no replay links.</li>
        <li>Card and turn conditions describe your side. “Opponent avatar” describes the other player.</li>
        <li>Opening hands are after mulligans. “By your turn 7” includes your seventh turn.</li>
        <li>Uncertain plays are excluded from both played and not-played conditions unless another confirmed play resolves the answer. Unknown turn timing cannot satisfy a turn limit or its opposite.</li>
        <li>Custom names must match the recorded name. Suggestions include catalog names and recorded names with a sufficient sample.</li></ul>
    </details>
  </section>
}
export const QueryBuilder = memo(QueryBuilderInner)
