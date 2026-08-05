// ============================================================================
// Scan Status Enums
// ============================================================================

export type ScanStatusType =
  | 'queued'
  | 'scanning'
  | 'extracting_metadata'
  | 'completed'
  | 'failed'

export type ImportItemType = 'file' | 'folder'

export type ImportItemStatus = 'new' | 'modified' | 'unchanged' | 'deleted'

export type OperationType = 'import' | 'tag_modify' | 'move' | 'delete'

// ============================================================================
// Core Interfaces
// ============================================================================

/**
 * Information about an active or past scan operation
 */
export interface ScanInfo {
  id: number
  status: ScanStatusType
  startedAt: string
  completedAt: string | null
  itemsTotal: number
  itemsProcessed: number
  progressPercent: number | null
  currentFile: string | null
  errorMessage: string | null
}

/**
 * Real-time scan progress data
 */
export interface ScanProgress {
  libraryId: number
  librarySlug: string
  scanId: number
  status: ScanStatusType
  itemsProcessed: number
  itemsTotal: number
  percentage: number
  currentFile: string | null
  startedAt: string | null
  elapsedSeconds: number | null
}

/**
 * Current scan status for a library
 */
export interface ScanStatus {
  librarySlug: string
  currentScan: ScanInfo | null
  queuedScans: number
  blockingOperations: OperationType[]
  watcherActive: boolean
  lastCompletedScan: ScanInfo | null
}

/**
 * Response from manual scan trigger
 */
export interface ScanTriggerResponse {
  status: 'started' | 'queued' | 'blocked'
  scanId: number | null
  message: string
  queuePosition: number | null
  blockingOperations: OperationType[]
}

/**
 * A scan in the history list
 */
export interface ScanHistoryItem {
  id: number
  status: ScanStatusType
  startedAt: string
  completedAt: string | null
  itemsTotal: number
  itemsProcessed: number
  errorMessage: string | null
}

/**
 * Paginated scan history response
 */
export interface ScanHistoryResponse {
  items: ScanHistoryItem[]
  total: number
  skip: number
  limit: number
}

/**
 * A discovered file or folder from an import scan
 */
export interface ImportItem {
  id: number
  itemType: ImportItemType
  path: string
  directory: string
  filename: string
  album: string | null
  albumArtist: string | null
  artist: string | null
  title: string | null
  trackNumber: number | null
  trackTotal: number | null
  genre: string | null
  format: string | null
  bitrate: number | null
  status: ImportItemStatus
  firstSeenAt: string
  lastSeenAt: string
}

/**
 * Paginated import items list response
 */
export interface ImportItemListResponse {
  items: ImportItem[]
  total: number
  skip: number
  limit: number
  scanId: number | null
  scanCompletedAt: string | null
}

// ============================================================================
// SSE Event Types
// ============================================================================

export type SSEEventType =
  | 'scan_started'
  | 'scan_progress'
  | 'scan_completed'
  | 'scan_failed'
  | 'scan_queued'
  | 'scan_blocked'
  | 'heartbeat'

export interface SSEScanStartedData {
  scanId: number
  librarySlug: string
  startedAt: string
}

export interface SSEScanProgressData {
  scanId: number
  status: ScanStatusType
  itemsTotal: number
  itemsProcessed: number
  progressPercent: number
  currentFile: string | null
  elapsedSeconds: number
}

export interface SSEScanCompletedData {
  scanId: number
  status: 'completed'
  itemsTotal: number
  itemsProcessed: number
  newItems: number
  modifiedItems: number
  deletedItems: number
  completedAt: string
  durationSeconds: number
}

export interface SSEScanFailedData {
  scanId: number
  status: 'failed'
  errorMessage: string
  failedAt: string
}

export interface SSEScanQueuedData {
  librarySlug: string
  queuePosition: number
  blockedBy: string[]
}

export interface SSEScanBlockedData {
  librarySlug: string
  blockingOperations: string[]
}

export interface SSEHeartbeatData {
  timestamp: string
}

export type SSEEventData =
  | SSEScanStartedData
  | SSEScanProgressData
  | SSEScanCompletedData
  | SSEScanFailedData
  | SSEScanQueuedData
  | SSEScanBlockedData
  | SSEHeartbeatData

// ============================================================================
// Hook State Types
// ============================================================================

export interface ScanProgressState {
  isConnected: boolean
  isScanning: boolean
  isQueued: boolean
  isBlocked: boolean
  progress: ScanProgress | null
  error: string | null
  queuePosition: number | null
  blockingOperations: string[]
}
