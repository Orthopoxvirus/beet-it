import type {
  TransformationRule,
  BatchPreviewResponse,
  BatchUpdateResponse,
  ItemPreview,
  ItemResult,
  PreviewWarning,
  PreviewError,
  ItemError,
} from '@/types/batch-tag-editor'

const API_URL = import.meta.env.VITE_API_URL || '/api'

// ============================================================================
// API Error Handling
// ============================================================================

export interface ApiError {
  detail: string
  code?: string
}

export class BatchTagApiError extends Error {
  code?: string
  status: number

  constructor(message: string, status: number, code?: string) {
    super(message)
    this.name = 'BatchTagApiError'
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
    throw new BatchTagApiError(errorData.detail, response.status, errorData.code)
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

interface RawItemError {
  code: string
  message: string
  file_path?: string
}

interface RawItemResult {
  item_id: number
  status: 'success' | 'failed'
  changes_applied?: Record<string, string>
  error?: RawItemError
}

interface RawBatchUpdateResponse {
  status: 'completed'
  items_total: number
  items_succeeded: number
  items_failed: number
  started_at: string
  completed_at: string
  duration_seconds: number
  results: RawItemResult[]
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

function transformItemError(raw: RawItemError): ItemError {
  return {
    code: raw.code,
    message: raw.message,
    file_path: raw.file_path,
  }
}

function transformItemResult(raw: RawItemResult): ItemResult {
  return {
    itemId: raw.item_id,
    status: raw.status,
    changesApplied: raw.changes_applied as ItemResult['changesApplied'],
    error: raw.error ? transformItemError(raw.error) : undefined,
  }
}

function transformBatchUpdateResponse(raw: RawBatchUpdateResponse): BatchUpdateResponse {
  return {
    status: raw.status,
    itemsTotal: raw.items_total,
    itemsSucceeded: raw.items_succeeded,
    itemsFailed: raw.items_failed,
    startedAt: raw.started_at,
    completedAt: raw.completed_at,
    durationSeconds: raw.duration_seconds,
    results: raw.results.map(transformItemResult),
  }
}

// ============================================================================
// Request Body Preparation
// ============================================================================

export interface BatchPreviewRequest {
  item_ids: number[]
  rules: TransformationRule[]
}

export interface BatchUpdateRequest {
  item_ids: number[]
  rules: TransformationRule[]
}

// ============================================================================
// API Client Functions
// ============================================================================

/**
 * Preview tag transformations without persisting changes
 */
export async function previewTagTransformations(
  slug: string,
  itemIds: number[],
  rules: TransformationRule[]
): Promise<BatchPreviewResponse> {
  const requestBody: BatchPreviewRequest = {
    item_ids: itemIds,
    rules: rules,
  }

  const response = await fetch(`${API_URL}/v1/libraries/${slug}/import-items/preview`, {
    method: 'POST',
    headers: {
      'Content-Type': 'application/json',
    },
    body: JSON.stringify(requestBody),
  })

  const raw = await handleResponse<RawBatchPreviewResponse>(response)
  return transformBatchPreviewResponse(raw)
}

/**
 * Apply tag transformations to items (non-SSE version)
 */
export async function batchUpdateTags(
  slug: string,
  itemIds: number[],
  rules: TransformationRule[]
): Promise<BatchUpdateResponse> {
  const requestBody: BatchUpdateRequest = {
    item_ids: itemIds,
    rules: rules,
  }

  const response = await fetch(`${API_URL}/v1/libraries/${slug}/import-items/batch-update`, {
    method: 'POST',
    headers: {
      'Content-Type': 'application/json',
    },
    body: JSON.stringify(requestBody),
  })

  const raw = await handleResponse<RawBatchUpdateResponse>(response)
  return transformBatchUpdateResponse(raw)
}

/**
 * Get the SSE endpoint URL for batch tag updates with progress
 */
export function getBatchUpdateSSEUrl(slug: string): string {
  return `${API_URL}/v1/libraries/${slug}/import-items/batch-update`
}

// ============================================================================
// SSE Data Transformers
// ============================================================================

interface RawSSEBatchStartedData {
  total_items: number
  started_at: string
}

interface RawSSEItemProgressData {
  item_id: number
  status: 'success' | 'failed'
  items_processed: number
  items_total: number
  progress_percent: number
  error?: RawItemError
}

interface RawSSEBatchCompletedData {
  items_total: number
  items_succeeded: number
  items_failed: number
  completed_at: string
  duration_seconds: number
}

interface RawSSEBatchFailedData {
  error_code: string
  message: string
  failed_at: string
}

export function transformSSEBatchStartedData(raw: RawSSEBatchStartedData) {
  return {
    totalItems: raw.total_items,
    startedAt: raw.started_at,
  }
}

export function transformSSEItemProgressData(raw: RawSSEItemProgressData) {
  return {
    itemId: raw.item_id,
    status: raw.status,
    itemsProcessed: raw.items_processed,
    itemsTotal: raw.items_total,
    progressPercent: raw.progress_percent,
    error: raw.error ? transformItemError(raw.error) : undefined,
  }
}

export function transformSSEBatchCompletedData(raw: RawSSEBatchCompletedData) {
  return {
    itemsTotal: raw.items_total,
    itemsSucceeded: raw.items_succeeded,
    itemsFailed: raw.items_failed,
    completedAt: raw.completed_at,
    durationSeconds: raw.duration_seconds,
  }
}

export function transformSSEBatchFailedData(raw: RawSSEBatchFailedData) {
  return {
    errorCode: raw.error_code,
    message: raw.message,
    failedAt: raw.failed_at,
  }
}
