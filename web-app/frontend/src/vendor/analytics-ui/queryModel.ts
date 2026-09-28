import type { CardMetadata } from './cardTable'

export type QueryField = 'avatar' | 'opponent_avatar' | 'deck_card' | 'opening_card' | 'played_card'
  | 'went_first' | 'mulligan_count' | 'queue_type'
export type QueryFilter = { kind: 'group'; operator: 'and' | 'or'; children: QueryFilter[]; negate?: boolean }
  | { kind: 'condition'; field: QueryField; value: string | number | boolean; byPlayerTurn?: number; negate?: boolean }
export type QueryNode = { id: string; kind: 'group'; operator: 'and' | 'or'; children: QueryNode[]; negate?: boolean }
  | { id: string; kind: 'condition'; field: QueryField; value: string | number | boolean; search?: string; byPlayerTurn?: number; negate?: boolean }
export interface RecordedName { name: string; kind: 'card' | 'avatar' }
export interface NameOption extends RecordedName { source: 'catalog' | 'recorded'; type?: string; imageUrl?: string }
export const FIELD_LABELS: Record<QueryField, string> = {
  avatar: 'Your avatar', opponent_avatar: 'Opponent avatar', deck_card: 'Card in deck',
  played_card: 'Card played', opening_card: 'Card in opening hand', went_first: 'Going first / second',
  mulligan_count: 'Cards mulliganed', queue_type: 'Game type',
}
export const MAX_QUERY_NODES = 25
let nextNodeId = 0
export function newRule(field: QueryField = 'avatar', value: string | number | boolean = ''): Extract<QueryNode, { kind: 'condition' }> {
  return { id: `query-${++nextNodeId}`, kind: 'condition', field, value,
    ...(typeof value === 'string' ? { search: value } : {}) }
}
export function newGroup(children: QueryNode[] = [], operator: 'and' | 'or' = 'and'): Extract<QueryNode, { kind: 'group' }> {
  return { id: `query-${++nextNodeId}`, kind: 'group', operator, children }
}
export function queryNodeCount(node: QueryNode): number {
  return 1 + (node.kind === 'group' ? node.children.reduce((sum, child) => sum + queryNodeCount(child), 0) : 0)
}
export function updateQueryNode(node: QueryNode, id: string, update: (node: QueryNode) => QueryNode): QueryNode {
  if (node.id === id) return update(node)
  return node.kind === 'group' ? { ...node, children: node.children.map(child => updateQueryNode(child, id, update)) } : node
}
export function removeQueryNode(node: QueryNode, id: string): QueryNode {
  return node.kind === 'group' ? { ...node, children: node.children.filter(child => child.id !== id).map(child => removeQueryNode(child, id)) } : node
}
export function queryFilter(node: QueryNode): QueryFilter {
  if (node.kind === 'group') return { kind: 'group', operator: node.operator, children: node.children.map(queryFilter), ...(node.negate ? { negate: true } : {}) }
  return { kind: 'condition', field: node.field, value: node.value, ...(node.negate ? { negate: true } : {}),
    ...(node.byPlayerTurn === undefined ? {} : { byPlayerTurn: node.byPlayerTurn }) }
}
export function queryProblem(node: QueryNode, depth = 0): string | null {
  if (depth > 4 || queryNodeCount(node) > MAX_QUERY_NODES) return 'Use fewer rules or groups in this query.'
  if (node.kind === 'group') {
    if (!node.children.length) return 'Add a rule to each group, or remove the empty group.'
    if (node.children.length > 10) return 'Use at most 10 rules in one group.'
    return node.children.map(child => queryProblem(child, depth + 1)).find(Boolean) ?? null
  }
  if (node.field === 'mulligan_count' && (!Number.isInteger(node.value) || Number(node.value) < 0 || Number(node.value) > 20)) return 'Enter a whole number from 0 to 20 for cards mulliganed.'
  if (node.byPlayerTurn !== undefined && (!Number.isInteger(node.byPlayerTurn) || node.byPlayerTurn < 1 || node.byPlayerTurn > 100)) return 'Enter a whole turn number from 1 to 100.'
  if (typeof node.value === 'string' && (!node.value.trim() || node.value.length > 120)) return `Choose a value for “${FIELD_LABELS[node.field]}”.`
  return null
}
export function describeQuery(node: QueryNode): string {
  if (node.kind === 'group') {
    if (!node.children.length) return 'add a rule'
    const text = node.children.map(child => child.kind === 'group' ? `(${describeQuery(child)})` : describeQuery(child)).join(node.operator === 'and' ? ' AND ' : ' OR ')
    return node.negate ? `NOT (${text})` : text
  }
  const name = typeof node.value === 'string' ? node.value || '…' : String(node.value)
  const not = node.negate
  switch (node.field) {
    case 'avatar': return `your avatar ${not ? 'is not' : 'is'} ${name}`
    case 'opponent_avatar': return `opponent avatar ${not ? 'is not' : 'is'} ${name}`
    case 'deck_card': return `your deck ${not ? 'does not contain' : 'contains'} ${name}`
    case 'opening_card': return `your post-mulligan hand ${not ? 'does not contain' : 'contains'} ${name}`
    case 'played_card': return `you ${not ? 'did not play' : 'played'} ${name}${node.byPlayerTurn === undefined ? '' : ` by your turn ${node.byPlayerTurn}`}`
    case 'went_first': return `you went ${node.value === !not ? 'first' : 'second'}`
    case 'mulligan_count': return `you mulliganed ${not ? 'a number other than ' : ''}${name} cards`
    case 'queue_type': return `game type ${not ? 'is not' : 'is'} ${{ all: 'All', casual: 'Casual', summit_ranked: 'Summit Ranked' }[name] ?? name}`
  }
}
export function nameKey(name: string): string {
  return name.normalize('NFKD').replace(/[\u0300-\u036f]/g, '').toLowerCase().replace(/[^a-z0-9]+/g, ' ').trim()
}
export function buildNameOptions(catalog: readonly CardMetadata[], recorded: readonly RecordedName[]): NameOption[] {
  const names = new Map<string, NameOption>()
  for (const card of catalog) {
    const kind = card.type.toLowerCase() === 'avatar' ? 'avatar' : 'card'
    names.set(`${kind}:${nameKey(card.name)}`, { name: card.name, kind, source: 'catalog', type: card.type, imageUrl: card.imageUrl })
  }
  for (const entry of recorded) {
    const key = `${entry.kind}:${nameKey(entry.name)}`
    if (entry.name.trim() && !names.has(key)) names.set(key, { ...entry, source: 'recorded' })
  }
  return [...names.values()].sort((a, b) => a.name.localeCompare(b.name))
}
function editDistance(a: string, b: string): number {
  const matrix = Array.from({ length: a.length + 1 }, (_, i) => Array.from({ length: b.length + 1 }, (_, j) => i === 0 ? j : j === 0 ? i : 0))
  for (let i = 1; i <= a.length; i++) for (let j = 1; j <= b.length; j++) {
    matrix[i][j] = Math.min(matrix[i - 1][j] + 1, matrix[i][j - 1] + 1, matrix[i - 1][j - 1] + Number(a[i - 1] !== b[j - 1]))
    if (i > 1 && j > 1 && a[i - 1] === b[j - 2] && a[i - 2] === b[j - 1]) matrix[i][j] = Math.min(matrix[i][j], matrix[i - 2][j - 2] + 1)
  }
  return matrix[a.length][b.length]
}
export function searchNames(options: readonly NameOption[], search: string, kind: 'card' | 'avatar'): NameOption[] {
  const key = nameKey(search)
  return options.filter(option => option.kind === kind).map(option => {
    const candidate = nameKey(option.name)
    let score = !key ? 4 : candidate === key ? 0 : candidate.startsWith(key) ? 1 : candidate.includes(key) ? 2 : Infinity
    if (score === Infinity) {
      const words = candidate.split(' ')
      const distances = key.split(' ').map(token => Math.min(...words.map(word => word.startsWith(token) ? 0
        : token.length >= 3 && Math.abs(word.length - token.length) <= 2 ? editDistance(token, word) : 99)))
      if (distances.every((distance, index) => distance <= (key.split(' ')[index].length >= 6 ? 2 : 1))) score = 3 + distances.reduce((a, b) => a + b, 0)
    }
    return { option, score }
  }).filter(entry => Number.isFinite(entry.score)).sort((a, b) => a.score - b.score || a.option.name.localeCompare(b.option.name))
    .slice(0, 8).map(entry => entry.option)
}
