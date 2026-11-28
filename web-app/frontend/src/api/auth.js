import { get, post } from './client'

export const getMe = () => get('/api/me')
export const logout = () => get('/api/logout')
export const finishWelcome = () => post('/api/me/welcome-done')
