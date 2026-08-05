// ============================================================================
// Library Folder Tree Types
// ============================================================================

/**
 * A folder in the library's on-disk layout.
 *
 * Derived server-side from the beets SQLite DB's `items.path` column, so this
 * tree reflects exactly how beets wrote your music to disk (not the import
 * source tree — see `import-tree.ts` for that).
 */
export interface LibraryFolderNode {
  /** Folder basename (e.g. "Abbey Road"). */
  name: string
  /** Path relative to the library root. Empty string at the root. */
  path: string
  /**
   * True if this folder contains at least one track directly (not only
   * subfolders). A compilation folder with tracks directly and a Disc 2
   * subfolder has `isAlbum: true` AND non-empty children.
   */
  isAlbum: boolean
  /**
   * Union of distinct beets album ids in this folder and every descendant
   * folder. Selecting this node for batch edit loads exactly these albums.
   */
  albumIds: number[]
  /** Nested folders, alphabetically sorted by name. */
  children: LibraryFolderNode[]
}

/** Response from GET /api/v1/libraries/{slug}/library-tree. */
export interface LibraryTreeResponse {
  /** Absolute container path of the library root. */
  libraryPath: string | null
  /** Root folder of the library. */
  root: LibraryFolderNode
}
