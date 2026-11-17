import { useEffect, useState } from 'react'

export function usePlayerSocket(guildId, onUpdate) {
  const [connected, setConnected] = useState(false)

  useEffect(() => {
    if (!guildId) {
      setConnected(false)
      return undefined
    }

    let socket
    let reconnectTimer
    let disposed = false
    let retryDelay = 1000

    const open = () => {
      if (disposed) return
      const scheme = window.location.protocol === 'https:' ? 'wss:' : 'ws:'
      const wsBase = import.meta.env.VITE_WS_BASE_URL
        || `${scheme}//${window.location.host}/ws`
      socket = new WebSocket(`${wsBase}/guilds/${guildId}`)
      socket.onopen = () => {
        retryDelay = 1000
        setConnected(true)
      }
      socket.onmessage = (event) => {
        try {
          const message = JSON.parse(event.data)
          if (message.type === 'player_update' && String(message.guild_id) === String(guildId)) {
            onUpdate(message.state)
          }
        } catch (error) {
          console.error('Could not read player update:', error)
        }
      }
      socket.onclose = () => {
        setConnected(false)
        if (!disposed) {
          reconnectTimer = window.setTimeout(open, retryDelay)
          retryDelay = Math.min(retryDelay * 1.7, 15000)
        }
      }
      socket.onerror = () => socket.close()
    }

    open()
    return () => {
      disposed = true
      window.clearTimeout(reconnectTimer)
      socket?.close()
      setConnected(false)
    }
  }, [guildId, onUpdate])

  return connected
}
