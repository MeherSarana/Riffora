import { useCallback, useEffect, useMemo, useRef, useState } from 'react'
import Icon from './components/Icon.jsx'
import { usePlayerSocket } from './hooks/usePlayerSocket.js'
import {
  connectPlayer, control, disconnectPlayer, getChannels, getGuilds, getHealth,
  getAuthStatus, getPlayer, logout, playSong, removeSong, setLoop, setVolume, shuffleQueue,
} from './services/api.js'

const emptyPlayer = {
  connected: false, voice_channel: null, playing: false, paused: false,
  current: null, elapsed: 0, queue: [], loop_enabled: false, volume: 1,
}

function formatTime(value) {
  if (!Number.isFinite(value) || value < 0) return '0:00'
  const seconds = Math.floor(value)
  return `${Math.floor(seconds / 60)}:${String(seconds % 60).padStart(2, '0')}`
}

function songKey(song) {
  return song?.webpage_url || `${song?.title || ''}:${song?.uploader || ''}`
}

const authErrorMessages = {
  not_allowed: 'That Discord account is not allowed to use this dashboard.',
  state_failed: 'Sign-in could not be verified. Please try again.',
  cancelled: 'Discord sign-in was cancelled.',
  login_failed: 'Discord sign-in failed. Please try again.',
}

function LoginScreen({ configured, unavailable, error, onLogin }) {
  return (
    <main className="auth-screen">
      <div className="auth-card">
        <a className="brand auth-brand" href="#"><span className="brand-mark"><Icon name="music" size={20}/></span><span>Riffora<span className="brand-dot">.</span></span></a>
        <div className="auth-orbit"><Icon name="discord" size={27}/></div>
        <div className="eyebrow"><span className="eyebrow-line"/> PRIVATE MUSIC DASHBOARD</div>
        <h1>{unavailable ? 'Dashboard offline' : <>Your music,<br/> together.</>}</h1>
        <p>{unavailable
          ? 'Start the backend, then refresh this page.'
          : configured
            ? 'Sign in with your authorized Discord account to control your server’s shared music session.'
            : 'Discord sign-in is not configured yet. Add the OAuth settings to the backend .env file, then restart the app.'}</p>
        {error && <div className="auth-error" role="alert">{error}</div>}
        {configured && !unavailable && <button className="discord-login-button" onClick={onLogin}><Icon name="discord" size={19}/> Continue with Discord</button>}
        {!configured && !unavailable && <div className="auth-setup-hint">OAuth values belong in the backend environment only.</div>}
        <div className="auth-footer"><span className="small-pulse"/> YOUR SESSION IS PRIVATE</div>
      </div>
      <div className="auth-backdrop-glow"/>
    </main>
  )
}

function App() {
  const [guilds, setGuilds] = useState([])
  const [authStatus, setAuthStatus] = useState(null)
  const [authError, setAuthError] = useState('')
  const [guildId, setGuildId] = useState(localStorage.getItem('music-dashboard-guild') || '')
  const [channels, setChannels] = useState([])
  const [channelId, setChannelId] = useState('')
  const [player, setPlayer] = useState(emptyPlayer)
  const [botOnline, setBotOnline] = useState(false)
  const [socketOnline, setSocketOnline] = useState(false)
  const [search, setSearch] = useState('')
  const [busy, setBusy] = useState(false)
  const [message, setMessage] = useState('')
  const [recent, setRecent] = useState([])
  const [stateReceivedAt, setStateReceivedAt] = useState(Date.now())
  const [clock, setClock] = useState(Date.now())
  const lastTrack = useRef('')
  const messageTimer = useRef(null)

  const flash = useCallback((text) => {
    setMessage(text)
    window.clearTimeout(messageTimer.current)
    messageTimer.current = window.setTimeout(() => setMessage(''), 3200)
  }, [])

  const handlePlayerUpdate = useCallback((state) => {
    setPlayer(state)
    setStateReceivedAt(Date.now())
    const currentKey = songKey(state.current)
    if (state.current && currentKey && currentKey !== lastTrack.current) {
      lastTrack.current = currentKey
      setRecent((previous) => {
        const next = [state.current, ...previous.filter((song) => songKey(song) !== currentKey)].slice(0, 8)
        try { localStorage.setItem(`music-dashboard-recent-${state.guild_id}`, JSON.stringify(next)) } catch { /* storage is optional */ }
        return next
      })
    }
  }, [])

  const socketOnlineNow = usePlayerSocket(authStatus?.authenticated ? guildId : '', handlePlayerUpdate)
  useEffect(() => setSocketOnline(socketOnlineNow), [socketOnlineNow])

  useEffect(() => {
    let active = true
    const query = new URLSearchParams(window.location.search)
    const signInResult = query.get('auth')
    if (signInResult) {
      setAuthError(authErrorMessages[signInResult] || 'Discord sign-in did not complete.')
      window.history.replaceState({}, '', window.location.pathname)
    }
    getAuthStatus()
      .then((status) => { if (active) setAuthStatus(status) })
      .catch(() => {
        if (active) {
          setAuthStatus({ configured: false, authenticated: false, unavailable: true })
          setAuthError('Could not reach the backend.')
        }
      })
    return () => { active = false }
  }, [])

  useEffect(() => {
    if (!authStatus?.authenticated) return undefined
    let active = true
    Promise.all([getHealth(), getGuilds()])
      .then(([health, list]) => {
        if (!active) return
        setBotOnline(Boolean(health.discord_connected))
        setGuilds(list)
        const savedGuild = localStorage.getItem('music-dashboard-guild')
        const available = list.some((guild) => guild.id === savedGuild)
        if (!list.some((guild) => guild.id === guildId)) {
          setGuildId(available ? savedGuild : list[0]?.id || '')
        }
      })
      .catch(() => active && flash('Could not reach the music API. Start the backend and try again.'))
    return () => { active = false }
  }, [flash, authStatus?.authenticated])

  useEffect(() => {
    if (!authStatus?.authenticated) return undefined
    if (!guildId) {
      setChannels([])
      setPlayer(emptyPlayer)
      setRecent([])
      return undefined
    }
    localStorage.setItem('music-dashboard-guild', guildId)
    lastTrack.current = ''
    try {
      setRecent(JSON.parse(localStorage.getItem(`music-dashboard-recent-${guildId}`) || '[]'))
    } catch { setRecent([]) }
    let active = true
    Promise.all([getChannels(guildId), getPlayer(guildId)])
      .then(([channelList, state]) => {
        if (!active) return
        setChannels(channelList)
        setPlayer(state)
        setStateReceivedAt(Date.now())
        const activeChannelId = state.voice_channel?.id || ''
        setChannelId(channelList.some((channel) => channel.id === activeChannelId)
          ? activeChannelId : channelList[0]?.id || '')
        if (state.current) {
          lastTrack.current = songKey(state.current)
          setRecent((previous) => {
            const next = [state.current, ...previous.filter((song) => songKey(song) !== songKey(state.current))].slice(0, 8)
            try { localStorage.setItem(`music-dashboard-recent-${guildId}`, JSON.stringify(next)) } catch { /* storage is optional */ }
            return next
          })
        }
      })
      .catch(() => active && flash('Could not load this server. Check that the bot is a member.'))
    return () => { active = false }
  }, [guildId, flash, authStatus?.authenticated])

  useEffect(() => {
    const timer = window.setInterval(() => setClock(Date.now()), 1000)
    return () => window.clearInterval(timer)
  }, [])

  const guild = useMemo(() => guilds.find((item) => item.id === guildId), [guilds, guildId])
  const channel = useMemo(() => channels.find((item) => item.id === channelId), [channels, channelId])
  const duration = Number(player.current?.duration) || 0
  const elapsed = Math.max(0, Number(player.elapsed) || 0)
    + (player.playing && !player.paused ? Math.max(0, (clock - stateReceivedAt) / 1000) : 0)
  const progress = duration ? Math.min(100, (elapsed / duration) * 100) : 0
  const volumePercent = Math.round((Number(player.volume) || 0) * 50)

  const runAction = useCallback(async (operation, successText) => {
    setBusy(true)
    try {
      const result = await operation()
      const state = result?.player || result
      if (state && typeof state === 'object' && 'guild_id' in state) {
        setPlayer(state)
        setStateReceivedAt(Date.now())
      }
      if (successText) flash(successText)
      return result
    } catch (error) {
      flash(error.response?.data?.detail || 'That action could not be completed.')
      return null
    } finally {
      setBusy(false)
    }
  }, [flash])

  const submitSearch = async (event) => {
    event.preventDefault()
    const query = search.trim()
    if (!guildId || !query) return
    const result = await runAction(() => playSong(guildId, query, channelId), 'Added to the queue')
    if (result) setSearch('')
  }

  const handleConnect = () => {
    if (!guildId) return flash('Choose a server first.')
    if (player.connected) {
      runAction(() => disconnectPlayer(guildId), 'Disconnected from voice')
    } else if (!channelId) {
      flash('Choose a voice channel first.')
    } else {
      runAction(() => connectPlayer(guildId, channelId), `Connecting to ${channel?.name || 'voice'}…`)
    }
  }

  const changeVolume = (value) => {
    const normalized = Number(value) / 50
    setPlayer((state) => ({ ...state, volume: normalized }))
  }

  const persistVolume = () => {
    if (guildId) runAction(() => setVolume(guildId, Number(player.volume) || 0), '')
  }

  const handleLogin = () => { window.location.assign('/api/auth/login') }

  const handleLogout = async () => {
    try {
      await logout()
    } catch {
      flash('Could not sign out cleanly. Refresh the page to check your session.')
    }
    setAuthStatus((status) => ({ ...status, authenticated: false, user: null }))
    setGuilds([])
    setGuildId('')
    setChannels([])
    setPlayer(emptyPlayer)
    setSocketOnline(false)
  }

  if (!authStatus) {
    return <main className="auth-screen"><div className="auth-loading"><span className="auth-spinner"/>Checking your session…</div></main>
  }
  if (!authStatus.authenticated) {
    return <LoginScreen configured={authStatus.configured} unavailable={authStatus.unavailable} error={authError} onLogin={handleLogin}/>
  }

  return (
    <div className="app-shell min-h-screen bg-[#0c0e12] text-white">
      <aside className="sidebar">
        <a className="brand" href="#overview" aria-label="Riffora home">
          <span className="brand-mark"><Icon name="music" size={20} /></span>
          <span>Riffora<span className="brand-dot">.</span></span>
        </a>

        <div className="side-label">WORKSPACE</div>
        <nav className="side-nav" aria-label="Main navigation">
          <a className="nav-link active" href="#overview"><Icon name="home" /> Overview</a>
          <a className="nav-link" href="#search"><Icon name="search" /> Music search</a>
          <a className="nav-link" href="#queue"><Icon name="queue" /> Queue <span className="nav-count">{player.queue?.length || 0}</span></a>
          <a className="nav-link" href="#recent"><Icon name="clock" /> Recently played</a>
        </nav>

        <div className="side-divider" />
        <div className="side-label">YOUR SERVER</div>
        <label className="select-wrap">
          <span className="sr-only">Discord server</span>
          <select value={guildId} onChange={(event) => setGuildId(event.target.value)} disabled={!guilds.length}>
            {guilds.length ? guilds.map((item) => <option key={item.id} value={item.id}>{item.name}</option>) : <option value="">No servers found</option>}
          </select>
          <Icon name="chevron" size={15} />
        </label>

        <label className="select-wrap channel-select">
          <span className="select-prefix"><Icon name="headphones" size={15} /></span>
          <span className="sr-only">Voice channel</span>
          <select value={channelId} onChange={(event) => setChannelId(event.target.value)} disabled={!channels.length}>
            {channels.length ? channels.map((item) => <option key={item.id} value={item.id}>{item.name}</option>) : <option value="">No voice channels</option>}
          </select>
          <Icon name="chevron" size={15} />
        </label>

        <button className={`connect-button ${player.connected ? 'is-connected' : ''}`} onClick={handleConnect} disabled={busy || !guildId}>
          <span className="connect-indicator" />
          {player.connected ? 'Disconnect bot' : 'Connect to voice'}
        </button>

        <div className="sidebar-bottom">
          <div className="sidebar-user-icon">{authStatus.user?.avatar_url ? <img src={authStatus.user.avatar_url} alt=""/> : <Icon name="discord" size={17} />}</div>
          <div className="sidebar-user-copy"><b>{authStatus.user?.display_name || 'Discord account'}</b><span>Authorized account</span></div>
          <span className={`tiny-status ${botOnline ? 'online' : ''}`} title={botOnline ? 'Bot online' : 'Bot offline'} />
        </div>
      </aside>

      <main className="main-content" id="overview">
        <header className="topbar">
          <div className="mobile-brand"><span className="brand-mark"><Icon name="music" size={18} /></span> Riffora<span className="brand-dot">.</span></div>
          <div className="breadcrumb"><span>Workspace</span><span className="crumb-slash">/</span><b>Overview</b></div>
          <div className="topbar-right">
            <span className={`live-pill ${socketOnline ? 'live' : ''}`}><i />{socketOnline ? 'Live updates' : 'Connecting'}</span>
            <span className={`bot-pill ${botOnline ? 'online' : ''}`}><i />{botOnline ? 'Bot online' : 'Bot offline'}</span>
            <button className="signout-button" onClick={handleLogout} title={`Sign out ${authStatus.user?.username || ''}`}>Sign out</button>
          </div>
        </header>

        <div className="page-wrap">
          <section className="page-heading">
            <div>
              <div className="eyebrow"><span className="eyebrow-line" /> YOUR MUSIC, IN SYNC</div>
              <h1>Good music.<br className="mobile-break" /> <span>One shared session.</span></h1>
              <p>Control the music playing in your Discord server.</p>
            </div>
            <div className="heading-server">
              <div className="server-avatar"><Icon name="discord" size={21} /></div>
              <div><span>CONTROLLING</span><b>{guild?.name || 'Select a server'}</b></div>
              <span className={`server-live-dot ${player.connected ? 'online' : ''}`} />
            </div>
          </section>

          <section className="now-card" aria-label="Now playing">
            <div className="now-art-wrap">
              <div className="now-art">
                {player.current?.thumbnail
                  ? <img src={player.current.thumbnail} alt="" />
                  : <div className="art-placeholder"><span className="art-ring ring-one"/><span className="art-ring ring-two"/><Icon name="music" size={42}/></div>}
                {player.playing && <span className="playing-equalizer" aria-label="Playing"><i/><i/><i/><i/></span>}
              </div>
            </div>
            <div className="now-details">
              <div className="section-kicker"><span className="equalizer-mini"><i/><i/><i/></span> NOW PLAYING</div>
              {player.current ? <>
                <h2 title={player.current.title}>{player.current.title}</h2>
                <p className="track-artist">{player.current.uploader || 'YouTube'}</p>
              </> : <>
                <h2 className="empty-title">Nothing playing <span>right now</span></h2>
                <p className="track-artist">Pick a song and let the room change.</p>
              </>}
              <div className="progress-area">
                <div className="progress-track"><span style={{ width: `${progress}%` }} /></div>
                <div className="progress-labels"><span>{player.current ? formatTime(elapsed) : '0:00'}</span><span>{duration ? formatTime(duration) : '--:--'}</span></div>
              </div>
              <div className="playback-row">
                <button className={`icon-button ${player.loop_enabled ? 'control-selected' : ''}`} title="Toggle loop" aria-label="Toggle loop" onClick={() => guildId && runAction(() => setLoop(guildId, !player.loop_enabled), player.loop_enabled ? 'Loop off' : 'Loop on')}><Icon name="repeat" size={18}/></button>
                <div className="transport-controls">
                  <button className="icon-button transport-skip" title="Skip" aria-label="Skip track" disabled={busy || !player.current} onClick={() => runAction(() => control(guildId, 'skip'), 'Skipped')}><Icon name="skip" size={21}/></button>
                  <button className="main-play-button" title={player.paused ? 'Resume' : 'Pause'} aria-label={player.paused ? 'Resume playback' : 'Pause playback'} disabled={busy || !player.current} onClick={() => runAction(() => control(guildId, player.paused ? 'resume' : 'pause'), player.paused ? 'Playback resumed' : 'Playback paused')}><Icon name={player.paused ? 'play' : 'pause'} size={21}/></button>
                  <button className="icon-button transport-skip" title="Stop and clear queue" aria-label="Stop playback" disabled={busy || (!player.current && !player.queue?.length)} onClick={() => runAction(() => control(guildId, 'stop'), 'Playback stopped')}><Icon name="stop" size={18}/></button>
                </div>
                <div className="volume-control">
                  <Icon name="volume" size={18}/>
                  <input aria-label="Volume" type="range" min="0" max="100" value={volumePercent} onChange={(event) => changeVolume(event.target.value)} onPointerUp={persistVolume} onKeyUp={persistVolume} style={{ '--range-value': `${volumePercent}%` }} />
                  <span>{volumePercent}%</span>
                </div>
              </div>
            </div>
            <div className="now-decoration"><span/><span/><span/></div>
          </section>

          <div className="content-grid">
            <div className="primary-column">
              <section className="panel search-panel" id="search">
                <div className="panel-heading">
                  <div><div className="section-kicker">FIND YOUR NEXT TRACK</div><h3>Music search</h3></div>
                  <span className="panel-icon"><Icon name="search" size={17}/></span>
                </div>
                <form className="search-form" onSubmit={submitSearch}>
                  <Icon name="search" size={18}/>
                  <input value={search} onChange={(event) => setSearch(event.target.value)} placeholder="Search a song or paste a YouTube link" aria-label="Search for music" maxLength={500}/>
                  <button type="submit" disabled={busy || !search.trim() || !guildId}><Icon name="plus" size={16}/> Add to queue</button>
                </form>
                <div className="search-footnote"><span className="small-pulse"/> Adds to the same queue used by Discord</div>
              </section>

              <section className="panel queue-panel" id="queue">
                <div className="panel-heading queue-heading">
                  <div><div className="section-kicker">UP NEXT</div><h3>Queue <span className="count-badge">{player.queue?.length || 0}</span></h3></div>
                  <button className="text-button" disabled={busy || (player.queue?.length || 0) < 2} onClick={() => runAction(() => shuffleQueue(guildId), 'Queue shuffled')}><Icon name="shuffle" size={15}/> Shuffle</button>
                </div>
                {player.queue?.length ? <div className="queue-list">
                  {player.queue.map((song, index) => <div className="queue-item" key={`${songKey(song)}-${index}`}>
                    <span className="queue-index">{String(index + 1).padStart(2, '0')}</span>
                    <div className="queue-thumb">{song.thumbnail ? <img src={song.thumbnail} alt=""/> : <Icon name="music" size={16}/>}</div>
                    <div className="queue-song"><b title={song.title}>{song.title}</b><span>{song.uploader || 'YouTube'}</span></div>
                    <span className="queue-duration">{song.duration ? formatTime(song.duration) : '--:--'}</span>
                    <button className="remove-button" aria-label={`Remove ${song.title}`} title="Remove from queue" onClick={() => runAction(() => removeSong(guildId, index + 1), 'Removed from queue')}><Icon name="x" size={17}/></button>
                  </div>)}
                </div> : <div className="queue-empty"><span className="queue-empty-icon"><Icon name="queue" size={20}/></span><b>Your queue is clear</b><span>Search for a track to add it next.</span></div>}
                {player.queue?.length > 5 && <div className="queue-footer">Showing {player.queue.length} upcoming tracks</div>}
              </section>
            </div>

            <div className="secondary-column">
              <section className="connection-card">
                <div className="connection-top"><div><div className="section-kicker">DISCORD VOICE</div><h3>Connection</h3></div><span className={`connection-icon ${player.connected ? 'online' : ''}`}><Icon name="headphones" size={19}/></span></div>
                <div className="connection-state"><span className={`state-light ${player.connected ? 'online' : ''}`} /><b>{player.connected ? 'Connected' : 'Not connected'}</b><span className="state-server">{guild?.name || 'No server selected'}</span></div>
                <div className="connection-channel"><span>VOICE CHANNEL</span><b>{player.voice_channel?.name || channel?.name || 'Choose a channel'}</b></div>
                <button className={`connection-action ${player.connected ? 'disconnect-action' : ''}`} onClick={handleConnect} disabled={busy || !guildId || (!player.connected && !channelId)}>
                  {player.connected ? 'Disconnect' : 'Connect bot'} <span>↗</span>
                </button>
              </section>

              <section className="panel recent-panel" id="recent">
                <div className="panel-heading"><div><div className="section-kicker">YOUR LISTENING HISTORY</div><h3>Recently played</h3></div><span className="panel-icon"><Icon name="clock" size={17}/></span></div>
                {recent.length ? <div className="recent-list">{recent.slice(0, 5).map((song, index) => <div className="recent-item" key={`${songKey(song)}-${index}`}>
                  <div className="recent-thumb">{song.thumbnail ? <img src={song.thumbnail} alt=""/> : <Icon name="music" size={15}/>}</div>
                  <div className="recent-song"><b title={song.title}>{song.title}</b><span>{song.uploader || 'YouTube'}</span></div>
                  {index === 0 && player.playing && <span className="recent-now">NOW</span>}
                </div>)}</div> : <div className="recent-empty">Tracks you play will show up here.</div>}
                <p className="local-history-note">History is saved in this browser.</p>
              </section>

              <div className="tip-card"><span className="tip-star">✳</span><div><b>One queue, two ways to control.</b><p>Changes made in Discord show up here in real time.</p></div></div>
            </div>
          </div>
          <footer className="page-footer"><span>RIFFORA / PERSONAL MUSIC CONTROL</span><span><i className={botOnline ? 'online' : ''}/> {botOnline ? 'ALL SYSTEMS READY' : 'WAITING FOR BOT'}</span></footer>
        </div>
      </main>
      {message && <div className="toast" role="status"><span className="toast-mark"><Icon name="check" size={15}/></span>{message}</div>}
    </div>
  )
}

export default App
