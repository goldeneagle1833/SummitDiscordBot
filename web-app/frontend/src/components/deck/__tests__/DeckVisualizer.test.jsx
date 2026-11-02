import { describe, it, expect } from 'vitest'
import { screen, within } from '@testing-library/react'
import { render } from '@/test/test-utils'
import DeckVisualizer from '../DeckVisualizer'

const spell = (name, rarity, extra = {}) => ({
  name,
  rarity,
  type: 'Magic',
  image: `${name}.png`,
  quantity: 1,
  cost: 2,
  ...extra,
})

const site = (name, rarity, extra = {}) => ({
  name,
  rarity,
  type: 'Site',
  image: `${name}.png`,
  quantity: 1,
  ...extra,
})

function panelFor(title) {
  return screen.getByText(title).closest('div').parentElement
}

describe('DeckVisualizer card grid', () => {
  it('shows a card we have no image for, so the counts match the stats', () => {
    render(
      <DeckVisualizer
        spellbook={[
          spell('Bolt', 'Ordinary', { type: 'Minion' }),
          // No image resolved for this one.
          { name: 'Apply Alkahest', rarity: 'Ordinary', type: 'Minion', quantity: 2 },
        ]}
      />,
    )

    expect(screen.getByText(/minions \(3\)/i)).toBeInTheDocument()
    expect(screen.getByText('Apply Alkahest')).toBeInTheDocument()
    expect(screen.getByText('x2')).toBeInTheDocument()
  })

  it('still renders the art for cards that have it', () => {
    const { container } = render(<DeckVisualizer spellbook={[spell('Bolt', 'Ordinary')]} />)
    expect(
      [...container.querySelectorAll('img')].some((i) => i.src.includes('/card-images/Bolt.png')),
    ).toBe(true)
  })
})

describe('DeckVisualizer rarity breakdown', () => {
  it('counts spellbook rarity on its own', () => {
    render(
      <DeckVisualizer
        spellbook={[spell('Heirloom', 'Unique'), spell('Bolt', 'Ordinary'), spell('Zap', 'Ordinary')]}
        atlas={[site('Court', 'Unique')]}
      />,
    )

    const spells = panelFor('Spellbook rarity')
    expect(within(spells).getByText('Unique').nextSibling).toHaveTextContent('1')
    expect(within(spells).getByText('Ordinary').nextSibling).toHaveTextContent('2')
  })

  it('counts atlas rarity separately, so courts are visible', () => {
    render(
      <DeckVisualizer
        spellbook={[spell('Bolt', 'Ordinary')]}
        atlas={[site('Court A', 'Unique'), site('Court B', 'Unique'), site('Plains', 'Ordinary')]}
      />,
    )

    const sites = panelFor('Atlas rarity')
    expect(within(sites).getByText('Unique').nextSibling).toHaveTextContent('2')
    expect(within(sites).getByText('Ordinary').nextSibling).toHaveTextContent('1')
  })

  it('respects card quantities', () => {
    render(
      <DeckVisualizer
        spellbook={[spell('Bolt', 'Ordinary', { quantity: 4 })]}
        atlas={[site('Plains', 'Ordinary', { quantity: 3 })]}
      />,
    )

    expect(within(panelFor('Spellbook rarity')).getByText('Ordinary').nextSibling).toHaveTextContent('4')
    expect(within(panelFor('Atlas rarity')).getByText('Ordinary').nextSibling).toHaveTextContent('3')
  })

  it('hides the atlas breakdown for a deck with no sites', () => {
    render(<DeckVisualizer spellbook={[spell('Bolt', 'Ordinary')]} />)
    expect(screen.getByText('Spellbook rarity')).toBeInTheDocument()
    expect(screen.queryByText('Atlas rarity')).not.toBeInTheDocument()
  })

  it('does not lump the two boards together', () => {
    render(
      <DeckVisualizer
        spellbook={[spell('Heirloom', 'Unique')]}
        atlas={[site('Court', 'Unique')]}
      />,
    )

    // One unique on each side, not two on one.
    expect(within(panelFor('Spellbook rarity')).getByText('Unique').nextSibling).toHaveTextContent('1')
    expect(within(panelFor('Atlas rarity')).getByText('Unique').nextSibling).toHaveTextContent('1')
  })

  it('leaves Collection cards out of the rarity counts', () => {
    render(
      <DeckVisualizer
        spellbook={[spell('Bolt', 'Ordinary', { quantity: 2 })]}
        atlas={[site('Plains', 'Ordinary')]}
        sideboard={[
          spell('Heirloom', 'Unique', { quantity: 3 }),
          spell('Zap', 'Ordinary'),
          site('Court', 'Unique'),
        ]}
      />,
    )

    const spells = panelFor('Spellbook rarity')
    expect(within(spells).getByText('Ordinary').nextSibling).toHaveTextContent('2')
    expect(within(spells).queryByText('Unique')).not.toBeInTheDocument()
    const sites = panelFor('Atlas rarity')
    expect(within(sites).getByText('Ordinary').nextSibling).toHaveTextContent('1')
    expect(within(sites).queryByText('Unique')).not.toBeInTheDocument()
  })
})

describe('DeckVisualizer stats ignore the Collection', () => {
  it('counts only Spellbook and Atlas cards in the totals', () => {
    render(
      <DeckVisualizer
        spellbook={[spell('Bolt', 'Ordinary', { quantity: 2, type: 'Minion', elements: 'Fire' })]}
        atlas={[site('Plains', 'Ordinary', { elements: 'Earth' })]}
        sideboard={[spell('Zap', 'Ordinary', { quantity: 5, elements: 'Water' })]}
      />,
    )

    // 2 + 1 in the deck; the 5 in the Collection are not counted.
    expect(screen.getByText('Cards:').nextSibling).toHaveTextContent('3')
    expect(screen.getByText('Spell:Minion:').nextSibling).toHaveTextContent('0 : 2')
    expect(screen.queryByText('Water')).not.toBeInTheDocument()
    // The Collection itself is still shown.
    expect(screen.getByText(/collection \(5\)/i)).toBeInTheDocument()
  })
})
