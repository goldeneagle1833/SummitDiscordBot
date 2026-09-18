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
})
