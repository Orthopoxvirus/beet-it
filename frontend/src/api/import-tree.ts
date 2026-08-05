import type { ImportTreeResponse } from '@/types/import-tree'

const API_URL = import.meta.env.VITE_API_URL || '/api'

// ============================================================================
// API Error Handling
// ============================================================================

export interface ApiError {
  detail: string
}

export class ImportTreeApiError extends Error {
  status: number

  constructor(message: string, status: number) {
    super(message)
    this.name = 'ImportTreeApiError'
    this.status = status
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
    throw new ImportTreeApiError(errorData.detail, response.status)
  }
  return response.json()
}

// ============================================================================
// API Client Functions
// ============================================================================

/**
 * Fetches the import folder tree for a specific library.
 * @param slug - The library's URL-safe slug
 * @returns The hierarchical folder tree for the library's import folder
 */
export async function fetchImportTree(slug: string): Promise<ImportTreeResponse> {
  const response = await fetch(`${API_URL}/v1/libraries/${slug}/import-tree`)
  return handleResponse<ImportTreeResponse>(response)
}

export interface DeleteImportFolderResult {
  status: string
  path: string
  itemsRemoved: number
}

interface RawDeleteImportFolderResponse {
  status: string
  path: string
  items_removed: number
}

/**
 * Deletes a folder from the library's import area. Removes the folder
 * recursively from disk and purges the matching import items from the
 * database. The caller is responsible for invalidating the import-tree query.
 *
 * @param slug - The library's URL-safe slug
 * @param path - Folder path relative to the import root (as given by the tree node)
 */
export async function deleteImportFolder(
  slug: string,
  path: string
): Promise<DeleteImportFolderResult> {
  const params = new URLSearchParams({ path })
  const response = await fetch(
    `${API_URL}/libraries/${slug}/import-folder?${params}`,
    { method: 'DELETE' }
  )
  const raw = await handleResponse<RawDeleteImportFolderResponse>(response)
  return {
    status: raw.status,
    path: raw.path,
    itemsRemoved: raw.items_removed,
  }
}
