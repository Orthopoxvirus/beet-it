const API_URL = import.meta.env.VITE_API_URL || '/api'

// ============================================================================
// TypeScript Interfaces
// ============================================================================

export interface Album {
  id: number
  title: string
  artist: string
  cover_art_path: string | null
  /** Cover file mtime; pass to getAlbumCoverUrl as a cache-buster. */
  cover_version?: number | null
}

export interface AlbumListResponse {
  items: Album[]
  total: number
  skip: number
  limit: number
}

/**
 * Response from GET /api/v1/libraries/{slug}/albums/letters endpoint.
 */
export interface AlbumLettersResponse {
  /** Array of letters (A-Z) and '#' that have at least one album */
  letters: string[]
}

/**
 * Complete album metadata returned by the album detail endpoint.
 */
export interface AlbumDetail {
  id: number
  title: string
  artist: string
  year: number | null
  genre: string | null
  label: string | null
  total_tracks: number
  total_duration: number
  cover_art_path: string | null
  /** Cover file mtime; pass to getAlbumCoverUrl as a cache-buster. */
  cover_version?: number | null
  disc_count: number
  added: string
  album_type: string | null
  mb_albumid: string | null
  format: string | null
  bitrate: number | null
  sample_rate: number | null
  bit_depth: number | null
  channels: number | null
}

/**
 * Track metadata for a single track.
 */
export interface Track {
  id: number
  title: string
  artist: string
  album_id: number
  track_number: number
  disc_number: number
  duration: number
  format: string
  bitrate: number
  sample_rate: number
  channels: number
  mb_trackid: string | null
}

/**
 * Response containing a list of tracks.
 */
export interface TrackListResponse {
  items: Track[]
  total: number
}

/**
 * Response returned after successful cover art upload or URL download.
 */
export interface CoverUploadResponse {
  status: 'success'
  album_id: number
  cover_path: string
  message: string
}

/**
 * Request body for downloading cover art from a URL.
 */
export interface CoverUrlRequest {
  url: string
}

/**
 * Request body for moving an album to a different library.
 */
export interface MoveAlbumRequest {
  target_library_slug: string
}

/**
 * Response from POST /albums/{id}/move — the move runs asynchronously,
 * so the response only confirms that the job was queued.
 */
export interface MoveAlbumResponse {
  status: 'queued'
  job_id: string
  task_event_id: number | null
  source_library_slug: string
  target_library_slug: string
  album_id: number
}

/**
 * Response from POST /albums/{id}/convert-wav — the conversion runs
 * asynchronously; poll the audio-op status endpoint with `job_id`.
 */
export interface ConvertAlbumWavResponse {
  status: 'queued'
  job_id: string
  album_id: number
  wav_track_count: number
  message: string
}

export interface ApiError {
  detail: string
}

// ============================================================================
// API Error Handling
// ============================================================================

export class AlbumApiError extends Error {
  status: number

  constructor(message: string, status: number) {
    super(message)
    this.name = 'AlbumApiError'
    this.status = status
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
    throw new AlbumApiError(errorData.detail, response.status)
  }
  return response.json()
}

// ============================================================================
// API Client Functions
// ============================================================================

export async function fetchLibraryAlbums(
  slug: string,
  skip = 0,
  limit = 50
): Promise<AlbumListResponse> {
  const params = new URLSearchParams({
    skip: skip.toString(),
    limit: limit.toString(),
  })
  const response = await fetch(
    `${API_URL}/v1/libraries/${slug}/albums?${params}`
  )
  return handleResponse<AlbumListResponse>(response)
}

/**
 * Fetch the list of starting letters that have albums in a library.
 *
 * @param slug - The library's slug identifier
 * @returns Promise resolving to array of letters with albums
 * @throws AlbumApiError if the request fails
 */
export async function fetchAlbumLetters(slug: string): Promise<string[]> {
  const response = await fetch(
    `${API_URL}/v1/libraries/${encodeURIComponent(slug)}/albums/letters`
  )
  const data = await handleResponse<AlbumLettersResponse>(response)
  return data.letters
}

// ============================================================================
// Helper Functions
// ============================================================================

/**
 * Constructs the URL for fetching album cover art.
 *
 * Pass `size` to request a cached WebP thumbnail (longest edge in pixels).
 * The backend whitelists 64 / 128 / 192 / 256 / 384 / 512 / 768 / 1024 —
 * pick the smallest one that still looks crisp at the rendered tile size.
 * Original artwork is returned when `size` is omitted.
 *
 * Pass `version` (an album's `cover_version`) to bust the browser cache when
 * the cover is replaced — the cover endpoint serves immutable responses, so
 * without a changing URL a swapped cover would keep showing the old image.
 */
export function getAlbumCoverUrl(
  slug: string,
  albumId: number,
  size?: number,
  version?: number | null
): string {
  const base = `${API_URL}/v1/libraries/${slug}/albums/${albumId}/cover`
  const params = new URLSearchParams()
  if (size) params.set('size', String(size))
  if (version != null) params.set('v', String(version))
  const query = params.toString()
  return query ? `${base}?${query}` : base
}

/**
 * Constructs the URL for streaming a track's audio.
 */
export function getTrackStreamUrl(slug: string, trackId: number): string {
  return `${API_URL}/v1/libraries/${slug}/tracks/${trackId}/stream`
}

/**
 * Constructs the URL for downloading an album as a ZIP archive.
 *
 * The backend streams the archive and sets the filename via
 * Content-Disposition, so this URL is meant to be used directly as an
 * `<a href download>` target rather than fetched into memory.
 */
export function getAlbumDownloadUrl(slug: string, albumId: number): string {
  return `${API_URL}/v1/libraries/${slug}/albums/${albumId}/download`
}

// ============================================================================
// Album Detail API Functions
// ============================================================================

/**
 * Fetch detailed album metadata.
 *
 * @param slug - The library's slug identifier
 * @param albumId - The album's ID
 * @returns Promise resolving to album detail object
 * @throws AlbumApiError if the request fails
 */
export async function fetchAlbumDetail(
  slug: string,
  albumId: number
): Promise<AlbumDetail> {
  const response = await fetch(
    `${API_URL}/v1/libraries/${encodeURIComponent(slug)}/albums/${albumId}`
  )
  return handleResponse<AlbumDetail>(response)
}

/**
 * Fetch all tracks for an album.
 *
 * @param slug - The library's slug identifier
 * @param albumId - The album's ID
 * @returns Promise resolving to track list response
 * @throws AlbumApiError if the request fails
 */
export async function fetchAlbumTracks(
  slug: string,
  albumId: number
): Promise<TrackListResponse> {
  const response = await fetch(
    `${API_URL}/v1/libraries/${encodeURIComponent(slug)}/albums/${albumId}/tracks`
  )
  return handleResponse<TrackListResponse>(response)
}

// ============================================================================
// Cover Art Management API Functions
// ============================================================================

/**
 * Upload cover art for an album.
 *
 * @param slug - The library's slug identifier
 * @param albumId - The album's ID
 * @param file - The image file to upload
 * @returns Promise resolving to cover upload response
 * @throws AlbumApiError if the request fails
 */
export async function uploadCoverArt(
  slug: string,
  albumId: number,
  file: File
): Promise<CoverUploadResponse> {
  const formData = new FormData()
  formData.append('file', file)

  const response = await fetch(
    `${API_URL}/v1/libraries/${encodeURIComponent(slug)}/albums/${albumId}/cover`,
    {
      method: 'POST',
      body: formData,
    }
  )
  return handleResponse<CoverUploadResponse>(response)
}

/**
 * Download and set cover art from a URL.
 *
 * @param slug - The library's slug identifier
 * @param albumId - The album's ID
 * @param url - The URL to download the cover art from
 * @returns Promise resolving to cover upload response
 * @throws AlbumApiError if the request fails
 */
export async function downloadCoverArtFromUrl(
  slug: string,
  albumId: number,
  url: string
): Promise<CoverUploadResponse> {
  const response = await fetch(
    `${API_URL}/v1/libraries/${encodeURIComponent(slug)}/albums/${albumId}/cover/url`,
    {
      method: 'POST',
      headers: {
        'Content-Type': 'application/json',
      },
      body: JSON.stringify({ url }),
    }
  )
  return handleResponse<CoverUploadResponse>(response)
}

// ============================================================================
// Move Album API Function
// ============================================================================

/**
 * Queue a job to move an album to a different library.
 *
 * The actual file move and DB sync runs asynchronously; the activity
 * monitor reports progress via the standard task-event stream.
 *
 * @param slug - Source library slug
 * @param albumId - Album ID in the source library
 * @param targetLibrarySlug - Destination library slug
 * @throws AlbumApiError on validation / conflict failures
 */
export async function moveAlbumToLibrary(
  slug: string,
  albumId: number,
  targetLibrarySlug: string
): Promise<MoveAlbumResponse> {
  const response = await fetch(
    `${API_URL}/v1/libraries/${encodeURIComponent(slug)}/albums/${albumId}/move`,
    {
      method: 'POST',
      headers: {
        'Content-Type': 'application/json',
      },
      body: JSON.stringify({ target_library_slug: targetLibrarySlug }),
    }
  )
  return handleResponse<MoveAlbumResponse>(response)
}

/**
 * Queue an in-place WAV→FLAC conversion for an already-imported album.
 *
 * Each WAV track is losslessly transcoded to a sibling .flac and the beets
 * database entry is updated to point at the new file. With `deleteOriginals`
 * (the default) the WAVs are removed once their FLACs are verified.
 *
 * @throws AlbumApiError on validation / conflict failures (409 = an audio
 *   operation is already running for this album)
 */
export async function convertAlbumWav(
  slug: string,
  albumId: number,
  deleteOriginals: boolean
): Promise<ConvertAlbumWavResponse> {
  const response = await fetch(
    `${API_URL}/v1/libraries/${encodeURIComponent(slug)}/albums/${albumId}/convert-wav`,
    {
      method: 'POST',
      headers: {
        'Content-Type': 'application/json',
      },
      body: JSON.stringify({ delete_originals: deleteOriginals }),
    }
  )
  return handleResponse<ConvertAlbumWavResponse>(response)
}

/**
 * How to dispose of an album's files when deleting it from a library. The
 * beets DB rows are removed in every mode; the mode only decides the fate of
 * the files on disk. `detach` removes only the DB rows and never touches
 * disk — the sole mode that works on a duplicate row sharing its folder with
 * another album (the file modes refuse shared folders with a 409).
 */
export type DeleteAlbumMode = 'delete_files' | 'move_to_import' | 'detach'

export interface DeleteAlbumResponse {
  status: 'deleted'
  album_id: number
  mode: DeleteAlbumMode
  /** True when the folder was erased from disk. */
  files_deleted: boolean
  /** Destination folder when the album was moved to the import staging area. */
  relocated_to: string | null
}

/**
 * Delete a single album from a library (synchronous).
 *
 * `mode = 'delete_files'` erases the album folder from disk; `'move_to_import'`
 * moves it back to the library's import staging area for re-import. Either way
 * the album disappears from the beets DB.
 *
 * @throws AlbumApiError on validation / conflict failures
 */
export async function deleteAlbum(
  slug: string,
  albumId: number,
  mode: DeleteAlbumMode
): Promise<DeleteAlbumResponse> {
  const response = await fetch(
    `${API_URL}/v1/libraries/${encodeURIComponent(slug)}/albums/${albumId}?mode=${mode}`,
    { method: 'DELETE' }
  )
  return handleResponse<DeleteAlbumResponse>(response)
}

// ============================================================================
// Online cover-art search (Maintenance feature, issue #147)
// ============================================================================

export interface CoverSearchResult {
  url: string
  source: string
  width: number | null
  height: number | null
}

export interface CoverSearchResponse {
  query: string
  results: CoverSearchResult[]
}

/**
 * Search public sources (iTunes / Deezer / Cover Art Archive) for cover-art
 * candidates for an album. The chosen URL is applied via downloadCoverArtFromUrl.
 */
export async function searchCoverArt(
  slug: string,
  albumId: number
): Promise<CoverSearchResponse> {
  const response = await fetch(
    `${API_URL}/v1/libraries/${encodeURIComponent(slug)}/albums/${albumId}/cover/search`
  )
  return handleResponse<CoverSearchResponse>(response)
}
