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
  const nativeApi = window.pywebview?.api
  if (nativeApi) {
    const config = await nativeApi.get_runtime_config()
    return { apiBaseUrl: config.apiBaseUrl, sessionToken: config.sessionToken }
  }

  return {
    apiBaseUrl: import.meta.env.VITE_API_BASE_URL ?? window.location.origin,
    sessionToken: null,
  }
}
