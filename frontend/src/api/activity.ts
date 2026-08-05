import type {
  ActivitySnapshot,
  ActivityHistoryResponse,
  ActivityHistoryParams,
  TaskType,
  TaskStatus,
  ActiveTask,
  QueuedTask,
  CompletedTask,
  TaskEventHistoryItem,
} from '@/types/activity'

const API_URL = import.meta.env.VITE_API_URL || '/api'

// ============================================================================
// API Error Handling
// ============================================================================

export interface ApiError {
  detail: string
  code?: string
}

export class ActivityApiError extends Error {
  code?: string
  status: number

  constructor(message: string, status: number, code?: string) {
    super(message)
    this.name = 'ActivityApiError'
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
    throw new ActivityApiError(errorData.detail, response.status, errorData.code)
  }
  return response.json()
}

// ============================================================================
// Response Transformers (snake_case to camelCase)
// ============================================================================

interface RawActiveTask {
  event_id: number
  task_type: string
  library_id: number | null
  library_slug: string
  description: string
  status: string
  started_at: string
  elapsed_seconds: number
  progress_percent: number | null
  metadata: Record<string, unknown>
}

interface RawQueuedTask {
  task_type: string
  library_id: number | null
  library_slug: string
  description: string
  queue_position: number
  queued_at: string
}

interface RawCompletedTask {
  event_id: number
  task_type: string
  library_id: number | null
  library_slug: string
  description: string
  status: string
  started_at: string
  completed_at: string
  duration_seconds: number
  metadata: Record<string, unknown>
}

interface RawActivityCounts {
  active: number
  queued: number
  recent: number
}

interface RawActivitySnapshot {
  active_tasks: RawActiveTask[]
  queued_tasks: RawQueuedTask[]
  recent_completions: RawCompletedTask[]
  counts: RawActivityCounts
}

interface RawTaskEventHistoryItem {
  id: number
  task_type: string
  library_id: number | null
  library_slug: string
  description: string
  status: string
  started_at: string
  completed_at: string | null
  duration_seconds: number | null
  metadata: Record<string, unknown>
}

interface RawActivityHistoryResponse {
  items: RawTaskEventHistoryItem[]
  total: number
  skip: number
  limit: number
}

function transformActiveTask(raw: RawActiveTask): ActiveTask {
  return {
    eventId: raw.event_id,
    taskType: raw.task_type as TaskType,
    libraryId: raw.library_id,
    librarySlug: raw.library_slug,
    description: raw.description,
    status: raw.status as TaskStatus,
    startedAt: raw.started_at,
    elapsedSeconds: raw.elapsed_seconds,
    progressPercent: raw.progress_percent,
    metadata: raw.metadata,
  }
}

function transformQueuedTask(raw: RawQueuedTask): QueuedTask {
  return {
    taskType: raw.task_type as TaskType,
    libraryId: raw.library_id,
    librarySlug: raw.library_slug,
    description: raw.description,
    queuePosition: raw.queue_position,
    queuedAt: raw.queued_at,
  }
}

function transformCompletedTask(raw: RawCompletedTask): CompletedTask {
  return {
    eventId: raw.event_id,
    taskType: raw.task_type as TaskType,
    libraryId: raw.library_id,
    librarySlug: raw.library_slug,
    description: raw.description,
    status: raw.status as TaskStatus,
    startedAt: raw.started_at,
    completedAt: raw.completed_at,
    durationSeconds: raw.duration_seconds,
    metadata: raw.metadata,
  }
}

function transformActivitySnapshot(raw: RawActivitySnapshot): ActivitySnapshot {
  return {
    activeTasks: raw.active_tasks.map(transformActiveTask),
    queuedTasks: raw.queued_tasks.map(transformQueuedTask),
    recentCompletions: raw.recent_completions.map(transformCompletedTask),
    counts: raw.counts,
  }
}

function transformTaskEventHistoryItem(raw: RawTaskEventHistoryItem): TaskEventHistoryItem {
  return {
    id: raw.id,
    taskType: raw.task_type as TaskType,
    libraryId: raw.library_id,
    librarySlug: raw.library_slug,
    description: raw.description,
    status: raw.status as TaskStatus,
    startedAt: raw.started_at,
    completedAt: raw.completed_at,
    durationSeconds: raw.duration_seconds,
    metadata: raw.metadata,
  }
}

function transformActivityHistoryResponse(raw: RawActivityHistoryResponse): ActivityHistoryResponse {
  return {
    items: raw.items.map(transformTaskEventHistoryItem),
    total: raw.total,
    skip: raw.skip,
    limit: raw.limit,
  }
}

// ============================================================================
// API Client Functions
// ============================================================================

/**
 * Fetch the current activity snapshot (active, queued, recent).
 */
export async function fetchActivity(): Promise<ActivitySnapshot> {
  const response = await fetch(`${API_URL}/v1/activity`)
  const raw = await handleResponse<RawActivitySnapshot>(response)
  return transformActivitySnapshot(raw)
}

/**
 * Fetch paginated activity history with optional filters.
 */
export async function fetchActivityHistory(
  params: ActivityHistoryParams = {}
): Promise<ActivityHistoryResponse> {
  const searchParams = new URLSearchParams()

  if (params.skip !== undefined) {
    searchParams.set('skip', params.skip.toString())
  }
  if (params.limit !== undefined) {
    searchParams.set('limit', params.limit.toString())
  }
  if (params.libraryId !== undefined && params.libraryId !== null) {
    searchParams.set('library_id', params.libraryId.toString())
  }
  if (params.taskType !== undefined && params.taskType !== null) {
    searchParams.set('task_type', params.taskType)
  }
  if (params.status !== undefined && params.status !== null) {
    searchParams.set('status', params.status)
  }

  const response = await fetch(`${API_URL}/v1/activity/history?${searchParams}`)
  const raw = await handleResponse<RawActivityHistoryResponse>(response)
  return transformActivityHistoryResponse(raw)
}

/**
 * Get the SSE endpoint URL for activity stream.
 */
export function getActivityStreamUrl(): string {
  return `${API_URL}/v1/activity/stream`
}

// ============================================================================
// SSE Data Transformers
// ============================================================================

interface RawSSETaskStartedData {
  event_id: number
  task_type: string
  library_id: number | null
  library_slug: string
  description: string
  started_at: string
  metadata: Record<string, unknown>
}

interface RawSSETaskProgressData {
  event_id: number
  task_type: string
  progress_percent: number | null
  elapsed_seconds: number
  metadata: Record<string, unknown>
}

interface RawSSETaskCompletedData {
  event_id: number
  task_type: string
  library_id: number | null
  library_slug: string
  description: string
  status: 'completed'
  started_at: string
  completed_at: string
  duration_seconds: number
  metadata: Record<string, unknown>
}

interface RawSSETaskFailedData {
  event_id: number
  task_type: string
  library_id: number | null
  library_slug: string
  description: string
  status: 'failed'
  started_at: string
  completed_at: string
  duration_seconds: number
  metadata: Record<string, unknown>
}

export function transformSSETaskStartedData(raw: RawSSETaskStartedData) {
  return {
    eventId: raw.event_id,
    taskType: raw.task_type as TaskType,
    libraryId: raw.library_id,
    librarySlug: raw.library_slug,
    description: raw.description,
    startedAt: raw.started_at,
    metadata: raw.metadata,
  }
}

export function transformSSETaskProgressData(raw: RawSSETaskProgressData) {
  return {
    eventId: raw.event_id,
    taskType: raw.task_type as TaskType,
    progressPercent: raw.progress_percent,
    elapsedSeconds: raw.elapsed_seconds,
    metadata: raw.metadata,
  }
}

export function transformSSETaskCompletedData(raw: RawSSETaskCompletedData) {
  return {
    eventId: raw.event_id,
    taskType: raw.task_type as TaskType,
    libraryId: raw.library_id,
    librarySlug: raw.library_slug,
    description: raw.description,
    status: raw.status,
    startedAt: raw.started_at,
    completedAt: raw.completed_at,
    durationSeconds: raw.duration_seconds,
    metadata: raw.metadata,
  }
}

export function transformSSETaskFailedData(raw: RawSSETaskFailedData) {
  return {
    eventId: raw.event_id,
    taskType: raw.task_type as TaskType,
    libraryId: raw.library_id,
    librarySlug: raw.library_slug,
    description: raw.description,
    status: raw.status,
    startedAt: raw.started_at,
    completedAt: raw.completed_at,
    durationSeconds: raw.duration_seconds,
    metadata: raw.metadata,
  }
}

// ============================================================================
// Clear History Types and API
// ============================================================================

/**
 * Parameters for clearing activity history.
 */
export interface ClearHistoryParams {
  /** Filter deletion to specific library ID */
  libraryId?: number | null
  /** Filter deletion to specific task type */
  taskType?: TaskType | null
}

/**
 * Response from DELETE /api/v1/activity/history endpoint.
 */
export interface ClearHistoryResponse {
  /** Number of task event records deleted */
  deletedCount: number
}

/**
 * Raw API response (snake_case) before transformation.
 */
interface RawClearHistoryResponse {
  deleted_count: number
}

/**
 * Transform snake_case API response to camelCase.
 */
function transformClearHistoryResponse(raw: RawClearHistoryResponse): ClearHistoryResponse {
  return {
    deletedCount: raw.deleted_count,
  }
}

/**
 * Clear activity history records.
 * Running tasks are excluded from deletion.
 *
 * @param params - Optional filters for targeted deletion
 * @returns Promise resolving to the count of deleted records
 * @throws ActivityApiError on failure
 */
export async function clearActivityHistory(
  params: ClearHistoryParams = {}
): Promise<ClearHistoryResponse> {
  const searchParams = new URLSearchParams()

  if (params.libraryId !== undefined && params.libraryId !== null) {
    searchParams.set('library_id', params.libraryId.toString())
  }
  if (params.taskType !== undefined && params.taskType !== null) {
    searchParams.set('task_type', params.taskType)
  }

  const queryString = searchParams.toString()
  const url = queryString
    ? `${API_URL}/v1/activity/history?${queryString}`
    : `${API_URL}/v1/activity/history`

  const response = await fetch(url, { method: 'DELETE' })
  const raw = await handleResponse<RawClearHistoryResponse>(response)
  return transformClearHistoryResponse(raw)
}
