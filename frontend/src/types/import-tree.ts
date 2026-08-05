// ============================================================================
// Import Folder Tree Types
// ============================================================================

/**
 * Represents a single folder node in the import folder tree.
 */
export interface ImportFolderNode {
  /** Folder name (e.g., "Folge_26") */
  name: string
  /** Relative path from import root (e.g., "TKKG/Folge_26") */
  path: string
  /** True if this is a leaf/album folder */
  isAlbum: boolean
  /** True if parent of multi-disc album set */
  isMultiDiscParent: boolean
  /** Child folder nodes */
  children: ImportFolderNode[]
  /** Hint for lazy loading optimization */
  hasSubfolders: boolean
}

/**
 * Response from the import tree API endpoint.
 */
export interface ImportTreeResponse {
  /** The library's import path (absolute) */
  importPath: string | null
  /** Top-level folder nodes */
  children: ImportFolderNode[]
}
