import { z } from 'zod'

const API_URL = import.meta.env.VITE_API_URL || '/api'

// ============================================================================
// Zod Schemas
// ============================================================================

// Slug validation regex: lowercase alphanumeric characters and hyphens only
export const SLUG_REGEX = /^[a-z0-9]+(?:-[a-z0-9]+)*$/

export const libraryCreateSchema = z.object({
  name: z
    .string()
    .min(1, 'Name is required')
    .max(255, 'Name must be 255 characters or less'),
  description: z.string().optional().nullable(),
  slug: z
    .string()
    .min(1, 'Slug is required')
    .regex(SLUG_REGEX, 'Slug must contain only lowercase letters, numbers, and hyphens')
    .optional(),
})

export const libraryUpdateSchema = z.object({
  name: z
    .string()
    .min(1, 'Name is required')
    .max(255, 'Name must be 255 characters or less')
    .optional(),
  description: z.string().optional().nullable(),
  slug: z
    .string()
    .min(1, 'Slug is required')
    .regex(SLUG_REGEX, 'Slug must contain only lowercase letters, numbers, and hyphens')
    .optional(),
})

export const deleteOptionsSchema = z.object({
  keep_config: z.boolean().default(true),
  keep_database: z.boolean().default(true),
  keep_folders: z.boolean().default(true),
})

// ============================================================================
// TypeScript Interfaces (inferred from Zod schemas + API response types)
// ============================================================================

export type LibraryCreate = z.infer<typeof libraryCreateSchema>
export type LibraryUpdate = z.infer<typeof libraryUpdateSchema>
export type DeleteOptions = z.infer<typeof deleteOptionsSchema>

export interface Library {
  id: number
  name: string
  slug: string
  description: string | null
  config_path: string
  database_path: string
  library_path: string
  import_path: string
  created_at: string
  updated_at: string | null
}

export interface LibraryListResponse {
  items: Library[]
  total: number
  skip: number
  limit: number
}

export interface DeleteResponse {
  status: 'deleted'
  id: number
  resources_deleted: {
    config: boolean
    database: boolean
    folders: boolean
  }
}

export interface ApiError {
  detail: string
  code?: string
}

// ============================================================================
// API Error Handling
// ============================================================================

export class LibraryApiError extends Error {
  code?: string
  status: number

  constructor(message: string, status: number, code?: string) {
    super(message)
    this.name = 'LibraryApiError'
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
    throw new LibraryApiError(errorData.detail, response.status, errorData.code)
  }
  return response.json()
}

// ============================================================================
// API Client Functions
// ============================================================================

export async function fetchLibraries(
  skip = 0,
  limit = 100
): Promise<LibraryListResponse> {
  const params = new URLSearchParams({
    skip: skip.toString(),
    limit: limit.toString(),
  })
  const response = await fetch(`${API_URL}/v1/libraries/?${params}`)
  return handleResponse<LibraryListResponse>(response)
}

export async function fetchLibrary(slug: string): Promise<Library> {
  const response = await fetch(`${API_URL}/v1/libraries/${slug}`)
  return handleResponse<Library>(response)
}

export async function createLibrary(data: LibraryCreate): Promise<Library> {
  const response = await fetch(`${API_URL}/v1/libraries/`, {
    method: 'POST',
    headers: {
      'Content-Type': 'application/json',
    },
    body: JSON.stringify(data),
  })
  return handleResponse<Library>(response)
}

export async function updateLibrary(
  slug: string,
  data: LibraryUpdate
): Promise<Library> {
  const response = await fetch(`${API_URL}/v1/libraries/${slug}`, {
    method: 'PUT',
    headers: {
      'Content-Type': 'application/json',
    },
    body: JSON.stringify(data),
  })
  return handleResponse<Library>(response)
}

export async function deleteLibrary(
  slug: string,
  options: DeleteOptions = { keep_config: true, keep_database: true, keep_folders: true }
): Promise<DeleteResponse> {
  const params = new URLSearchParams()
  if (options.keep_config !== undefined) {
    params.set('keep_config', options.keep_config.toString())
  }
  if (options.keep_database !== undefined) {
    params.set('keep_database', options.keep_database.toString())
  }
  if (options.keep_folders !== undefined) {
    params.set('keep_folders', options.keep_folders.toString())
  }

  const response = await fetch(`${API_URL}/v1/libraries/${slug}?${params}`, {
    method: 'DELETE',
  })
  return handleResponse<DeleteResponse>(response)
}
