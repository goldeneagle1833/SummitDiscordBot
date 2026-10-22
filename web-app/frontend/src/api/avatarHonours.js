import { get } from './client'

// Season avatar honours: the top three players on each avatar, every ended season
export const getAvatarHonours = () => get('/api/avatar-honours')
