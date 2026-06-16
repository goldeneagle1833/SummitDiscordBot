import { get, post, put, del } from './client'

export const fetchDeckFromUrl = (url) =>
  post('/api/deck-builder/fetch', { url })

export const fetchAllCards = () =>
  get('/api/deck-builder/all-cards')

export const saveNewDeck = (data) =>
  post('/api/deck-builder/save', data)

export const updateSavedDeck = (id, data) =>
  put(`/api/deck-builder/${id}`, data)

export const listMyDecks = (search) =>
  get(`/api/deck-builder/my-decks${search ? `?q=${encodeURIComponent(search)}` : ''}`)

export const loadSavedDeck = (id) =>
  get(`/api/deck-builder/${id}`)

export const deleteSavedDeck = (id) =>
  del(`/api/deck-builder/${id}`)
