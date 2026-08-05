import type {
  ScanStatus,
  ScanTriggerResponse,
  ScanHistoryResponse,
  ImportItemListResponse,
  ImportItemType,
  ImportItemStatus,
} from '@/types/scan'

const API_URL = import.meta.env.VITE_API_URL || '/api'

// ============================================================================
// API Error Handling
// ============================================================================

export interface ApiError {
  detail: string
  code?: string
}

export class ScanApiError extends Error {
  code?: string
  status: number

  constructor(message: string, status: number, code?: string) {
    super(message)
    this.name = 'ScanApiError'
    this.status = status
    this.code = code
  }
}

async function handleResponse<T>(response: Response): Promise<T> {
  if (!response.ok) {
    let errorData: ApiError = { detail: 'An unknown error occurred' }
    try {
      errorData = await response.json()
    } catch {
      // Response body may not be JSON
    }
    throw new ScanApiError(errorData.detail, response.status, errorData.code)
  }
  return response.json()
}

// ============================================================================
// Response Transformers (snake_case to camelCase)
// ============================================================================

interface RawScanInfo {
  id: number
  status: string
  started_at: string
  completed_at: string | null
  items_total: number
  items_processed: number
  progress_percent: number | null
  current_file: string | null
  error_message: string | null
}

interface RawScanStatus {
  library_slug: string
  current_scan: RawScanInfo | null
  queued_scans: number
  blocking_operations: string[]
  watcher_active: boolean
  last_completed_scan: RawScanInfo | null
}

interface RawScanTriggerResponse {
  status: 'started' | 'queued' | 'blocked'
  scan_id: number | null
  message: string
  queue_position: number | null
  blocking_operations: string[]
}

interface RawScanHistoryItem {
  id: number
  status: string
  started_at: string
  completed_at: string | null
  items_total: number
  items_processed: number
  error_message: string | null
}

interface RawScanHistoryResponse {
  items: RawScanHistoryItem[]
  total: number
  skip: number
  limit: number
}

interface RawImportItem {
  id: number
  item_type: string
  path: string
  directory: string
  filename: string
  album: string | null
  album_artist: string | null
  artist: string | null
  title: string | null
  track_number: number | null
  track_total: number | null
  genre: string | null
  format: string | null
  bitrate: number | null
  status: string
  first_seen_at: string
  last_seen_at: string
}

interface RawImportItemListResponse {
  items: RawImportItem[]
  total: number
  skip: number
  limit: number
  scan_id: number | null
  scan_completed_at: string | null
}

function transformScanInfo(raw: RawScanInfo | null) {
  if (!raw) return null
  return {
    id: raw.id,
    status: raw.status as ScanStatus['currentScan'] extends { status: infer S } ? S : never,
    startedAt: raw.started_at,
    completedAt: raw.completed_at,
    itemsTotal: raw.items_total,
    itemsProcessed: raw.items_processed,
    progressPercent: raw.progress_percent,
    currentFile: raw.current_file,
    errorMessage: raw.error_message,
  }
}

function transformScanStatus(raw: RawScanStatus): ScanStatus {
  return {
    librarySlug: raw.library_slug,
    currentScan: transformScanInfo(raw.current_scan),
    queuedScans: raw.queued_scans,
    blockingOperations: raw.blocking_operations as ScanStatus['blockingOperations'],
    watcherActive: raw.watcher_active,
    lastCompletedScan: transformScanInfo(raw.last_completed_scan),
  }
}

function transformScanTriggerResponse(raw: RawScanTriggerResponse): ScanTriggerResponse {
  return {
    status: raw.status,
    scanId: raw.scan_id,
    message: raw.message,
    queuePosition: raw.queue_position,
    blockingOperations: raw.blocking_operations as ScanTriggerResponse['blockingOperations'],
  }
}

function transformScanHistoryResponse(raw: RawScanHistoryResponse): ScanHistoryResponse {
  return {
    items: raw.items.map((item) => ({
      id: item.id,
      status: item.status as ScanHistoryResponse['items'][0]['status'],
      startedAt: item.started_at,
      completedAt: item.completed_at,
      itemsTotal: item.items_total,
      itemsProcessed: item.items_processed,
      errorMessage: item.error_message,
    })),
    total: raw.total,
    skip: raw.skip,
    limit: raw.limit,
  }
}

function transformImportItemListResponse(raw: RawImportItemListResponse): ImportItemListResponse {
  return {
    items: raw.items.map((item) => ({
      id: item.id,
      itemType: item.item_type as ImportItemType,
      path: item.path,
      directory: item.directory,
      filename: item.filename,
      album: item.album,
      albumArtist: item.album_artist,
      artist: item.artist,
      title: item.title,
      trackNumber: item.track_number,
      trackTotal: item.track_total,
      genre: item.genre,
      format: item.format,
      bitrate: item.bitrate,
      status: item.status as ImportItemStatus,
      firstSeenAt: item.first_seen_at,
      lastSeenAt: item.last_seen_at,
    })),
    total: raw.total,
    skip: raw.skip,
    limit: raw.limit,
    scanId: raw.scan_id,
    scanCompletedAt: raw.scan_completed_at,
  }
}

// ============================================================================
// API Client Functions
// ============================================================================

/**
 * Fetch the current scan status for a library
 */
export async function fetchScanStatus(slug: string): Promise<ScanStatus> {
  const response = await fetch(`${API_URL}/libraries/${slug}/scan/status`)
  const raw = await handleResponse<RawScanStatus>(response)
  return transformScanStatus(raw)
}

/**
 * Trigger a manual scan for a library's import folder
 */
export async function triggerScan(slug: string): Promise<ScanTriggerResponse> {
  const response = await fetch(`${API_URL}/libraries/${slug}/scan`, {
    method: 'POST',
  })
  const raw = await handleResponse<RawScanTriggerResponse>(response)
  return transformScanTriggerResponse(raw)
}

/**
 * Fetch scan history for a library
 */
export async function fetchScanHistory(
  slug: string,
  skip = 0,
  limit = 20
): Promise<ScanHistoryResponse> {
  const params = new URLSearchParams({
    skip: skip.toString(),
    limit: limit.toString(),
  })
  const response = await fetch(`${API_URL}/libraries/${slug}/scan/history?${params}`)
  const raw = await handleResponse<RawScanHistoryResponse>(response)
  return transformScanHistoryResponse(raw)
}

/**
 * Fetch import items for a library
 */
export interface FetchImportItemsOptions {
  skip?: number
  limit?: number
  itemType?: ImportItemType | null
  status?: ImportItemStatus | null
  directory?: string | null
  pathPrefix?: string | null
  search?: string | null
}

export async function fetchImportItems(
  slug: string,
  options: FetchImportItemsOptions = {}
): Promise<ImportItemListResponse> {
  const params = new URLSearchParams()

  if (options.skip !== undefined) {
    params.set('skip', options.skip.toString())
  }
  if (options.limit !== undefined) {
    params.set('limit', options.limit.toString())
  }
  if (options.itemType) {
    params.set('item_type', options.itemType)
  }
  if (options.status) {
    params.set('status', options.status)
  }
  if (options.directory) {
    params.set('directory', options.directory)
  }
  if (options.pathPrefix) {
    params.set('path_prefix', options.pathPrefix)
  }
  if (options.search) {
    params.set('search', options.search)
  }

  const response = await fetch(`${API_URL}/libraries/${slug}/import-items?${params}`)
  const raw = await handleResponse<RawImportItemListResponse>(response)
  return transformImportItemListResponse(raw)
}

/**
 * Get the SSE endpoint URL for scan progress
 */
export function getScanProgressSSEUrl(slug: string): string {
  return `${API_URL}/libraries/${slug}/scan/progress`
}

/**
 * Get the audio stream URL for a discovered import item. Suitable as the `src`
 * of an <audio> element; the endpoint supports HTTP Range requests for seeking.
 */
export function getImportItemAudioUrl(slug: string, itemId: number): string {
  return `${API_URL}/libraries/${slug}/import-items/${itemId}/audio`
}
