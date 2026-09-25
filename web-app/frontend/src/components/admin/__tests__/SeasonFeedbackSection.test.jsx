import { describe, it, expect, vi, beforeEach } from 'vitest'
import { screen, render, userEvent, waitFor, within } from '@/test/test-utils'

vi.mock('@/api/seasonFeedback', async () => {
  const actual = await vi.importActual('@/api/seasonFeedback')
  return {
    ...actual,
    getSeasonFeedbackResponses: vi.fn(),
    deleteSeasonFeedbackResponse: vi.fn(),
  }
})

import {
  getSeasonFeedbackResponses,
  deleteSeasonFeedbackResponse,
} from '@/api/seasonFeedback'
import SeasonFeedbackSection from '../SeasonFeedbackSection'

const SECTIONS = [
  {
    title: 'Overall',
    questions: [
      { key: 'enjoyment', label: 'Overall, how much did you enjoy the season?', type: 'scale', min: 1, max: 10 },
      { key: 'voice_mode', label: 'Did you play mostly with voice or without?', type: 'radio', options: ['Mostly voice', 'A mix'] },
      { key: 'final_thoughts', label: 'Any final thoughts or feedback?', type: 'textarea' },
    ],
  },
]

const DATA = {
  season: 'Gothic Summit Season 7',
  seasons: ['Gothic Summit Season 7', 'Gothic Summit Season 6'],
  current_season: 'Gothic Summit Season 7',
  sections: SECTIONS,
  responses: [
    {
      id: 2,
      season: 'Gothic Summit Season 7',
      username: 'Rubonic',
      user_id: '1',
      created_at: '2026-09-25T10:00:00',
      answers: { enjoyment: 9, voice_mode: 'A mix', final_thoughts: 'Loved it', seasons_played: '4+' },
    },
    {
      id: 1,
      season: 'Gothic Summit Season 7',
      username: null,
      user_id: null,
      created_at: '2026-09-24T10:00:00',
      answers: { enjoyment: 5, voice_mode: 'Mostly voice', final_thoughts: null, negative_interactions: 'Yes, minor' },
    },
  ],
  summary: {
    enjoyment: { type: 'scale', count: 2, average: 7, min: 1, max: 10 },
    voice_mode: { type: 'choice', count: 2, counts: { 'Mostly voice': 1, 'A mix': 1 } },
    final_thoughts: { type: 'text', count: 1 },
  },
}

describe('SeasonFeedbackSection', () => {
  beforeEach(() => {
    vi.clearAllMocks()
    getSeasonFeedbackResponses.mockResolvedValue(DATA)
    deleteSeasonFeedbackResponse.mockResolvedValue({ success: true })
  })

  it('shows the summary, the share link, and a CSV export for the selected season', async () => {
    render(<SeasonFeedbackSection />)
    expect(await screen.findByText('2 responses')).toBeInTheDocument()
    expect(screen.getByText('7 / 10')).toBeInTheDocument()
    expect(screen.getByText('Mostly voice')).toBeInTheDocument()
    expect(screen.getByText(/\/season-feedback$/)).toBeInTheDocument()
    expect(screen.getByRole('link', { name: 'Export CSV' })).toHaveAttribute(
      'href',
      '/api/feedback/season/export.csv?season=Gothic%20Summit%20Season%207',
    )
  })

  it('reloads when a different season is chosen', async () => {
    const user = userEvent.setup()
    render(<SeasonFeedbackSection />)
    await screen.findByText('2 responses')

    getSeasonFeedbackResponses.mockResolvedValue({ ...DATA, season: 'Gothic Summit Season 6', responses: [], summary: {} })
    await user.selectOptions(screen.getByLabelText('Season'), 'Gothic Summit Season 6')

    await waitFor(() => expect(getSeasonFeedbackResponses).toHaveBeenLastCalledWith('Gothic Summit Season 6'))
    expect(await screen.findByText('No responses for this season yet.')).toBeInTheDocument()
  })

  it('lists individual responses and can delete one', async () => {
    const user = userEvent.setup()
    window.confirm = vi.fn(() => true)
    render(<SeasonFeedbackSection />)
    await screen.findByText('2 responses')

    await user.click(screen.getByRole('button', { name: 'responses' }))
    expect(screen.getByText('Rubonic')).toBeInTheDocument()
    expect(screen.getByText('Anonymous')).toBeInTheDocument()
    expect(screen.getByText('· Yes, minor')).toBeInTheDocument()

    await user.click(screen.getByRole('button', { name: /Rubonic/ }))
    const card = screen.getByRole('button', { name: /Rubonic/ }).parentElement
    expect(within(card).getByText('Loved it')).toBeInTheDocument()

    await user.click(within(card).getByRole('button', { name: 'Delete response' }))
    await waitFor(() => expect(deleteSeasonFeedbackResponse).toHaveBeenCalledWith(2))
    expect(getSeasonFeedbackResponses).toHaveBeenCalledTimes(2)
  })
})
