import axios from 'axios'

const api = axios.create({
  baseURL: import.meta.env.VITE_API_BASE_URL || '/api',
  timeout: 15000,
  withCredentials: true,
})

export const getAuthStatus = () => api.get('/auth/status').then((r) => r.data)
export const logout = () => api.post('/auth/logout').then((r) => r.data)
export const getHealth = () => api.get('/health').then((r) => r.data)
export const getGuilds = () => api.get('/guilds').then((r) => r.data)
export const getChannels = (guildId) => api.get(`/guilds/${guildId}/channels`).then((r) => r.data)
export const getPlayer = (guildId) => api.get(`/guilds/${guildId}/player`).then((r) => r.data)
export const connectPlayer = (guildId, voiceChannelId) =>
  api.post(`/guilds/${guildId}/connect`, { voice_channel_id: String(voiceChannelId) }).then((r) => r.data)
export const disconnectPlayer = (guildId) => api.post(`/guilds/${guildId}/disconnect`).then((r) => r.data)
export const playSong = (guildId, query, voiceChannelId) =>
  api.post(`/guilds/${guildId}/play`, {
    query,
    voice_channel_id: voiceChannelId ? String(voiceChannelId) : undefined,
  }).then((r) => r.data)
export const control = (guildId, action) => api.post(`/guilds/${guildId}/${action}`).then((r) => r.data)
export const removeSong = (guildId, index) => api.delete(`/guilds/${guildId}/queue/${index}`).then((r) => r.data)
export const shuffleQueue = (guildId) => api.post(`/guilds/${guildId}/shuffle`).then((r) => r.data)
export const setVolume = (guildId, volume) => api.put(`/guilds/${guildId}/volume`, { volume }).then((r) => r.data)
export const setLoop = (guildId, enabled) => api.put(`/guilds/${guildId}/loop`, { enabled }).then((r) => r.data)

export default api
