import type { LibraryTreeResponse } from '@/types/library-tree'

const API_URL = import.meta.env.VITE_API_URL || '/api'

/**
 * Fetch the nested folder tree for a library.
 *
 * The tree is derived server-side from the beets SQLite DB's item paths and
 * reflects the on-disk layout of the organised music — artist folders,
 * album folders, disc subfolders, etc.
 *
 * @see backend/app/api/routes/library_items.py for the endpoint
 * @see docs/architecture.md for the role of this tree in batch editing
 */
export async function getLibraryTree(slug: string): Promise<LibraryTreeResponse> {
  const url = `${API_URL}/v1/libraries/${encodeURIComponent(slug)}/library-tree`
  const response = await fetch(url)
  if (!response.ok) {
    const errorCode = response.headers.get('X-Error-Code')
    if (response.status === 404) {
      throw new Error(errorCode === 'LIBRARY_NOT_FOUND' ? 'Library not found' : 'Beets database not found')
    }
    const body = await response.json().catch(() => ({}))
    throw new Error(body.detail || `Failed to load library tree (${response.status})`)
  }
  return response.json()
}
