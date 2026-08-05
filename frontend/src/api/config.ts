import type {
  BeetsConfig,
  EmbyTestRequest,
  EmbyTestResponse,
  FilesystemBrowseResponse,
  FilesystemCreateRequest,
  FilesystemCreateResponse,
  PathStatusResponse,
  RawPathStatusResponse,
  InitializeResponse,
  RawInitializeResponse,
} from '@/types/beets-config'
import {
  transformPathStatusResponse,
  transformInitializeResponse,
} from '@/types/beets-config'

const API_URL = import.meta.env.VITE_API_URL || '/api'

// ============================================================================
// Error Handling
// ============================================================================

export interface ApiError {
  detail: string
  code?: string
  errors?: Array<{
    loc: (string | number)[]
    msg: string
    type: string
  }>
}

export class ConfigApiError extends Error {
  code?: string
  status: number

  constructor(message: string, status: number, code?: string) {
    super(message)
    this.name = 'ConfigApiError'
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
    throw new ConfigApiError(errorData.detail, response.status, errorData.code)
  }
  return response.json()
}

// ============================================================================
// Library Config API Functions
// ============================================================================

/**
 * Fetch the beets configuration for a library
 */
export async function fetchLibraryConfig(libraryId: number): Promise<BeetsConfig> {
  const response = await fetch(`${API_URL}/v1/libraries/${libraryId}/config`)
  return handleResponse<BeetsConfig>(response)
}

/**
 * Update the beets configuration for a library
 */
export async function updateLibraryConfig(
  libraryId: number,
  config: BeetsConfig
): Promise<BeetsConfig> {
  const response = await fetch(`${API_URL}/v1/libraries/${libraryId}/config`, {
    method: 'PUT',
    headers: {
      'Content-Type': 'application/json',
    },
    body: JSON.stringify(config),
  })
  return handleResponse<BeetsConfig>(response)
}

/**
 * Test Emby server connection
 */
export async function testEmbyConnection(
  libraryId: number,
  credentials: EmbyTestRequest
): Promise<EmbyTestResponse> {
  const response = await fetch(
    `${API_URL}/v1/libraries/${libraryId}/config/emby/test`,
    {
      method: 'POST',
      headers: {
        'Content-Type': 'application/json',
      },
      body: JSON.stringify(credentials),
    }
  )
  return handleResponse<EmbyTestResponse>(response)
}

// ============================================================================
// Filesystem Browse API Functions
// ============================================================================

/**
 * Browse filesystem directories
 */
export async function browseFilesystem(
  path?: string
): Promise<FilesystemBrowseResponse> {
  const params = new URLSearchParams()
  if (path) {
    params.set('path', path)
  }
  const queryString = params.toString()
  const url = queryString
    ? `${API_URL}/v1/filesystem/browse?${queryString}`
    : `${API_URL}/v1/filesystem/browse`
  const response = await fetch(url)
  return handleResponse<FilesystemBrowseResponse>(response)
}

/**
 * Create a new directory
 */
export async function createDirectory(
  data: FilesystemCreateRequest
): Promise<FilesystemCreateResponse> {
  const response = await fetch(`${API_URL}/v1/filesystem/browse`, {
    method: 'POST',
    headers: {
      'Content-Type': 'application/json',
    },
    body: JSON.stringify(data),
  })
  return handleResponse<FilesystemCreateResponse>(response)
}

// ============================================================================
// Library Path Status & Initialization API Functions
// ============================================================================

/**
 * Check the existence status of library directory and database paths.
 *
 * @param libraryId - The library ID
 * @returns Promise resolving to path existence status
 * @throws ConfigApiError on failure
 */
export async function fetchPathStatus(libraryId: number): Promise<PathStatusResponse> {
  const response = await fetch(`${API_URL}/v1/libraries/${libraryId}/config/path-status`)
  const raw = await handleResponse<RawPathStatusResponse>(response)
  return transformPathStatusResponse(raw)
}

/**
 * Initialize library resources (create directory and database).
 *
 * Creates the library directory if missing and runs beet config -p
 * to initialize the beets database. This operation is idempotent.
 *
 * @param libraryId - The library ID
 * @returns Promise resolving to initialization result
 * @throws ConfigApiError on failure
 */
export async function initializeLibrary(libraryId: number): Promise<InitializeResponse> {
  const response = await fetch(`${API_URL}/v1/libraries/${libraryId}/config/initialize`, {
    method: 'POST',
    headers: {
      'Content-Type': 'application/json',
    },
  })
  const raw = await handleResponse<RawInitializeResponse>(response)
  return transformInitializeResponse(raw)
}
