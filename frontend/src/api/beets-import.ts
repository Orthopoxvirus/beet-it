import type {
  AnalyzeAlbumRequest,
  AnalyzeAlbumResponse,
  AnalyzeJobResponse,
  AnalyzeStatusResponse,
  CacheStatusResponse,
  ManualCandidateProvider,
  ManualCandidateRequest,
  ManualCandidateResponse,
  AnalyzeQueueResponse,
  AnalyzeFolderResponse,
  AutoAnalyzeSettingResponse,
  ImportJobRequest,
  ImportJobResponse,
  ImportJobStatusResponse,
  BulkImportStatusResponse,
  SearchCandidatesResponse,
  AudioOpJobResponse,
  AudioOpStatusResponse,
  AudioOpResult,
  ConvertSource,
  ConvertTarget,
} from '@/types/beets-import'

const API_URL = import.meta.env.VITE_API_URL || '/api'
const POLL_INTERVAL_MS = 1000 // Poll every 1 second
const MAX_POLL_ATTEMPTS = 60 // Max 60 seconds

// ============================================================================
// API Error Handling
// ============================================================================

export interface ApiError {
  detail: string
  error_code?: string
}

export class BeetsImportApiError extends Error {
  status: number
  errorCode?: string
  /** Extra payload from error responses (e.g. 409 existing-album details). */
  data?: unknown

  constructor(
    message: string,
    status: number,
    errorCode?: string,
    data?: unknown
  ) {
    super(message)
    this.name = 'BeetsImportApiError'
    this.status = status
    this.errorCode = errorCode
    this.data = data
  }
}

async function handleResponse<T>(response: Response): Promise<T> {
  console.log('[handleResponse] Response status:', response.status, response.ok)

  if (!response.ok) {
    let errorData: ApiError & Record<string, unknown> = {
      detail: 'An unknown error occurred',
    }
    try {
      errorData = await response.json()
    } catch {
      // Response body may not be JSON
    }
    console.error('[handleResponse] Error response:', errorData)
    throw new BeetsImportApiError(
      errorData.detail,
      response.status,
      errorData.error_code,
      errorData
    )
  }

  const data = await response.json()
  console.log('[handleResponse] Success response data:', data)
  return data
}

// ============================================================================
// API Client Functions
// ============================================================================

/**
 * Poll for analysis job status until completed or failed.
 *
 * @param librarySlug - The library slug identifier
 * @param jobId - The job ID to poll for
 * @returns Promise resolving to final analysis results
 * @throws BeetsImportApiError for API errors or timeout
 */
async function pollAnalysisStatus(
  librarySlug: string,
  jobId: string
): Promise<AnalyzeAlbumResponse> {
  console.log('[pollAnalysisStatus] Starting polling for job:', jobId)

  for (let attempt = 0; attempt < MAX_POLL_ATTEMPTS; attempt++) {
    console.log(`[pollAnalysisStatus] Poll attempt ${attempt + 1}/${MAX_POLL_ATTEMPTS}`)

    const response = await fetch(
      `${API_URL}/v1/libraries/${encodeURIComponent(librarySlug)}/beets/analyze/${jobId}/status`
    )

    console.log('[pollAnalysisStatus] Status response:', response.status)
    const statusResponse = await handleResponse<AnalyzeStatusResponse>(response)
    console.log('[pollAnalysisStatus] Status data:', statusResponse)

    if (statusResponse.status === 'completed' && statusResponse.result) {
      console.log('[pollAnalysisStatus] Analysis completed!', statusResponse.result)
      return statusResponse.result
    } else if (statusResponse.status === 'failed') {
      console.error('[pollAnalysisStatus] Analysis failed:', statusResponse.error)
      // Extract error message from error object or string
      const errorMessage = typeof statusResponse.error === 'string'
        ? statusResponse.error
        : statusResponse.error?.message || 'Analysis failed'
      throw new BeetsImportApiError(
        errorMessage,
        500,
        'BEETS_ERROR'
      )
    }

    // Still analyzing, wait before next poll
    console.log('[pollAnalysisStatus] Still analyzing, waiting...')
    await new Promise((resolve) => setTimeout(resolve, POLL_INTERVAL_MS))
  }

  console.error('[pollAnalysisStatus] Polling timeout!')
  throw new BeetsImportApiError(
    'Analysis timeout - exceeded maximum wait time',
    408,
    'ANALYSIS_TIMEOUT'
  )
}

/**
 * Analyze an album folder using beets to find candidate matches.
 *
 * This starts an async analysis job and polls for completion.
 * If forceReanalyze is false (default), the backend may return a cached result instantly.
 *
 * @param librarySlug - The library slug identifier
 * @param albumPath - Path to the album folder (relative to import folder or absolute)
 * @param forceReanalyze - If true, bypass cache and run fresh MusicBrainz analysis
 * @returns Promise resolving to analysis results with candidates
 * @throws BeetsImportApiError for API errors
 */
export async function analyzeAlbum(
  librarySlug: string,
  albumPath: string,
  forceReanalyze = false
): Promise<AnalyzeAlbumResponse> {
  console.log('[analyzeAlbum] Starting analysis for:', { librarySlug, albumPath, forceReanalyze })

  // Start the analysis job
  const response = await fetch(
    `${API_URL}/v1/libraries/${encodeURIComponent(librarySlug)}/beets/analyze`,
    {
      method: 'POST',
      headers: {
        'Content-Type': 'application/json',
      },
      body: JSON.stringify({
        album_path: albumPath,
        force_reanalyze: forceReanalyze,
      } satisfies AnalyzeAlbumRequest),
    }
  )

  console.log('[analyzeAlbum] POST response status:', response.status)
  const jobResponse = await handleResponse<AnalyzeJobResponse>(response)
  console.log('[analyzeAlbum] Job response:', jobResponse)

  // If the backend returned a completed status (cache hit), fetch the result directly
  // without entering the polling loop — this avoids a 1-second wait
  if (jobResponse.status === 'completed') {
    console.log('[analyzeAlbum] Cache hit — fetching result directly without polling')
    const statusUrl = `${API_URL}/v1/libraries/${encodeURIComponent(librarySlug)}/beets/analyze/${jobResponse.jobId}/status`
    const statusResponse = await fetch(statusUrl)
    const statusData = await handleResponse<AnalyzeStatusResponse>(statusResponse)
    if (statusData.status === 'completed' && statusData.result) {
      return statusData.result
    }
  }

  // Poll for completion (for async analysis)
  console.log('[analyzeAlbum] Starting to poll for job_id:', jobResponse.jobId)
  return pollAnalysisStatus(librarySlug, jobResponse.jobId)
}

/**
 * Check cache status for multiple album paths.
 *
 * This endpoint checks whether cached beets analysis results exist for each
 * album path without returning the actual cached data.
 *
 * @param librarySlug - The library slug identifier
 * @param albumPaths - Array of album paths to check cache status for
 * @returns Promise resolving to cache status response with map of path to boolean
 * @throws BeetsImportApiError for API errors
 */
export async function getCacheStatus(
  librarySlug: string,
  albumPaths: string[]
): Promise<CacheStatusResponse> {
  // Build query parameters with repeated album_paths
  const params = new URLSearchParams()
  albumPaths.forEach((path) => params.append('album_paths', path))

  const response = await fetch(
    `${API_URL}/v1/libraries/${encodeURIComponent(librarySlug)}/beets/cache-status?${params}`,
    {
      headers: {
        Accept: 'application/json',
      },
    }
  )

  return handleResponse<CacheStatusResponse>(response)
}

// ============================================================================
// WAV→FLAC convert / duplicate-WAV cleanup
// ============================================================================

const AUDIO_OP_POLL_INTERVAL_MS = 1500
const AUDIO_OP_MAX_POLL_ATTEMPTS = 1240 // ~31 min, just over the convert task cap

/**
 * Fetch the current status of a WAV/WMA convert or dedup job. A single shot —
 * callers that want to surface intermediate states (queued → running) poll this
 * themselves; callers that only care about the final outcome use
 * {@link pollAudioOpStatus}.
 */
export async function getAudioOpStatus(
  librarySlug: string,
  jobId: string
): Promise<AudioOpStatusResponse> {
  const response = await fetch(
    `${API_URL}/v1/libraries/${encodeURIComponent(librarySlug)}/beets/audio-op/${jobId}/status`
  )
  return handleResponse<AudioOpStatusResponse>(response)
}

/**
 * Poll a WAV convert / dedup job until it completes or fails.
 *
 * @returns the per-file result counts on success
 * @throws BeetsImportApiError on failure or timeout
 */
export async function pollAudioOpStatus(
  librarySlug: string,
  jobId: string
): Promise<AudioOpResult> {
  for (let attempt = 0; attempt < AUDIO_OP_MAX_POLL_ATTEMPTS; attempt++) {
    const status = await getAudioOpStatus(librarySlug, jobId)

    if (status.status === 'completed') {
      return status.result ?? {}
    }
    if (status.status === 'failed') {
      throw new BeetsImportApiError(
        status.error || 'Operation failed',
        500,
        'AUDIO_OP_ERROR'
      )
    }
    await new Promise((resolve) => setTimeout(resolve, AUDIO_OP_POLL_INTERVAL_MS))
  }
  throw new BeetsImportApiError(
    'Operation timed out',
    408,
    'AUDIO_OP_TIMEOUT'
  )
}

/**
 * Enqueue a WAV/WMA → FLAC/MP3 conversion. Returns as soon as the job is
 * accepted (status 'queued'); the caller polls {@link getAudioOpStatus} to track
 * it through queued → running → completed.
 */
export async function startConvertAudio(
  librarySlug: string,
  albumPath: string,
  sourceFormat: ConvertSource,
  targetFormat: ConvertTarget,
  deleteOriginals: boolean
): Promise<AudioOpJobResponse> {
  const response = await fetch(
    `${API_URL}/v1/libraries/${encodeURIComponent(librarySlug)}/beets/convert-audio`,
    {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({
        album_path: albumPath,
        source_format: sourceFormat,
        target_format: targetFormat,
        delete_originals: deleteOriginals,
      }),
    }
  )
  return handleResponse<AudioOpJobResponse>(response)
}

/**
 * Enqueue a duplicate-WAV cleanup. Returns once accepted; poll for the outcome.
 */
export async function startDedupeWav(
  librarySlug: string,
  albumPath: string
): Promise<AudioOpJobResponse> {
  const response = await fetch(
    `${API_URL}/v1/libraries/${encodeURIComponent(librarySlug)}/beets/dedupe-wav`,
    {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ album_path: albumPath }),
    }
  )
  return handleResponse<AudioOpJobResponse>(response)
}

/**
 * Convert an album folder's WAV/WMA files to FLAC or MP3 (V0). Starts an async
 * job and resolves once it completes. Used by the standalone (non-shared) flow;
 * the combined import view drives jobs through the audio-op registry instead.
 *
 * @param sourceFormat - which source files to convert ('wav' | 'wma')
 * @param targetFormat - encode target ('flac' | 'mp3')
 * @param deleteOriginals - remove each source after its target is written + verified
 */
export async function convertAudio(
  librarySlug: string,
  albumPath: string,
  sourceFormat: ConvertSource,
  targetFormat: ConvertTarget,
  deleteOriginals: boolean
): Promise<AudioOpResult> {
  const job = await startConvertAudio(
    librarySlug,
    albumPath,
    sourceFormat,
    targetFormat,
    deleteOriginals
  )
  return pollAudioOpStatus(librarySlug, job.jobId)
}

/**
 * Remove duplicate WAVs (those with a same-basename FLAC sibling) from an album
 * folder. Starts an async job and resolves once it completes.
 */
export async function removeDuplicateWavs(
  librarySlug: string,
  albumPath: string
): Promise<AudioOpResult> {
  const job = await startDedupeWav(librarySlug, albumPath)
  return pollAudioOpStatus(librarySlug, job.jobId)
}

/**
 * Add a manual candidate by resolving an external service link.
 *
 * Accepts a link from a supported provider (Deezer, Spotify, Discogs, MusicBrainz)
 * and uses the corresponding beets plugin to fetch album metadata. The resolved
 * candidate is stored in the server-side cache for the specified album.
 *
 * @param librarySlug - The library slug identifier
 * @param request - The manual candidate request with album path and link
 * @returns Promise resolving to the resolved candidate and provider
 * @throws BeetsImportApiError for API errors (INVALID_LINK, RELEASE_NOT_FOUND, etc.)
 */
export async function addManualCandidate(
  librarySlug: string,
  request: ManualCandidateRequest
): Promise<ManualCandidateResponse> {
  console.log('[addManualCandidate] Adding manual candidate:', { librarySlug, request })

  const response = await fetch(
    `${API_URL}/v1/libraries/${encodeURIComponent(librarySlug)}/beets/manual-candidate`,
    {
      method: 'POST',
      headers: {
        'Content-Type': 'application/json',
      },
      body: JSON.stringify(request),
    }
  )

  console.log('[addManualCandidate] Response status:', response.status)
  return handleResponse<ManualCandidateResponse>(response)
}

/**
 * Search every active metadata provider for a free-text term at once.
 *
 * Queries MusicBrainz, Spotify, Deezer, and Discogs concurrently (gated by the
 * plugins enabled for the library). Each hit carries a canonical provider URL
 * the user can open in a new tab or feed to {@link addManualCandidate} to
 * resolve as a candidate.
 *
 * @param librarySlug - The library slug identifier
 * @param query - Free-text search term (album, artist, or both)
 * @param page - 1-indexed page number (default 1)
 * @param perPage - Results per provider per page (default 5)
 * @param providers - Subset of providers to search; the response then contains
 *   only those groups (used for per-provider pagination). Omit to search all.
 * @param structured - Optional artist/album terms. When provided, each provider
 *   is queried with its field-search syntax instead of the free-text `query`,
 *   sharply narrowing results (issue #69). `query` stays as the fallback.
 * @param expectedTracks - Track count of the local folder being imported. When
 *   provided, hits whose track count matches rank first within their provider
 *   group (issue #112).
 * @returns Promise resolving to per-provider grouped search results
 * @throws BeetsImportApiError for API errors
 */
export async function searchCandidates(
  librarySlug: string,
  query: string,
  page = 1,
  perPage = 5,
  providers?: ManualCandidateProvider[],
  structured?: { artist?: string | null; album?: string | null },
  expectedTracks?: number | null
): Promise<SearchCandidatesResponse> {
  const params = new URLSearchParams({
    q: query,
    page: String(page),
    perPage: String(perPage),
  })
  if (providers && providers.length > 0) {
    params.set('providers', providers.join(','))
  }
  if (structured?.artist) {
    params.set('artist', structured.artist)
  }
  if (structured?.album) {
    params.set('album', structured.album)
  }
  if (expectedTracks != null) {
    params.set('expectedTracks', String(expectedTracks))
  }

  const response = await fetch(
    `${API_URL}/v1/libraries/${encodeURIComponent(librarySlug)}/beets/search-candidates?${params}`,
    {
      headers: {
        Accept: 'application/json',
      },
    }
  )

  return handleResponse<SearchCandidatesResponse>(response)
}

// ============================================================================
// Analysis Queue API Functions
// ============================================================================

/**
 * Get the current analysis queue status for a library.
 *
 * @param librarySlug - The library slug identifier
 * @returns Promise resolving to queue status with depth, items, and active count
 * @throws BeetsImportApiError for API errors
 */
export async function getAnalyzeQueue(
  librarySlug: string
): Promise<AnalyzeQueueResponse> {
  console.log('[getAnalyzeQueue] Fetching queue status for:', librarySlug)

  const response = await fetch(
    `${API_URL}/v1/libraries/${encodeURIComponent(librarySlug)}/beets/analyze-queue`,
    {
      headers: {
        Accept: 'application/json',
      },
    }
  )

  console.log('[getAnalyzeQueue] Response status:', response.status)
  return handleResponse<AnalyzeQueueResponse>(response)
}

/**
 * Bulk enqueue analysis for all albums in the import folder.
 *
 * @param librarySlug - The library slug identifier
 * @param force - If true, re-analyze albums even if cached results exist
 * @returns Promise resolving to summary statistics
 * @throws BeetsImportApiError for API errors
 */
export async function analyzeFolder(
  librarySlug: string,
  force = false
): Promise<AnalyzeFolderResponse> {
  console.log('[analyzeFolder] Starting bulk analysis for:', { librarySlug, force })

  const response = await fetch(
    `${API_URL}/v1/libraries/${encodeURIComponent(librarySlug)}/beets/analyze-folder`,
    {
      method: 'POST',
      headers: {
        'Content-Type': 'application/json',
      },
      body: JSON.stringify({ force }),
    }
  )

  console.log('[analyzeFolder] Response status:', response.status)
  return handleResponse<AnalyzeFolderResponse>(response)
}

/**
 * Get the auto-analyze-after-scan setting for a library.
 *
 * @param librarySlug - The library slug identifier
 * @returns Promise resolving to the auto-analyze setting
 * @throws BeetsImportApiError for API errors
 */
export async function getAutoAnalyzeSetting(
  librarySlug: string
): Promise<AutoAnalyzeSettingResponse> {
  console.log('[getAutoAnalyzeSetting] Fetching setting for:', librarySlug)

  const response = await fetch(
    `${API_URL}/v1/libraries/${encodeURIComponent(librarySlug)}/settings/auto-analyze`,
    {
      headers: {
        Accept: 'application/json',
      },
    }
  )

  console.log('[getAutoAnalyzeSetting] Response status:', response.status)
  return handleResponse<AutoAnalyzeSettingResponse>(response)
}

/**
 * Set the auto-analyze-after-scan setting for a library.
 *
 * @param librarySlug - The library slug identifier
 * @param enabled - Whether to enable auto-analyze after scan
 * @returns Promise resolving to the updated setting
 * @throws BeetsImportApiError for API errors
 */
export async function setAutoAnalyzeSetting(
  librarySlug: string,
  enabled: boolean
): Promise<AutoAnalyzeSettingResponse> {
  console.log('[setAutoAnalyzeSetting] Setting auto-analyze:', { librarySlug, enabled })

  const response = await fetch(
    `${API_URL}/v1/libraries/${encodeURIComponent(librarySlug)}/settings/auto-analyze`,
    {
      method: 'PUT',
      headers: {
        'Content-Type': 'application/json',
      },
      body: JSON.stringify({ autoAnalyzeAfterScan: enabled }),
    }
  )

  console.log('[setAutoAnalyzeSetting] Response status:', response.status)
  return handleResponse<AutoAnalyzeSettingResponse>(response)
}

// ============================================================================
// Import Job API Functions
// ============================================================================

const IMPORT_POLL_INTERVAL_MS = 2000 // Poll every 2 seconds

/**
 * Start an import job for an album with a selected candidate.
 *
 * @param librarySlug - The library slug identifier
 * @param request - Import job request with album path and candidate metadata
 * @returns Promise resolving to job creation response
 * @throws BeetsImportApiError for API errors (including 409 for duplicate imports)
 */
export async function startImport(
  librarySlug: string,
  request: ImportJobRequest
): Promise<ImportJobResponse> {
  console.log('[startImport] Starting import job:', { librarySlug, request })

  const response = await fetch(
    `${API_URL}/v1/libraries/${encodeURIComponent(librarySlug)}/beets/import`,
    {
      method: 'POST',
      headers: {
        'Content-Type': 'application/json',
      },
      body: JSON.stringify(request),
    }
  )

  console.log('[startImport] Response status:', response.status)
  return handleResponse<ImportJobResponse>(response)
}

/**
 * Get the status of a single import job.
 *
 * @param librarySlug - The library slug identifier
 * @param jobId - The import job ID to check
 * @returns Promise resolving to job status
 * @throws BeetsImportApiError for API errors
 */
export async function getImportJobStatus(
  librarySlug: string,
  jobId: string
): Promise<ImportJobStatusResponse> {
  console.log('[getImportJobStatus] Fetching job status:', { librarySlug, jobId })

  const response = await fetch(
    `${API_URL}/v1/libraries/${encodeURIComponent(librarySlug)}/beets/import/${jobId}/status`,
    {
      headers: {
        Accept: 'application/json',
      },
    }
  )

  console.log('[getImportJobStatus] Response status:', response.status)
  return handleResponse<ImportJobStatusResponse>(response)
}

/**
 * Poll for import job status until it reaches a terminal state.
 *
 * @param librarySlug - The library slug identifier
 * @param jobId - The import job ID to poll
 * @param onUpdate - Optional callback for status updates during polling
 * @returns Promise resolving to final job status
 * @throws BeetsImportApiError for API errors
 */
export async function pollImportStatus(
  librarySlug: string,
  jobId: string,
  onUpdate?: (status: ImportJobStatusResponse) => void
): Promise<ImportJobStatusResponse> {
  console.log('[pollImportStatus] Starting polling for job:', jobId)

  // eslint-disable-next-line no-constant-condition
  while (true) {
    const status = await getImportJobStatus(librarySlug, jobId)

    // Notify caller of update
    if (onUpdate) {
      onUpdate(status)
    }

    // Check for terminal state
    if (status.status === 'completed' || status.status === 'failed') {
      console.log('[pollImportStatus] Job reached terminal state:', status.status)
      return status
    }

    // Wait before next poll
    console.log('[pollImportStatus] Job still processing, waiting...')
    await new Promise((resolve) => setTimeout(resolve, IMPORT_POLL_INTERVAL_MS))
  }
}

/**
 * Get bulk import status for all albums in the library's import folder.
 * Used to hydrate the three-box layout on page load.
 *
 * @param librarySlug - The library slug identifier
 * @returns Promise resolving to bulk import status
 * @throws BeetsImportApiError for API errors
 */
export async function getBulkImportStatus(
  librarySlug: string
): Promise<BulkImportStatusResponse> {
  console.log('[getBulkImportStatus] Fetching bulk import status:', librarySlug)

  const response = await fetch(
    `${API_URL}/v1/libraries/${encodeURIComponent(librarySlug)}/beets/import-status`,
    {
      headers: {
        Accept: 'application/json',
      },
    }
  )

  console.log('[getBulkImportStatus] Response status:', response.status)
  return handleResponse<BulkImportStatusResponse>(response)
}
