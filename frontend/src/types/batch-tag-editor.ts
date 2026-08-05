// ============================================================================
// Batch Tag Editor Types
// ============================================================================

/**
 * Supported transformation modes for tag updates
 */
export type TransformationMode = 'fixed' | 'regex' | 'sequence' | 'explicit'

/**
 * Canonical tag names supported for transformation
 */
export type TagName =
  | 'album'
  | 'album_artist'
  | 'artist'
  | 'title'
  | 'genre'
  | 'track_number'
  | 'disc_number'

/**
 * Valid source fields for regex transformations
 */
export type SourceField =
  | 'filename'
  | 'path'
  | 'album'
  | 'album_artist'
  | 'artist'
  | 'title'
  | 'genre'
  | 'track_number'
  | 'disc_number'

// ============================================================================
// Transformation Rule Types
// ============================================================================

/**
 * Fixed mode rule - replace tag with a constant value
 */
export interface FixedRule {
  tag: TagName
  mode: 'fixed'
  value: string
}

/**
 * Regex mode rule - apply pattern matching with capture group substitution
 */
export interface RegexRule {
  tag: TagName
  mode: 'regex'
  source_field: SourceField
  pattern: string
  replacement: string
}

/**
 * Sequence mode rule - auto-number tracks sequentially
 */
export interface SequenceRule {
  tag: 'track_number'
  mode: 'sequence'
  start: number
  per_directory: boolean
}

/**
 * Explicit mode rule - assign per-item values directly.
 *
 * Carries an item-id → value map computed client-side (the drag reorder
 * feature). Items absent from the map are left unchanged. Lets a manual
 * reorder commit the exact track numbers / titles it previewed.
 */
export interface ExplicitRule {
  tag: TagName
  mode: 'explicit'
  values: Record<number, string>
}

/**
 * Union type for all transformation rules
 */
export type TransformationRule = FixedRule | RegexRule | SequenceRule | ExplicitRule

// ============================================================================
// Preview Types
// ============================================================================

/**
 * Warning for a tag that couldn't be transformed
 */
export interface PreviewWarning {
  tag: TagName
  code: string
  message: string
}

/**
 * Preview result for a single import item
 */
export interface ItemPreview {
  itemId: number
  changes: Partial<Record<TagName, string>>
  warnings?: PreviewWarning[]
}

/**
 * Error for an item that couldn't be previewed
 */
export interface PreviewError {
  itemId: number
  code: string
  message: string
}

/**
 * Response from the preview endpoint
 */
export interface BatchPreviewResponse {
  previews: ItemPreview[]
  errors: PreviewError[]
}

// ============================================================================
// Batch Update Types
// ============================================================================

/**
 * Error details for a failed item update
 */
export interface ItemError {
  code: string
  message: string
  file_path?: string
}

/**
 * Result for a single item in the batch update
 */
export interface ItemResult {
  itemId: number
  status: 'success' | 'failed'
  changesApplied?: Partial<Record<TagName, string>>
  error?: ItemError
}

/**
 * Response from the batch update endpoint (non-SSE)
 */
export interface BatchUpdateResponse {
  status: 'completed'
  itemsTotal: number
  itemsSucceeded: number
  itemsFailed: number
  startedAt: string
  completedAt: string
  durationSeconds: number
  results: ItemResult[]
}

// ============================================================================
// SSE Event Types
// ============================================================================

/**
 * Data for batch_started SSE event
 */
export interface SSEBatchStartedData {
  totalItems: number
  startedAt: string
}

/**
 * Data for item_progress SSE event
 */
export interface SSEItemProgressData {
  itemId: number
  status: 'success' | 'failed'
  itemsProcessed: number
  itemsTotal: number
  progressPercent: number
  error?: ItemError
}

/**
 * Data for batch_completed SSE event
 */
export interface SSEBatchCompletedData {
  itemsTotal: number
  itemsSucceeded: number
  itemsFailed: number
  completedAt: string
  durationSeconds: number
}

/**
 * Data for batch_failed SSE event
 */
export interface SSEBatchFailedData {
  errorCode: string
  message: string
  failedAt: string
}

// ============================================================================
// Form State Types
// ============================================================================

/**
 * Configuration for a single tag field in the form
 */
export interface TagFieldState {
  enabled: boolean
  mode: TransformationMode | null
  // Fixed mode
  fixedValue?: string
  // Regex mode
  sourceField?: SourceField
  pattern?: string
  replacement?: string
  // Sequence mode (track_number only)
  sequenceStart?: number
  perDirectory?: boolean
}

/**
 * Form state for all tag fields
 */
export type BatchTagFormState = Record<TagName, TagFieldState>

// ============================================================================
// Hook State Types
// ============================================================================

/**
 * State for the batch tag update operation
 */
export interface BatchTagUpdateState {
  isUpdating: boolean
  progress: number
  itemsProcessed: number
  itemsTotal: number
  itemsSucceeded: number
  itemsFailed: number
  error: string | null
  isComplete: boolean
  results: ItemResult[]
}

// ============================================================================
// Constants
// ============================================================================

/**
 * All editable tag names
 */
export const EDITABLE_TAGS: TagName[] = [
  'album',
  'album_artist',
  'artist',
  'title',
  'genre',
  'track_number',
]

/**
 * Human-readable labels for tag names
 */
export const TAG_LABELS: Record<TagName, string> = {
  album: 'Album',
  album_artist: 'Album Artist',
  artist: 'Artist',
  title: 'Title',
  genre: 'Genre',
  track_number: 'Track Number',
  disc_number: 'Disc Number',
}

/**
 * Human-readable labels for source fields
 */
export const SOURCE_FIELD_LABELS: Record<SourceField, string> = {
  filename: 'Filename',
  path: 'Folder Path',
  album: 'Album',
  album_artist: 'Album Artist',
  artist: 'Artist',
  title: 'Title',
  genre: 'Genre',
  track_number: 'Track Number',
  disc_number: 'Disc Number',
}

/**
 * All available source fields for regex mode
 */
export const SOURCE_FIELDS: SourceField[] = [
  'filename',
  'path',
  'album',
  'album_artist',
  'artist',
  'title',
  'genre',
  'track_number',
  'disc_number',
]
