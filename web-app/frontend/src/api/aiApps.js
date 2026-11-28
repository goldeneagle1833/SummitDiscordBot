import { get, del } from './client'

// AI apps the signed-in player connected to the Summit (signed in) connector
export const getAiConnections = () => get('/api/mcp/connections')
export const disconnectAiApp = (clientId) =>
  del(clientId ? `/api/mcp/connections/${encodeURIComponent(clientId)}` : '/api/mcp/connections')
