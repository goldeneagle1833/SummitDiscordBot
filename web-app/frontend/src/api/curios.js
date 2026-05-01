import { get, del } from './client'

export const getCurioEntries = () => get('/api/curios/')
export const getCurioSets = () => get('/api/curios/sets')

export const createCurioEntry = (formData) =>
  fetch('/api/curios/', {
    method: 'POST',
    credentials: 'include',
    body: formData,
  }).then((r) => {
    if (!r.ok) return r.json().then((e) => Promise.reject(new Error(e.error || 'Failed to create')))
    return r.json()
  })

export const updateCurioEntry = (id, formData) =>
  fetch(`/api/curios/${id}`, {
    method: 'PUT',
    credentials: 'include',
    body: formData,
  }).then((r) => {
    if (!r.ok) return r.json().then((e) => Promise.reject(new Error(e.error || 'Failed to update')))
    return r.json()
  })

export const deleteCurioEntry = (id) => del(`/api/curios/${id}`)

export const createCurioSet = (name) =>
  fetch('/api/curios/sets', {
    method: 'POST',
    credentials: 'include',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ name }),
  }).then((r) => {
    if (!r.ok) return r.json().then((e) => Promise.reject(new Error(e.error || 'Failed to create set')))
    return r.json()
  })
