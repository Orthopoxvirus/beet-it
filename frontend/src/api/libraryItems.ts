import type {
  TransformationRule,
  BatchPreviewResponse,
  ItemPreview,
  PreviewWarning,
  PreviewError,
} from '@/types/batch-tag-editor'

const API_URL = import.meta.env.VITE_API_URL || '/api'

// ============================================================================
// TypeScript Interfaces
// ============================================================================

/**
 * A library item (track) from the beets database.
 */
export interface LibraryItem {
  id: number
  title: string
  artist: string
  album: string
  album_artist: string
  album_id: number
  track_number: number
  disc_number: number
  genre: string | null
  path: string
  duration: number
  format: string
  bitrate: number
}

/**
 * Response from GET /api/v1/libraries/{slug}/library-items endpoint.
 */
export interface LibraryItemsResponse {
  items: LibraryItem[]
  total: number
  page: number
  per_page: number
  album_filter: string | null
}

/**
 * Album summary for album picker.
 */
export interface AlbumSummary {
  id: number
  title: string
  artist: string
  track_count: number
}

/**
 * Response from GET /api/v1/libraries/{slug}/library-items/albums endpoint.
 */
export interface LibraryAlbumsResponse {
  albums: AlbumSummary[]
  total: number
}

/**
 * Per-album status in batch update response.
 */
export interface AlbumSyncStatus {
  album: string
  status: 'pending' | 'syncing' | 'success' | 'failed'
  error?: string
}

/**
 * Per-item result inside the batch-update JSON response.
 */
export interface RawItemResult {
  item_id: number
  status: 'success' | 'failed'
  changes_applied?: Record<string, string> | null
  error?: {
    code: string
    message: string
    file_path?: string | null
  } | null
}

/**
 * Response from POST /api/v1/libraries/{slug}/library-items/batch-update endpoint.
 */
export interface LibraryBatchUpdateResponse {
  status: 'submitted' | 'completed' | 'partial' | 'pending_sync'
  job_id: string
  items_total: number
  items_succeeded: number
  items_failed: number
  albums_to_sync: string[]
  results?: RawItemResult[]
}

/**
 * Response from GET /api/v1/libraries/{slug}/batch-update-status/{job_id} endpoint.
 */
export interface BatchUpdateStatusResponse {
  job_id: string
  status: 'pending' | 'running' | 'completed' | 'partial' | 'failed'
  started_at: string | null
  completed_at: string | null
  file_writes: {
    total: number
    succeeded: number
    failed: number
  }
  beets_updates: AlbumSyncStatus[]
  error?: string
}

export interface ApiError {
  detail: string
  code?: string
}

// ============================================================================
// API Error Handling
// ============================================================================

export class LibraryItemsApiError extends Error {
  code?: string
  status: number

  constructor(message: string, status: number, code?: string) {
    super(message)
    this.name = 'LibraryItemsApiError'
    this.status = status
    this.code = code
  }
}

/**
 * Flatten a FastAPI / Pydantic error payload into a single string so it can
 * surface in UI components that only expect Error.message. Handles three
 * shapes:
 *   - string: returned as-is
 *   - array of {loc, msg, type} (pydantic 422): joined as "loc: msg" lines
 *   - anything else: JSON-stringified as a fallback so we don't lose info
 */
function formatErrorDetail(detail: unknown): string {
  if (typeof detail === 'string') return detail
  if (Array.isArray(detail)) {
    const parts: string[] = []
    for (const entry of detail) {
      if (entry && typeof entry === 'object') {
        const e = entry as { loc?: unknown[]; msg?: unknown; type?: unknown }
        const loc = Array.isArray(e.loc)
          ? e.loc
              .filter((segment) => segment !== 'body')
              .map(String)
              .join('.')
          : ''
        const msg = typeof e.msg === 'string' ? e.msg : JSON.stringify(e)
        parts.push(loc ? `${loc}: ${msg}` : msg)
      } else if (typeof entry === 'string') {
        parts.push(entry)
      } else {
        parts.push(JSON.stringify(entry))
      }
    }
    return parts.join('; ')
  }
  if (detail == null) return 'Unknown error'
  try {
    return JSON.stringify(detail)
  } catch {
    return String(detail)
  }
}

async function handleResponse<T>(response: Response): Promise<T> {
  if (!response.ok) {
    let errorData: { detail?: unknown; code?: string } = {
      detail: 'An unknown error occurred',
    }
    try {
      errorData = await response.json()
    } catch {
      // Response body may not be JSON
    }
    throw new LibraryItemsApiError(
      formatErrorDetail(errorData.detail),
      response.status,
      errorData.code
    )
  }
  return response.json()
}

// ============================================================================
// Response Transformers (snake_case to camelCase)
// ============================================================================

interface RawPreviewWarning {
  tag: string
  code: string
  message: string
}

interface RawItemPreview {
  item_id: number
  changes: Record<string, string>
  warnings?: RawPreviewWarning[]
}

interface RawPreviewError {
  item_id: number
  code: string
  message: string
}

interface RawBatchPreviewResponse {
  previews: RawItemPreview[]
  errors: RawPreviewError[]
}

function transformPreviewWarning(raw: RawPreviewWarning): PreviewWarning {
  return {
    tag: raw.tag as PreviewWarning['tag'],
    code: raw.code,
    message: raw.message,
  }
}

function transformItemPreview(raw: RawItemPreview): ItemPreview {
  return {
    itemId: raw.item_id,
    changes: raw.changes as ItemPreview['changes'],
    warnings: raw.warnings?.map(transformPreviewWarning),
  }
}

function transformPreviewError(raw: RawPreviewError): PreviewError {
  return {
    itemId: raw.item_id,
    code: raw.code,
    message: raw.message,
  }
}

function transformBatchPreviewResponse(raw: RawBatchPreviewResponse): BatchPreviewResponse {
  return {
    previews: raw.previews.map(transformItemPreview),
    errors: raw.errors.map(transformPreviewError),
  }
}

// ============================================================================
// Query Parameters
// ============================================================================

export interface LibraryItemsParams {
  album?: string
  /** Single album id (back-compat). Use `albumIds` for multi-album fetches. */
  album_id?: number
  /**
   * Multiple beets album ids — emitted as repeated `album_id=N` query params
   * so the server-side filter uses `WHERE items.album_id IN (...)`.
   */
  albumIds?: number[]
  page?: number
  per_page?: number
}

// ============================================================================
// API Client Functions
// ============================================================================

/**
 * Fetch library items from the beets database.
 *
 * @param slug - The library slug
 * @param params - Query parameters for filtering and pagination
 * @returns Promise resolving to library items response
 */
export async function getLibraryItems(
  slug: string,
  params: LibraryItemsParams = {}
): Promise<LibraryItemsResponse> {
  const queryParams = new URLSearchParams()

  if (params.album !== undefined) {
    queryParams.set('album', params.album)
  }
  if (params.album_id !== undefined) {
    queryParams.append('album_id', String(params.album_id))
  }
  if (params.albumIds && params.albumIds.length > 0) {
    for (const id of params.albumIds) {
      queryParams.append('album_id', String(id))
    }
  }
  if (params.page !== undefined) {
    queryParams.set('page', params.page.toString())
  }
  if (params.per_page !== undefined) {
    queryParams.set('per_page', params.per_page.toString())
  }

  const queryString = queryParams.toString()
  const url = `${API_URL}/v1/libraries/${encodeURIComponent(slug)}/library-items${queryString ? `?${queryString}` : ''}`

  const response = await fetch(url)
  return handleResponse<LibraryItemsResponse>(response)
}

/**
 * Fetch list of albums for the album picker.
 *
 * @param slug - The library slug
 * @returns Promise resolving to album summaries
 */
export async function getLibraryAlbumsForPicker(
  slug: string
): Promise<LibraryAlbumsResponse> {
  const response = await fetch(
    `${API_URL}/v1/libraries/${encodeURIComponent(slug)}/library-items/albums`
  )
  return handleResponse<LibraryAlbumsResponse>(response)
}

/**
 * Preview tag transformations on library items without applying changes.
 *
 * @param slug - The library slug
 * @param itemIds - Array of item IDs to preview
 * @param rules - Transformation rules to apply
 * @returns Promise resolving to preview response
 */
export async function previewLibraryItems(
  slug: string,
  itemIds: number[],
  rules: TransformationRule[]
): Promise<BatchPreviewResponse> {
  const response = await fetch(
    `${API_URL}/v1/libraries/${encodeURIComponent(slug)}/library-items/preview`,
    {
      method: 'POST',
      headers: {
        'Content-Type': 'application/json',
      },
      body: JSON.stringify({
        item_ids: itemIds,
        rules: rules,
      }),
    }
  )

  const raw = await handleResponse<RawBatchPreviewResponse>(response)
  return transformBatchPreviewResponse(raw)
}

/**
 * Apply batch updates to library items and trigger beets database sync.
 *
 * @param slug - The library slug
 * @param itemIds - Array of item IDs to update
 * @param rules - Transformation rules to apply
 * @returns Promise resolving to batch update response with job ID
 */
export async function batchUpdateLibraryItems(
  slug: string,
  itemIds: number[],
  rules: TransformationRule[]
): Promise<LibraryBatchUpdateResponse> {
  const response = await fetch(
    `${API_URL}/v1/libraries/${encodeURIComponent(slug)}/library-items/batch-update`,
    {
      method: 'POST',
      headers: {
        'Content-Type': 'application/json',
      },
      body: JSON.stringify({
        item_ids: itemIds,
        rules: rules,
      }),
    }
  )

  return handleResponse<LibraryBatchUpdateResponse>(response)
}

/**
 * Get the status of a batch update job including beets sync progress.
 *
 * @param slug - The library slug
 * @param jobId - The job ID returned from batchUpdateLibraryItems
 * @returns Promise resolving to batch update status
 */
export async function getBatchUpdateStatus(
  slug: string,
  jobId: string
): Promise<BatchUpdateStatusResponse> {
  const response = await fetch(
    `${API_URL}/v1/libraries/${encodeURIComponent(slug)}/batch-update-status/${encodeURIComponent(jobId)}`
  )
  return handleResponse<BatchUpdateStatusResponse>(response)
}

/**
 * Get the SSE endpoint URL for library batch updates with progress.
 */
export function getLibraryBatchUpdateSSEUrl(slug: string): string {
  return `${API_URL}/v1/libraries/${encodeURIComponent(slug)}/library-items/batch-update`
}
