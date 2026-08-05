// ============================================================================
// Activity Monitor Types
// ============================================================================

/**
 * Types of background tasks tracked by the activity monitor.
 */
export type TaskType =
  | 'scan'
  | 'analysis'
  | 'tag_write'
  | 'import'
  | 'move'
  | 'batch_edit_sync'
  | 'emby_refresh'
  | 'download'
  | 'convert_wav'
  | 'dedupe_wav'
  | 'cleanup'

/**
 * Possible states for a task event.
 */
export type TaskStatus = 'running' | 'completed' | 'failed'

// ============================================================================
// API Response Types
// ============================================================================

/**
 * An actively running task.
 */
export interface ActiveTask {
  eventId: number
  taskType: TaskType
  libraryId: number | null
  librarySlug: string
  description: string
  status: TaskStatus
  startedAt: string
  elapsedSeconds: number
  progressPercent: number | null
  metadata: Record<string, unknown>
}

/**
 * A task waiting in the queue.
 */
export interface QueuedTask {
  taskType: TaskType
  libraryId: number | null
  librarySlug: string
  description: string
  queuePosition: number
  queuedAt: string
}

/**
 * A recently completed task.
 */
export interface CompletedTask {
  eventId: number
  taskType: TaskType
  libraryId: number | null
  librarySlug: string
  description: string
  status: TaskStatus
  startedAt: string
  completedAt: string
  durationSeconds: number
  metadata: Record<string, unknown>
}

/**
 * Counts of tasks in each category.
 */
export interface ActivityCounts {
  active: number
  queued: number
  recent: number
}

/**
 * Response for GET /api/v1/activity snapshot endpoint.
 */
export interface ActivitySnapshot {
  activeTasks: ActiveTask[]
  queuedTasks: QueuedTask[]
  recentCompletions: CompletedTask[]
  counts: ActivityCounts
}

/**
 * A task event in the history list.
 */
export interface TaskEventHistoryItem {
  id: number
  taskType: TaskType
  libraryId: number | null
  librarySlug: string
  description: string
  status: TaskStatus
  startedAt: string
  completedAt: string | null
  durationSeconds: number | null
  metadata: Record<string, unknown>
}

/**
 * Response for GET /api/v1/activity/history endpoint.
 */
export interface ActivityHistoryResponse {
  items: TaskEventHistoryItem[]
  total: number
  skip: number
  limit: number
}

/**
 * Query parameters for the history endpoint.
 */
export interface ActivityHistoryParams {
  skip?: number
  limit?: number
  libraryId?: number | null
  taskType?: TaskType | null
  status?: TaskStatus | null
}

// ============================================================================
// SSE Event Types
// ============================================================================

export type SSEActivityEventType =
  | 'task_started'
  | 'task_progress'
  | 'task_completed'
  | 'task_failed'
  | 'heartbeat'

export interface SSETaskStartedData {
  eventId: number
  taskType: TaskType
  libraryId: number | null
  librarySlug: string
  description: string
  startedAt: string
  metadata: Record<string, unknown>
}

export interface SSETaskProgressData {
  eventId: number
  taskType: TaskType
  progressPercent: number | null
  elapsedSeconds: number
  metadata: Record<string, unknown>
}

export interface SSETaskCompletedData {
  eventId: number
  taskType: TaskType
  libraryId: number | null
  librarySlug: string
  description: string
  status: 'completed'
  startedAt: string
  completedAt: string
  durationSeconds: number
  metadata: Record<string, unknown>
}

export interface SSETaskFailedData {
  eventId: number
  taskType: TaskType
  libraryId: number | null
  librarySlug: string
  description: string
  status: 'failed'
  startedAt: string
  completedAt: string
  durationSeconds: number
  metadata: Record<string, unknown>
}

export interface SSEHeartbeatData {
  timestamp: string
}

export type SSEActivityEventData =
  | SSETaskStartedData
  | SSETaskProgressData
  | SSETaskCompletedData
  | SSETaskFailedData
  | SSEHeartbeatData

// ============================================================================
// Hook State Types
// ============================================================================

export interface ActivityState {
  isConnected: boolean
  snapshot: ActivitySnapshot | null
  error: string | null
}

// ============================================================================
// Utility Types
// ============================================================================

/**
 * Human-readable task type labels.
 */
export const TASK_TYPE_LABELS: Record<TaskType, string> = {
  scan: 'Scan',
  analysis: 'Analysis',
  tag_write: 'Tag Write',
  import: 'Import',
  move: 'Move',
  batch_edit_sync: 'Batch Sync',
  emby_refresh: 'Emby Refresh',
  download: 'Download',
  convert_wav: 'WAV→FLAC',
  dedupe_wav: 'WAV Cleanup',
  cleanup: 'Import Cleanup',
}

/**
 * Human-readable task status labels.
 */
export const TASK_STATUS_LABELS: Record<TaskStatus, string> = {
  running: 'Running',
  completed: 'Completed',
  failed: 'Failed',
}
