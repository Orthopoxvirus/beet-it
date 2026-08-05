// ============================================================================
// Beets Import Types - Candidate Analysis
// ============================================================================

// Request types
export interface AnalyzeAlbumRequest {
  album_path: string
  force_reanalyze?: boolean
}

// Response types
export interface LocalTrackInfo {
  path: string
  title: string | null
  trackNum: number | null
  length: number | null
}

/** Where the Local Album artist/album came from. */
export type MetadataSource = 'tags' | 'folder' | 'mixed'

export interface LocalAlbumInfo {
  path: string
  artist: string | null
  album: string | null
  /**
   * Where artist/album came from: 'tags' (embedded tags), 'folder' (parsed from
   * the folder name because tags were empty) or 'mixed'. Folder-derived values
   * are low-confidence hints. Defaults to 'tags' when absent.
   */
  metadataSource?: MetadataSource
  /** Most common container format across tracks (e.g. "FLAC", "MP3"); null if unknown. */
  dominantFormat?: string | null
  /** Whether the album folder contains any .wav files. */
  hasWav?: boolean
  /** Whether the album folder contains any .flac files. */
  hasFlac?: boolean
  /** Count of .wav files that have a same-basename .flac sibling (real duplicates). */
  duplicateWavCount?: number
  /** Whether the album folder contains any .wma files. */
  hasWma?: boolean
  /** Smart-default convert target for the album's WMA files ('mp3' or 'flac'); null if no WMA. */
  wmaRecommendedTarget?: ConvertTarget | null
  tracks: LocalTrackInfo[]
}

/** Source containers we can convert from. */
export type ConvertSource = 'wav' | 'wma'

/** Encode targets the convert action offers. */
export type ConvertTarget = 'flac' | 'mp3'

/** Parameters for the audio-convert action triggered from the Local Album card. */
export interface ConvertAudioParams {
  sourceFormat: ConvertSource
  targetFormat: ConvertTarget
  deleteOriginals: boolean
}

// --- Audio convert (WAV/WMA → FLAC/MP3) / duplicate-WAV cleanup ---

export interface ConvertAudioRequest {
  album_path: string
  source_format: ConvertSource
  target_format: ConvertTarget
  delete_originals?: boolean
}

export interface DedupeWavRequest {
  album_path: string
}

export interface AudioOpJobResponse {
  jobId: string
  albumPath: string
  status: 'queued' | 'running'
  message: string
}

export interface AudioOpResult {
  /** convert: number of WAVs transcoded to FLAC */
  converted?: number
  /** convert: targets skipped because a FLAC already existed */
  skipped?: number
  /** convert: originals deleted (only when delete_originals was set) */
  deleted?: number
  /** dedup: duplicate WAVs removed */
  removed?: number
  /** files that failed the operation */
  failed?: number
  failures?: Array<{ file: string; error: string }>
}

export interface AudioOpStatusResponse {
  jobId: string
  status: 'queued' | 'running' | 'completed' | 'failed'
  startedAt?: string | null
  completedAt?: string | null
  result?: AudioOpResult | null
  error?: string | null
}

/** Active (non-terminal) audio-op states an album can be in. */
export type AudioOpActiveStatus = 'queued' | 'running'

export interface MetadataChange {
  field: string
  fromValue: string | null
  toValue: string | null
}

export interface TrackChange {
  index: number
  localTitle: string | null
  candidateTitle: string | null
  /** Local track duration in seconds */
  localLength?: number | null
  /** Candidate track duration in seconds */
  candidateLength?: number | null
  /** Absolute path of the local audio file */
  localPath?: string | null
}

export interface CandidateTrack {
  index: number
  /** Disc (medium) number this track belongs to (null/undefined = single-disc release). */
  disc?: number | null
  title: string
  length: number | null
  /** Title of the local file paired to this candidate track (null = no local counterpart / new track). */
  localTitle?: string | null
  /** Absolute path of the local file paired to this candidate track (null = no local counterpart). */
  localPath?: string | null
  changes: MetadataChange[]
}

export interface Candidate {
  source: string
  sourceId: string | null
  similarity: number
  artist: string
  album: string
  year: number | null
  label: string | null
  country: string | null
  media: string | null
  tracks: CandidateTrack[]
  changes: MetadataChange[]
  trackChanges: TrackChange[]
  isManual?: boolean // True if this candidate was manually added via external link
  coverUrl?: string | null // Remote cover URL from the source, persisted on import
}

export interface AnalyzeAlbumResponse {
  albumPath: string
  localAlbum: LocalAlbumInfo
  candidates: Candidate[]
  manualCandidates?: Candidate[] // Manually added candidates (max one per provider)
  analyzedAt: string // ISO 8601 datetime
}

// Async job types
export type AnalyzeJobStatus = 'analyzing' | 'queued' | 'completed'

export interface AnalyzeJobResponse {
  jobId: string
  albumPath: string
  status: AnalyzeJobStatus
  queuePosition?: number // Only when status === "queued"
  message: string
}

// Analysis Queue types
export interface QueuedItem {
  albumPath: string
  position: number
  queuedAt: string // ISO 8601 datetime
}

export interface ActiveItem {
  albumPath: string
  jobId: string
  startedAt: string // ISO 8601 datetime
}

export interface AnalyzeQueueResponse {
  queueDepth: number
  activeCount: number
  maxConcurrent: number
  queuedItems: QueuedItem[]
  activeItems: ActiveItem[]
}

export interface AnalyzeFolderRequest {
  force?: boolean
}

export interface AnalyzeFolderResponse {
  enqueued: number
  dispatched: number
  alreadyCached: number
  alreadyQueued: number
  total: number
  message: string
}

// Auto-analyze settings
export interface AutoAnalyzeSettingRequest {
  autoAnalyzeAfterScan: boolean
}

export interface AutoAnalyzeSettingResponse {
  autoAnalyzeAfterScan: boolean
  message?: string
}

export type JobStatus = 'analyzing' | 'completed' | 'failed'

export interface AnalyzeStatusResponse {
  jobId: string
  status: JobStatus
  startedAt?: string
  completedAt?: string
  result?: AnalyzeAlbumResponse
  error?: string | { code?: string; message?: string; traceback?: string }
}

export interface ErrorResponse {
  detail: string
  error_code?: string
}

// Error code constants
export const ErrorCodes = {
  // Existing codes
  INVALID_ALBUM_PATH: 'INVALID_ALBUM_PATH',
  PATH_OUTSIDE_IMPORT: 'PATH_OUTSIDE_IMPORT',
  NO_IMPORT_PATH: 'NO_IMPORT_PATH',
  LIBRARY_NOT_FOUND: 'LIBRARY_NOT_FOUND',
  ALBUM_NOT_FOUND: 'ALBUM_NOT_FOUND',
  NO_AUDIO_FILES: 'NO_AUDIO_FILES',
  ANALYSIS_TIMEOUT: 'ANALYSIS_TIMEOUT',
  BEETS_ERROR: 'BEETS_ERROR',
  MUSICBRAINZ_ERROR: 'MUSICBRAINZ_ERROR',
  // New codes for manual candidates
  INVALID_LINK: 'INVALID_LINK',
  RELEASE_NOT_FOUND: 'RELEASE_NOT_FOUND',
  PLUGIN_NOT_AVAILABLE: 'PLUGIN_NOT_AVAILABLE',
  PROVIDER_ERROR: 'PROVIDER_ERROR',
  RESOLUTION_TIMEOUT: 'RESOLUTION_TIMEOUT',
  // Queue-related codes
  ALREADY_QUEUED: 'ALREADY_QUEUED',
  ALREADY_ANALYZING: 'ALREADY_ANALYZING',
} as const

export type ErrorCode = (typeof ErrorCodes)[keyof typeof ErrorCodes]

// ============================================================================
// Cache Status Types
// ============================================================================

/**
 * Response from the bulk cache status check endpoint.
 */
export interface CacheStatusResponse {
  /** Map of album path to cache status (true if cached, false otherwise) */
  cacheStatus: Record<string, boolean>
  /** Number of paths that were checked */
  pathsChecked: number
  /** Number of paths that have cached results */
  pathsCached: number
}

// ============================================================================
// Album Stage Types for UI
// ============================================================================

/**
 * Import stages for an album:
 * - none: Not yet analyzed
 * - analyzed: Beets has found candidates
 * - chosen: User has selected a candidate (Phase 2)
 * - imported: Album has been imported (Phase 2)
 */
export type AlbumStage = 'none' | 'analyzed' | 'chosen' | 'imported'

/**
 * Album item displayed in the album list.
 * Combines data from import-items with analysis state.
 */
export interface AlbumListItem {
  /** Unique identifier (from import items or derived from path) */
  id: number | string
  /** Folder path relative to import root */
  path: string
  /** Folder name */
  name: string
  /**
   * Parent folder the album is saved in, relative to the import root.
   * Null/undefined for albums sitting directly in the import root.
   * Used to group albums by the folder they live in (issue #80).
   */
  folder?: string | null
  /** Detected artist from audio tags */
  artist: string | null
  /** Detected album from audio tags */
  album: string | null
  /** Current import stage */
  stage: AlbumStage
  /** Whether analysis is currently in progress */
  isAnalyzing: boolean
  /** True if this album spans multiple discs (a multi-disc parent folder). */
  isMultiDisc?: boolean
}

// ============================================================================
// Manual Candidate Types
// ============================================================================

/**
 * Supported metadata providers for manual candidates.
 */
export type ManualCandidateProvider = 'deezer' | 'spotify' | 'discogs' | 'musicbrainz'

/**
 * Request body for adding a manual candidate via external link.
 */
export interface ManualCandidateRequest {
  /** Path to the album folder for metadata comparison context */
  albumPath: string
  /** External service URL or MusicBrainz release ID */
  link: string
}

/**
 * Response from the manual candidate resolution endpoint.
 */
export interface ManualCandidateResponse {
  /** The resolved candidate with isManual=true */
  candidate: Candidate
  /** Provider name: 'deezer', 'spotify', 'discogs', or 'musicbrainz' */
  provider: ManualCandidateProvider
}

// ============================================================================
// Multi-Provider Search Types
// ============================================================================

/**
 * A single album hit from one provider's search.
 */
export interface SearchResultItem {
  provider: ManualCandidateProvider
  sourceId: string
  title: string
  artist: string
  year: number | null
  trackCount: number | null
  /** Canonical provider URL — opens in a new tab and resolves via addManualCandidate. */
  externalUrl: string
  coverUrl: string | null
}

/**
 * Per-provider search outcome: results, availability, and pagination state.
 */
export interface SearchProviderGroup {
  provider: ManualCandidateProvider
  /** True if the provider was searched; false means skipped (see `reason`). */
  available: boolean
  /** Why the provider is unavailable, or the error message when a search failed. */
  reason: string | null
  results: SearchResultItem[]
  /** True if more result pages exist for this provider. */
  hasMore: boolean
}

/**
 * Aggregated multi-provider search response for one query page.
 */
export interface SearchCandidatesResponse {
  query: string
  page: number
  perPage: number
  providers: SearchProviderGroup[]
}

// ============================================================================
// Link Validation Utilities
// ============================================================================

/**
 * Regex patterns for validating external service links.
 * Used for client-side validation before API submission.
 */
export const LINK_PATTERNS = {
  deezer: /^https?:\/\/(?:www\.)?deezer\.com\/(?:[a-z]{2}\/)?album\/(\d+)/i,
  spotify: /^https?:\/\/open\.spotify\.com\/(?:intl-[a-z]{2}\/)?album\/([a-zA-Z0-9]+)/i,
  discogs: /^https?:\/\/(?:www\.)?discogs\.com\/(?:[a-z]{2}\/)?(release|master)\/(\d+)/i,
  musicbrainzUrl: /^https?:\/\/(?:www\.)?musicbrainz\.org\/release\/([a-f0-9]{8}-[a-f0-9]{4}-[a-f0-9]{4}-[a-f0-9]{4}-[a-f0-9]{12})/i,
  musicbrainzUuid: /^[a-f0-9]{8}-[a-f0-9]{4}-[a-f0-9]{4}-[a-f0-9]{4}-[a-f0-9]{12}$/i,
} as const

/**
 * Validate a link and return the detected provider.
 * Returns null if the link does not match any supported pattern.
 */
export function detectProvider(link: string): ManualCandidateProvider | null {
  const trimmed = link.trim()

  if (LINK_PATTERNS.deezer.test(trimmed)) return 'deezer'
  if (LINK_PATTERNS.spotify.test(trimmed)) return 'spotify'
  if (LINK_PATTERNS.discogs.test(trimmed)) return 'discogs'
  if (LINK_PATTERNS.musicbrainzUrl.test(trimmed)) return 'musicbrainz'
  if (LINK_PATTERNS.musicbrainzUuid.test(trimmed)) return 'musicbrainz'

  return null
}

/**
 * Validate that a link matches a supported provider format.
 */
export function isValidLink(link: string): boolean {
  return detectProvider(link) !== null
}

// ============================================================================
// Import Job Types
// ============================================================================

/**
 * Status of an import job.
 */
export type ImportJobStatus = 'pending' | 'in_progress' | 'completed' | 'failed'

/**
 * Track metadata for an import candidate.
 */
export interface ImportCandidateTrack {
  index: number
  title: string
  length?: number
  /** Disc (medium) number this track belongs to (omit for single-disc releases). */
  disc?: number
  /** Absolute path of the local file paired to this track, so the backend applies
   *  each track's metadata to the correct file (multi-disc safe). */
  localPath?: string
}

/**
 * Candidate metadata to be applied during import.
 */
export interface ImportCandidate {
  source: string
  sourceId?: string
  artist: string
  album: string
  year?: number
  coverUrl?: string
  tracks: ImportCandidateTrack[]
}

/**
 * Request body for starting an import job.
 */
export interface ImportJobRequest {
  albumPath: string
  /** Selected candidate metadata. Omit when importAsIs is true. */
  candidate?: ImportCandidate
  /** Import with the files' existing tags untouched, no candidate required. */
  importAsIs?: boolean
  replaceExisting?: boolean
}

/**
 * Format / quality / size summary shared by both sides of the upgrade prompt.
 * Every field is best-effort; callers should tolerate 0 / null values.
 */
export interface AlbumQualityStats {
  trackCount: number
  totalBytes: number
  totalDurationSeconds: number
  dominantFormat: string | null
  avgBitrateKbps: number | null
}

/**
 * Existing album details returned on a 409 ALBUM_ALREADY_EXISTS error.
 * \`stats\` is best-effort — when file reads fail the backend returns null here
 * and the dialog should degrade to the name-only display.
 */
export interface ExistingAlbumInfo {
  albumId: number
  artist: string
  album: string
  matchReason: 'mb_albumid' | 'artist_album'
  stats: AlbumQualityStats | null
}

/**
 * Stats for the import the user is about to run, sent alongside
 * ExistingAlbumInfo so the dialog can render a side-by-side comparison.
 */
export interface IncomingAlbumInfo {
  stats: AlbumQualityStats | null
}

/**
 * Response from creating an import job.
 */
export interface ImportJobResponse {
  jobId: string
  status: 'pending'
  albumPath: string
  message: string
}

/**
 * Error details for a failed import job.
 */
export interface ImportJobError {
  code: string
  message: string
}

/**
 * Response from polling import job status.
 */
export interface ImportJobStatusResponse {
  jobId: string
  status: ImportJobStatus
  albumPath: string
  startedAt: string | null
  completedAt: string | null
  destinationPath?: string
  error?: ImportJobError
}

/**
 * Import state for a single album (from bulk status endpoint).
 */
export type ImportState = 'pending' | 'in_progress' | 'done'

/**
 * Album import state in bulk status response.
 */
export interface AlbumImportState {
  state: ImportState
  jobId?: string
  startedAt?: string
  completedAt?: string
  destinationPath?: string
}

/**
 * Summary counts for import status.
 */
export interface ImportStatusCounts {
  pending: number
  inProgress: number
  done: number
}

/**
 * Response from bulk import status endpoint.
 */
export interface BulkImportStatusResponse {
  albums: Record<string, AlbumImportState>
  counts: ImportStatusCounts
  importMode: 'copy' | 'move'
}

/**
 * Import error codes
 */
export const ImportErrorCodes = {
  // Request validation errors (400)
  INVALID_ALBUM_PATH: 'INVALID_ALBUM_PATH',
  PATH_OUTSIDE_IMPORT: 'PATH_OUTSIDE_IMPORT',
  ALBUM_NOT_FOUND: 'ALBUM_NOT_FOUND',
  NO_AUDIO_FILES: 'NO_AUDIO_FILES',
  INVALID_CANDIDATE: 'INVALID_CANDIDATE',
  TRACK_COUNT_MISMATCH: 'TRACK_COUNT_MISMATCH',

  // Resource not found errors (404)
  LIBRARY_NOT_FOUND: 'LIBRARY_NOT_FOUND',
  NO_IMPORT_PATH: 'NO_IMPORT_PATH',
  JOB_NOT_FOUND: 'JOB_NOT_FOUND',

  // Conflict errors (409)
  IMPORT_IN_PROGRESS: 'IMPORT_IN_PROGRESS',
  ALBUM_ALREADY_EXISTS: 'ALBUM_ALREADY_EXISTS',

  // Task execution errors
  TAG_WRITE_FAILED: 'TAG_WRITE_FAILED',
  FILE_COPY_FAILED: 'FILE_COPY_FAILED',
  FILE_MOVE_FAILED: 'FILE_MOVE_FAILED',
  DATABASE_ERROR: 'DATABASE_ERROR',
  BEETS_ERROR: 'BEETS_ERROR',
  PERMISSION_DENIED: 'PERMISSION_DENIED',
  DISK_FULL: 'DISK_FULL',
} as const

export type ImportErrorCode = (typeof ImportErrorCodes)[keyof typeof ImportErrorCodes]
