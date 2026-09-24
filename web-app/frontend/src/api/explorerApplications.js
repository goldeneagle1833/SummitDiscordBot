import { get, post, put, del } from './client'

// Public (logged-in applicant)
export const submitApplication = (payload) =>
  post('/api/explorer/applications', payload)

export const getMyApplication = () => get('/api/explorer/applications/mine')

export const updateMyApplication = (payload) =>
  put('/api/explorer/applications/mine', payload)

// Explorer admin review
export const getApplications = (status) =>
  get(`/api/explorer/applications${status ? `?status=${encodeURIComponent(status)}` : ''}`)

export const getApplication = (id) => get(`/api/explorer/applications/${id}`)

export const voteOnApplication = (id, scores) =>
  post(`/api/explorer/applications/${id}/vote`, scores)

export const setApplicationStatus = (id, status) =>
  post(`/api/explorer/applications/${id}/status`, { status })

export const getPublishPreview = () => get('/api/explorer/applications/publish')

export const publishDecisions = (confirm) =>
  post('/api/explorer/applications/publish', { confirm })

export const addApplicationComment = (id, body) =>
  post(`/api/explorer/applications/${id}/comments`, { body })

export const addCandidate = (payload) =>
  post('/api/explorer/applications/candidates', payload)

export const deleteApplication = (id) => del(`/api/explorer/applications/${id}`)

export const regeocodeApplication = (id) =>
  post(`/api/explorer/applications/${id}/geocode`)

export const refreshLgsAttendance = (id) =>
  post(`/api/explorer/applications/${id}/lgs-attendance`)

export const EXPORT_CSV_URL = '/api/explorer/applications/export.csv'
