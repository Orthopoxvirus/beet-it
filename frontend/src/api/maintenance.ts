// API client for the library Maintenance feature (issue #147).
// Mirrors the snake_case wire shape used by the album endpoints.

const API_URL = import.meta.env.VITE_API_URL || '/api'

export class MaintenanceApiError extends Error {
  status: number
  constructor(message: string, status: number) {
    super(message)
    this.name = 'MaintenanceApiError'
    this.status = status
  }
}

async function handleResponse<T>(response: Response): Promise<T> {
  if (!response.ok) {
    let detail = 'An unknown error occurred'
    try {
      const data = await response.json()
      detail = data.detail ?? detail
    } catch {
      // body may not be JSON
    }
    throw new MaintenanceApiError(detail, response.status)
  }
  return response.json()
}

// ---------------------------------------------------------------------------
// Missing cover art
// ---------------------------------------------------------------------------
export interface MissingCoverAlbum {
  album_id: number
  title: string
  artist: string
  /** True when the album folder itself is gone from disk (ghost entry) —
   * cover search is pointless; the UI offers a DB-only removal instead. */
  folder_missing: boolean
}

export interface MissingCoverResponse {
  items: MissingCoverAlbum[]
  total: number
}

export async function fetchMissingCover(
  slug: string
): Promise<MissingCoverResponse> {
  const response = await fetch(
    `${API_URL}/v1/libraries/${encodeURIComponent(slug)}/maintenance/missing-cover`
  )
  return handleResponse<MissingCoverResponse>(response)
}

// ---------------------------------------------------------------------------
// Unimported (stray) files
// ---------------------------------------------------------------------------
export interface StrayFile {
  path: string
  name: string
  size: number
  /** True for image files — preview + use-as-cover are offered. */
  is_image: boolean
}

export interface StrayGroup {
  folder: string
  relative_folder: string
  files: StrayFile[]
  total_size: number
  fully_untracked: boolean
  /** The single album living in this folder, if it is a tracked album dir. */
  album_id: number | null
  /** mtime of that album's active cover (cache-buster); null = no cover. */
  cover_version: number | null
}

export interface UnimportedResponse {
  enabled: boolean
  groups: StrayGroup[]
  total_files: number
}

export type StrayAction = 'delete' | 'move_to_import'

export interface StrayActionResult {
  path: string
  status: string
  detail: string | null
  relocated_to: string | null
}

export interface StrayActionResponse {
  results: StrayActionResult[]
}

export interface PluginStatus {
  plugin: string
  enabled: boolean
}

export async function fetchUnimported(
  slug: string
): Promise<UnimportedResponse> {
  const response = await fetch(
    `${API_URL}/v1/libraries/${encodeURIComponent(slug)}/maintenance/unimported`
  )
  return handleResponse<UnimportedResponse>(response)
}

export async function enablePlugin(
  slug: string,
  plugin: string
): Promise<PluginStatus> {
  const response = await fetch(
    `${API_URL}/v1/libraries/${encodeURIComponent(slug)}/maintenance/plugins/${encodeURIComponent(plugin)}/enable`,
    { method: 'POST' }
  )
  return handleResponse<PluginStatus>(response)
}

export async function actOnStrays(
  slug: string,
  paths: string[],
  action: StrayAction
): Promise<StrayActionResponse> {
  const response = await fetch(
    `${API_URL}/v1/libraries/${encodeURIComponent(slug)}/maintenance/unimported/action`,
    {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ paths, action }),
    }
  )
  return handleResponse<StrayActionResponse>(response)
}

/** URL serving a stray image file for preview (no-store on the server). */
export function getStrayPreviewUrl(slug: string, path: string): string {
  return `${API_URL}/v1/libraries/${encodeURIComponent(slug)}/maintenance/unimported/preview?path=${encodeURIComponent(path)}`
}

export interface UseAsCoverResponse {
  status: string
  album_id: number
  cover_path: string
}

export async function useStrayAsCover(
  slug: string,
  path: string
): Promise<UseAsCoverResponse> {
  const response = await fetch(
    `${API_URL}/v1/libraries/${encodeURIComponent(slug)}/maintenance/unimported/use-as-cover`,
    {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ path }),
    }
  )
  return handleResponse<UseAsCoverResponse>(response)
}

// ---------------------------------------------------------------------------
// BPM backfill (autobpm)
// ---------------------------------------------------------------------------
export interface BpmInfo {
  missing_count: number
  estimated_seconds: number
  workers: number
}

export type BpmBackfillState =
  | 'idle'
  | 'queued'
  | 'running'
  | 'completed'
  | 'completed_with_errors'
  | 'cancelled'
  | 'failed'
  | 'unknown'

export interface BpmBackfillStatus {
  status: BpmBackfillState
  total: number
  processed: number
  failed: number
  job_id?: string | null
  error?: string | null
  updated_at?: string | null
  eta_seconds?: number | null
  workers?: number | null
}

export async function fetchBpmInfo(slug: string): Promise<BpmInfo> {
  const response = await fetch(
    `${API_URL}/v1/libraries/${encodeURIComponent(slug)}/maintenance/bpm`
  )
  return handleResponse<BpmInfo>(response)
}

export async function startBpmBackfill(slug: string): Promise<{ job_id: string; total: number }> {
  const response = await fetch(
    `${API_URL}/v1/libraries/${encodeURIComponent(slug)}/maintenance/bpm/backfill`,
    { method: 'POST' }
  )
  return handleResponse(response)
}

export async function fetchBpmBackfillStatus(slug: string): Promise<BpmBackfillStatus> {
  const response = await fetch(
    `${API_URL}/v1/libraries/${encodeURIComponent(slug)}/maintenance/bpm/backfill/status`
  )
  return handleResponse<BpmBackfillStatus>(response)
}

export async function cancelBpmBackfill(slug: string): Promise<void> {
  const response = await fetch(
    `${API_URL}/v1/libraries/${encodeURIComponent(slug)}/maintenance/bpm/backfill/cancel`,
    { method: 'POST' }
  )
  await handleResponse(response)
}
