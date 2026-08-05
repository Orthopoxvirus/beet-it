// API client for the Titles page — track-level search with BPM filtering.
// Mirrors the snake_case wire shape of the album endpoints.

const API_URL = import.meta.env.VITE_API_URL || '/api'

export interface TitleRow {
  id: number
  title: string
  artist: string
  albumartist: string
  album: string
  album_id: number | null
  bpm: number | null
  length: number | null
  format: string | null
  bitrate: number | null
}

export interface TitlesListResponse {
  items: TitleRow[]
  total: number
  page: number
  per_page: number
}

export interface TitleIdRow {
  id: number
  title: string
  artist: string
}

export interface TitleIdsResponse {
  items: TitleIdRow[]
  total: number
}

export interface TitleFilters {
  search?: string
  bpmMin?: number
  bpmMax?: number
  includeHalfDouble?: boolean
  /** Selected album artists (OR-combined). Empty/undefined = no artist filter. */
  albumArtists?: string[]
}

/** Album artists split by whether they appear in the current search+BPM result. */
export interface TitleArtistsResponse {
  in_result: string[]
  others: string[]
  total: number
}

export class TitlesApiError extends Error {
  status: number
  constructor(message: string, status: number) {
    super(message)
    this.name = 'TitlesApiError'
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
    throw new TitlesApiError(detail, response.status)
  }
  return response.json()
}

// The search + BPM half of the filters — shared by the listing and the
// artist-dropdown endpoint (the artist selection is deliberately left out of
// the dropdown query so the choices stay stable).
function searchBpmParams(filters: TitleFilters): URLSearchParams {
  const params = new URLSearchParams()
  if (filters.search) params.set('search', filters.search)
  if (filters.bpmMin != null && filters.bpmMax != null) {
    params.set('bpm_min', String(filters.bpmMin))
    params.set('bpm_max', String(filters.bpmMax))
    if (filters.includeHalfDouble) params.set('include_half_double', 'true')
  }
  return params
}

function filterParams(filters: TitleFilters): URLSearchParams {
  const params = searchBpmParams(filters)
  for (const artist of filters.albumArtists ?? []) {
    params.append('album_artist', artist)
  }
  return params
}

export async function fetchTitles(
  slug: string,
  filters: TitleFilters,
  page: number,
  perPage: number
): Promise<TitlesListResponse> {
  const params = filterParams(filters)
  params.set('page', String(page))
  params.set('per_page', String(perPage))
  const response = await fetch(
    `${API_URL}/v1/libraries/${encodeURIComponent(slug)}/titles?${params}`
  )
  return handleResponse<TitlesListResponse>(response)
}

/** Every title matching the filters (minimal rows), for select-all-results. */
export async function fetchTitleIds(
  slug: string,
  filters: TitleFilters
): Promise<TitleIdsResponse> {
  const params = filterParams(filters)
  const response = await fetch(
    `${API_URL}/v1/libraries/${encodeURIComponent(slug)}/titles/ids?${params}`
  )
  return handleResponse<TitleIdsResponse>(response)
}

/**
 * Album artists for the filter dropdown, grouped by the current result.
 * Only the search + BPM filters are sent — never the artist selection — so
 * the list stays stable as the user checks and unchecks artists.
 */
export async function fetchTitleArtists(
  slug: string,
  filters: TitleFilters
): Promise<TitleArtistsResponse> {
  const params = searchBpmParams(filters)
  const response = await fetch(
    `${API_URL}/v1/libraries/${encodeURIComponent(slug)}/titles/artists?${params}`
  )
  return handleResponse<TitleArtistsResponse>(response)
}

/** Direct-download URL for one title (Content-Disposition attachment). */
export function getTitleDownloadUrl(slug: string, trackId: number): string {
  return `${API_URL}/v1/libraries/${encodeURIComponent(slug)}/tracks/${trackId}/stream?download=true`
}

/** Inline-playback stream URL for one title (no attachment disposition). */
export function getTitleStreamUrl(slug: string, trackId: number): string {
  return `${API_URL}/v1/libraries/${encodeURIComponent(slug)}/tracks/${trackId}/stream`
}
