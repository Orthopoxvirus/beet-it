// ============================================================================
// Download Center API client
// ============================================================================

const API_URL = import.meta.env.VITE_API_URL || '/api'

export type DownloadJobStatus = 'pending' | 'packing' | 'completed' | 'failed'

export interface DownloadJob {
  id: number
  library_slug: string
  status: DownloadJobStatus
  album_count: number
  processed_count: number
  size_bytes: number | null
  filename: string | null
  error: string | null
  created_at: string
  completed_at: string | null
  expires_at: string | null
}

export interface DownloadJobListResponse {
  items: DownloadJob[]
  total: number
}

export interface AlbumSize {
  size_bytes: number
  track_count: number
}

interface ApiErrorBody {
  detail: string
}

export class DownloadApiError extends Error {
  status: number

  constructor(message: string, status: number) {
    super(message)
    this.name = 'DownloadApiError'
    this.status = status
  }
}

async function handleResponse<T>(response: Response): Promise<T> {
  if (!response.ok) {
    let errorData: ApiErrorBody = { detail: 'An unknown error occurred' }
    try {
      errorData = await response.json()
    } catch {
      // Response body may not be JSON
    }
    throw new DownloadApiError(errorData.detail, response.status)
  }
  return response.json()
}

/** Total on-disk size of an album, for the gathering bar's running sum. */
export async function fetchAlbumSize(slug: string, albumId: number): Promise<AlbumSize> {
  const response = await fetch(
    `${API_URL}/v1/libraries/${encodeURIComponent(slug)}/albums/${albumId}/size`
  )
  return handleResponse<AlbumSize>(response)
}

/** Queue a download of albums and/or single titles, start async packing. */
export async function queueDownload(
  slug: string,
  albumIds: number[],
  trackIds: number[] = []
): Promise<DownloadJob> {
  const response = await fetch(
    `${API_URL}/v1/libraries/${encodeURIComponent(slug)}/downloads`,
    {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ album_ids: albumIds, track_ids: trackIds }),
    }
  )
  return handleResponse<DownloadJob>(response)
}

/** List a library's download jobs, newest first. */
export async function fetchDownloads(slug: string): Promise<DownloadJobListResponse> {
  const response = await fetch(
    `${API_URL}/v1/libraries/${encodeURIComponent(slug)}/downloads`
  )
  return handleResponse<DownloadJobListResponse>(response)
}

/** Delete a download job and its archive. */
export async function deleteDownload(slug: string, jobId: number): Promise<void> {
  const response = await fetch(
    `${API_URL}/v1/libraries/${encodeURIComponent(slug)}/downloads/${jobId}`,
    { method: 'DELETE' }
  )
  if (!response.ok) {
    throw new DownloadApiError('Failed to delete download', response.status)
  }
}

/** Direct-download URL for a finished archive (used in an <a download> link). */
export function getDownloadFileUrl(slug: string, jobId: number): string {
  return `${API_URL}/v1/libraries/${encodeURIComponent(slug)}/downloads/${jobId}/file`
}
