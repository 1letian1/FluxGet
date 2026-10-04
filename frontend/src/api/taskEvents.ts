import { getRuntimeConfig } from './runtime'

export type ApiTask = {
  id: string
  url: string
  filename: string
  source_type: 'direct' | 'rule'
  status: string
  bytes_downloaded: number
  bytes_total: number | null
  progress: number | null
  speed_bytes_per_second?: number | null
  rule_id?: string | null
  error_message?: string | null
}

export type TaskEvent = {
  type: string
  data: ApiTask | Record<string, unknown>
  occurred_at: string | null
}

type TaskEventsHandlers = {
  onSnapshot: (tasks: ApiTask[]) => void
  onEvent: (event: TaskEvent) => void
  onConnectionChange?: (connected: boolean) => void
}

/** Keep the UI synchronized from persisted REST snapshots and live task events. */
export async function connectTaskEvents(handlers: TaskEventsHandlers): Promise<() => void> {
  const config = await getRuntimeConfig()
  const apiBase = new URL(config.apiBaseUrl, window.location.href)
  const socketUrl = new URL('/ws/events', apiBase)
  socketUrl.protocol = socketUrl.protocol === 'https:' ? 'wss:' : 'ws:'
  if (config.sessionToken) socketUrl.searchParams.set('session_token', config.sessionToken)

  let stopped = false
  let socket: WebSocket | undefined
  let heartbeat: number | undefined
  let reconnectTimer: number | undefined
  let reconnectAttempt = 0
  let generation = 0
  let resyncing = false
  let deferredEvents: TaskEvent[] = []

  const loadSnapshot = async (): Promise<ApiTask[]> => {
    const headers = config.sessionToken ? { 'X-Session-Token': config.sessionToken } : undefined
    const response = await fetch(new URL('/api/v1/tasks', apiBase), { headers })
    if (!response.ok) throw new Error(`Task snapshot failed (${response.status})`)
    const body = await response.json() as { items?: ApiTask[] }
    return Array.isArray(body.items) ? body.items : []
  }

  const processEvent = (event: TaskEvent, source: WebSocket) => {
    if (event.type === 'connection.resync_required') {
      if (resyncing) return
      resyncing = true
      void loadSnapshot().then((snapshot) => {
        if (stopped || source !== socket || source.readyState !== WebSocket.OPEN) return
        handlers.onSnapshot(snapshot)
        resyncing = false
        const pending = deferredEvents
        deferredEvents = []
        pending.forEach((item) => processEvent(item, source))
      }).catch(() => source.close())
      return
    }
    if (event.type === 'connection.pong') return
    if (resyncing) deferredEvents.push(event)
    else handlers.onEvent(event)
  }

  const scheduleReconnect = () => {
    if (stopped || reconnectTimer !== undefined) return
    const delay = Math.min(1000 * 2 ** reconnectAttempt, 15000)
    reconnectAttempt += 1
    reconnectTimer = window.setTimeout(() => {
      reconnectTimer = undefined
      openSocket()
    }, delay)
  }

  const openSocket = () => {
    if (stopped) return
    const currentGeneration = ++generation
    const nextSocket = new WebSocket(socketUrl)
    socket = nextSocket
    nextSocket.onopen = async () => {
      if (stopped || currentGeneration !== generation) return
      reconnectAttempt = 0
      handlers.onConnectionChange?.(true)
      try {
        // Subscribe first, then reconcile any events that arrived while the snapshot loaded.
        const buffered: TaskEvent[] = []
        const receive = nextSocket.onmessage
        nextSocket.onmessage = (message) => {
          try {
            buffered.push(JSON.parse(String(message.data)) as TaskEvent)
          } catch {
            // Ignore malformed frames; the next snapshot repairs task state.
          }
        }
        const snapshot = await loadSnapshot()
        if (stopped || currentGeneration !== generation || nextSocket.readyState !== WebSocket.OPEN) return
        handlers.onSnapshot(snapshot)
        nextSocket.onmessage = receive
        for (const event of buffered) processEvent(event, nextSocket)
      } catch {
        nextSocket.close()
      }
      heartbeat = window.setInterval(() => {
        if (nextSocket.readyState === WebSocket.OPEN) nextSocket.send('ping')
      }, 25000)
    }
    nextSocket.onmessage = (message) => {
      try {
        const event = JSON.parse(String(message.data)) as TaskEvent
        processEvent(event, nextSocket)
      } catch {
        // Ignore malformed frames; the next snapshot repairs task state.
      }
    }
    nextSocket.onclose = () => {
      if (socket === nextSocket) socket = undefined
      if (heartbeat !== undefined) window.clearInterval(heartbeat)
      heartbeat = undefined
      resyncing = false
      deferredEvents = []
      handlers.onConnectionChange?.(false)
      scheduleReconnect()
    }
    nextSocket.onerror = () => nextSocket.close()
  }

  openSocket()
  return () => {
    stopped = true
    generation += 1
    if (reconnectTimer !== undefined) window.clearTimeout(reconnectTimer)
    if (heartbeat !== undefined) window.clearInterval(heartbeat)
    socket?.close()
  }
}
