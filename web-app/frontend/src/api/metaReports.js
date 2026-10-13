import { del, get, post, put } from './client'

// Meta Report: see routes/api/meta_reports.py
export const listMetaReports = () => get('/api/meta-reports')
export const getMetaReport = (slug) => get(`/api/meta-reports/${encodeURIComponent(slug)}`)
export const subscribeMetaReport = (email) => post('/api/meta-reports/subscribe', { email })
export const confirmMetaReportEmail = (token) => post('/api/meta-reports/email/confirm', { token })
export const unsubscribeMetaReportEmail = (token) => post('/api/meta-reports/email/unsubscribe', { token })

export const adminListMetaReports = () => get('/api/meta-reports/admin')
export const adminGetMetaReport = (slug) => get(`/api/meta-reports/admin/${encodeURIComponent(slug)}`)
export const adminBuildMetaReport = (period) => post('/api/meta-reports/admin/build', { period })
export const adminSaveMetaReportStory = (slug, story) =>
  put(`/api/meta-reports/admin/${encodeURIComponent(slug)}/story`, { story })
export const adminPublishMetaReport = (slug, announce) =>
  post(`/api/meta-reports/admin/${encodeURIComponent(slug)}/publish`, { announce })
export const adminUnpublishMetaReport = (slug) =>
  post(`/api/meta-reports/admin/${encodeURIComponent(slug)}/unpublish`)
export const adminDeleteMetaReport = (slug) => del(`/api/meta-reports/admin/${encodeURIComponent(slug)}`)
