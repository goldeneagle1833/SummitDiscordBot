import { describe, it, expect, vi, beforeEach } from 'vitest'
import { screen, renderWithRouter, userEvent, waitFor } from '@/test/test-utils'

vi.mock('@/api/seasonFeedback', async () => {
  const actual = await vi.importActual('@/api/seasonFeedback')
  return {
    ...actual,
    getSeasonFeedbackForm: vi.fn(),
    submitSeasonFeedback: vi.fn(),
  }
})

vi.mock('@/context/AuthContext', () => ({ useAuth: vi.fn() }))

import { getSeasonFeedbackForm, submitSeasonFeedback } from '@/api/seasonFeedback'
import { useAuth } from '@/context/AuthContext'
import SeasonFeedback, { toPayload } from '../SeasonFeedback'

const FORM = {
  season: 'Gothic Summit Season 7',
  sections: [
    {
      title: 'About you',
      questions: [
        {
          key: 'seasons_played',
          label: 'How many Summit seasons have you played?',
          type: 'radio',
          options: ['This is my first', '2-3', '4+'],
          required: true,
        },
        { key: 'discord_name', label: 'Discord name (optional)', type: 'text' },
      ],
    },
    {
      title: 'New players',
      questions: [
        {
          key: 'welcome_rating',
          label: 'How welcome did you feel as a new player?',
          type: 'scale',
          min: 1,
          max: 5,
          labels: ['Not welcome', 'Very welcome'],
          show_if: { key: 'seasons_played', values: ['This is my first'] },
        },
      ],
    },
    {
      title: 'Overall',
      questions: [
        {
          key: 'enjoyment',
          label: 'Overall, how much did you enjoy the season?',
          type: 'scale',
          min: 1,
          max: 10,
          labels: ['Not enjoyable', 'Amazing'],
          required: true,
        },
        {
          key: 'bot_uses',
          label: 'What did you use the bot for?',
          type: 'checkbox',
          options: ['Queueing for games', 'The shop'],
          allow_other: true,
        },
        {
          key: 'voice_games_rating',
          label: 'How did games with voice feel?',
          type: 'scale',
          min: 1,
          max: 5,
          allow_na: true,
        },
        { key: 'final_thoughts', label: 'Any final thoughts or feedback?', type: 'textarea' },
      ],
    },
  ],
}

describe('SeasonFeedback page', () => {
  beforeEach(() => {
    vi.clearAllMocks()
    useAuth.mockReturnValue({ user: false, loading: false })
    getSeasonFeedbackForm.mockResolvedValue(FORM)
    submitSeasonFeedback.mockResolvedValue({ success: true, id: 1 })
    window.scrollTo = vi.fn()
  })

  it('renders the season title and hides conditional sections until triggered', async () => {
    const user = userEvent.setup()
    renderWithRouter(<SeasonFeedback />)
    expect(await screen.findByRole('heading', { name: 'Gothic Summit Season 7 Feedback' })).toBeInTheDocument()
    expect(screen.queryByText('New players')).toBeNull()

    await user.click(screen.getByLabelText('This is my first'))
    expect(screen.getByText('New players')).toBeInTheDocument()

    await user.click(screen.getByLabelText('4+'))
    expect(screen.queryByText('New players')).toBeNull()
  })

  it('blocks submission until required questions are answered', async () => {
    const user = userEvent.setup()
    renderWithRouter(<SeasonFeedback />)
    await screen.findByRole('heading', { name: /Feedback/ })

    await user.click(screen.getByRole('button', { name: 'Submit Feedback' }))
    expect(screen.getByRole('alert')).toHaveTextContent('How many Summit seasons')
    expect(submitSeasonFeedback).not.toHaveBeenCalled()
  })

  it('submits the visible answers and shows a thank-you', async () => {
    const user = userEvent.setup()
    renderWithRouter(<SeasonFeedback />)
    await screen.findByRole('heading', { name: /Feedback/ })

    await user.click(screen.getByLabelText('This is my first'))
    // welcome_rating = 4 (the "New players" scale), enjoyment = 9
    const welcome = screen.getByRole('radiogroup', { name: /How welcome/ })
    await user.click(welcome.querySelector('[aria-checked]:nth-child(4)'))
    const enjoyment = screen.getByRole('radiogroup', { name: /enjoy the season/ })
    await user.click(enjoyment.querySelector('[aria-checked]:nth-child(9)'))

    await user.click(screen.getByLabelText('The shop'))
    await user.click(screen.getByLabelText('Other'))
    await user.type(screen.getByLabelText(/bot for\? \(other\)/), 'Deck checks')

    const voice = screen.getByRole('radiogroup', { name: /games with voice/ })
    await user.click(voice.querySelector('[aria-checked]:last-child')) // N/A

    await user.type(screen.getByLabelText(/final thoughts/), '  Great season.  ')
    await user.click(screen.getByRole('button', { name: 'Submit Feedback' }))

    await waitFor(() => expect(submitSeasonFeedback).toHaveBeenCalledTimes(1))
    expect(submitSeasonFeedback).toHaveBeenCalledWith({
      seasons_played: 'This is my first',
      welcome_rating: 4,
      enjoyment: 9,
      bot_uses: ['The shop', 'Other: Deck checks'],
      final_thoughts: 'Great season.',
    })
    expect(await screen.findByText('Thank you!')).toBeInTheDocument()
  })

  it('prefills the Discord name for a logged-in player', async () => {
    useAuth.mockReturnValue({ user: { id: '1', username: 'Rubonic' }, loading: false })
    renderWithRouter(<SeasonFeedback />)
    expect(await screen.findByLabelText(/Discord name/)).toHaveValue('Rubonic')
  })

  it('shows the API error when submission fails', async () => {
    const user = userEvent.setup()
    submitSeasonFeedback.mockRejectedValue(new Error('enjoyment must be between 1 and 10'))
    renderWithRouter(<SeasonFeedback />)
    await screen.findByRole('heading', { name: /Feedback/ })

    await user.click(screen.getByLabelText('2-3'))
    const enjoyment = screen.getByRole('radiogroup', { name: /enjoy the season/ })
    await user.click(enjoyment.querySelector('[aria-checked]:first-child'))
    await user.click(screen.getByRole('button', { name: 'Submit Feedback' }))

    expect(await screen.findByRole('alert')).toHaveTextContent('enjoyment must be between 1 and 10')
  })
})

describe('toPayload', () => {
  it('drops hidden questions and empty values', () => {
    const payload = toPayload(FORM.sections, {
      seasons_played: '4+',
      welcome_rating: 3, // hidden because not a first-season player
      enjoyment: 7,
      bot_uses: { items: [], other: '   ' },
      voice_games_rating: 'N/A',
      final_thoughts: '   ',
    })
    expect(payload).toEqual({ seasons_played: '4+', enjoyment: 7 })
  })
})
