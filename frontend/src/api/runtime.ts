export type RuntimeConfig = {
  apiBaseUrl: string
  sessionToken: string | null
}

export type NativeBridgeApi = {
  get_runtime_config: () => Promise<{ apiBaseUrl: string; sessionToken: string }>
  choose_folder: (initialDir?: string) => Promise<string | null>
  open_folder: (path: string) => Promise<boolean>
  minimize: () => Promise<void>
  toggle_maximize: () => Promise<void>
  close_window: () => Promise<void>
}

declare global {
  interface Window {
    pywebview?: { api?: NativeBridgeApi }
  }
}

/** Resolve API credentials from the per-instance desktop bridge. */
export async function getRuntimeConfig(): Promise<RuntimeConfig> {
  let nativeApi = getReadyNativeApi()
  if (!nativeApi && (window.pywebview || isDesktopOrigin())) nativeApi = await waitForNativeApi()
  if (nativeApi) {
    const config = await nativeApi.get_runtime_config()
    return { apiBaseUrl: config.apiBaseUrl, sessionToken: config.sessionToken }
  }

  return {
    apiBaseUrl: import.meta.env.VITE_API_BASE_URL ?? window.location.origin,
    sessionToken: null,
  }
}

function isDesktopOrigin(): boolean {
  // The packaged app serves this page from its own random loopback port. In
  // WebView2, the pywebview namespace can appear after the frontend bundle runs.
  return window.location.protocol === 'http:'
    && window.location.hostname === '127.0.0.1'
    && window.location.port !== ''
    && window.location.port !== '5173'
}

function getReadyNativeApi(): NativeBridgeApi | undefined {
  const api = window.pywebview?.api
  return api && typeof api.get_runtime_config === 'function' ? api : undefined
}

function waitForNativeApi(): Promise<NativeBridgeApi | undefined> {
  return new Promise((resolve) => {
    let timeout = 0
    let poll = 0
    const finish = (api: NativeBridgeApi | undefined) => {
      window.clearTimeout(timeout)
      window.clearInterval(poll)
      window.removeEventListener('pywebviewready', onReady)
      resolve(api)
    }
    const onReady = () => {
      const api = getReadyNativeApi()
      if (api) finish(api)
    }

    window.addEventListener('pywebviewready', onReady)
    timeout = window.setTimeout(() => finish(getReadyNativeApi()), 10_000)
    poll = window.setInterval(onReady, 50)
    const api = getReadyNativeApi()
    if (api) finish(api)
  })
}
