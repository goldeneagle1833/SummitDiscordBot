import { get } from './client'

export const getMe = () => get('/api/me')
export const logout = () => get('/api/logout')
