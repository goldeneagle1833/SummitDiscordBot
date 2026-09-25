import { get, post, del } from './client'

// Public
export const getSeasonFeedbackForm = () => get('/api/feedback/season/form')

export const submitSeasonFeedback = (answers) =>
  post('/api/feedback/season', { answers })

// Admin
export const getSeasonFeedbackResponses = (season) =>
  get(`/api/feedback/season/responses${season ? `?season=${encodeURIComponent(season)}` : ''}`)

export const deleteSeasonFeedbackResponse = (id) => del(`/api/feedback/season/${id}`)

export const seasonFeedbackExportUrl = (season) =>
  `/api/feedback/season/export.csv${season ? `?season=${encodeURIComponent(season)}` : ''}`

export const OTHER_PREFIX = 'Other: '
