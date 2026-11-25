import { get } from './client'

// Top bar background check for logged-in people: pending match reports,
// site notifications and the live-stream dot in one request.
export const getNavChecks = () => get('/api/nav/checks')
