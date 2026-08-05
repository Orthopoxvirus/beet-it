import { useCallback, useMemo, useState } from 'react'
import {
  AlertTriangle,
  ChevronDown,
  ChevronRight,
  Disc3,
  Folder,
  FolderOpen,
  FolderX,
  Import,
  Loader2,
  Music,
  Trash2,
} from 'lucide-react'

import { ScrollArea } from '@/components/ui/scroll-area'
import {
  AlertDialog,
  AlertDialogAction,
  AlertDialogCancel,
  AlertDialogContent,
  AlertDialogDescription,
  AlertDialogFooter,
  AlertDialogHeader,
  AlertDialogTitle,
} from '@/components/ui/alert-dialog'
import { toast } from '@/components/ui/toast'
import { useLibraryTree } from '@/hooks/useLibraryTree'
import { useDeleteAlbum } from '@/hooks/useAlbums'
import type { DeleteAlbumMode } from '@/api/albums'
import type { LibraryFolderNode } from '@/types/library-tree'

/**
 * LibraryFolderTree — a folder-tree picker for the batch-edit page.
 *
 * Shape is intentionally parallel to `ImportFolderTree`: same expand/collapse
 * chevron pattern, same Folder/Music icon styling. The semantic differences:
 *
 *   - Each node here carries `albumIds` — the union of beets album_ids at or
 *     below it. Selecting a node hands that union back to the caller, which
 *     then loads items for every listed album and renders them as one
 *     sectioned table.
 *   - A node is displayed as an "album" (green Music icon) when `isAlbum` is
 *     true; a folder that contains more than one subfolder but no direct
 *     tracks is the blue Folder icon.
 *   - The component autoloads the tree via `useLibraryTree(slug)`.
 */

interface LibraryFolderTreeProps {
  librarySlug: string
  className?: string
  /** Called with the clicked node when user selects a folder (or `null` to clear). */
  onSelect?: (node: LibraryFolderNode | null) => void
  /** Path of the currently-selected folder (matched against `node.path`). */
  selectedPath?: string | null
  /**
   * Album ids in the caller's current selection. Used so deleting an album
   * that belongs to the active (possibly ancestor-folder) selection clears
   * it — otherwise the caller's stale snapshot would show a wrong count.
   */
  selectedAlbumIds?: number[]
}

interface NodeProps {
  node: LibraryFolderNode
  depth: number
  expanded: Set<string>
  onToggle: (path: string) => void
  onSelect?: (node: LibraryFolderNode) => void
  onRequestDelete?: (node: LibraryFolderNode) => void
  selectedPath?: string | null
}

function TreeNode({
  node,
  depth,
  expanded,
  onToggle,
  onSelect,
  onRequestDelete,
  selectedPath,
}: NodeProps) {
  const isExpanded = expanded.has(node.path)
  const hasChildren = node.children.length > 0
  const isSelected = selectedPath === node.path
  // Delete only makes sense for a node that maps to exactly one album. Folders
  // (and the rare node whose subtree spans several album ids) are ambiguous.
  const canDelete = node.isAlbum && node.albumIds.length === 1

  const icon = node.isAlbum ? (
    hasChildren ? (
      // Mixed folder — has tracks directly AND subfolders. Surface the
      // multi-disc style so it's visually distinct from a plain album.
      <Disc3 className="h-4 w-4 text-purple-500 shrink-0" />
    ) : (
      <Music className="h-4 w-4 text-green-500 shrink-0" />
    )
  ) : isExpanded ? (
    <FolderOpen className="h-4 w-4 text-blue-500 shrink-0" />
  ) : (
    <Folder className="h-4 w-4 text-blue-500 shrink-0" />
  )

  const handleSelect = (e: React.MouseEvent) => {
    e.stopPropagation()
    onSelect?.(node)
  }

  return (
    <div>
      <div
        className={`flex items-center gap-1 py-1.5 px-2 rounded-sm ${
          isSelected
            ? 'bg-primary/15 ring-1 ring-primary/30'
            : node.isAlbum
              ? hasChildren
                ? 'bg-purple-500/5 hover:bg-purple-500/10'
                : 'bg-green-500/5 hover:bg-green-500/10'
              : 'hover:bg-accent'
        }`}
        style={{ paddingLeft: `${depth * 16 + 8}px` }}
      >
        {hasChildren ? (
          <button
            type="button"
            className="p-0.5 hover:bg-muted rounded cursor-pointer"
            onClick={() => onToggle(node.path)}
            aria-label={isExpanded ? 'Collapse folder' : 'Expand folder'}
          >
            {isExpanded ? (
              <ChevronDown className="h-3 w-3" />
            ) : (
              <ChevronRight className="h-3 w-3" />
            )}
          </button>
        ) : (
          <span className="w-4 h-4" />
        )}

        <button
          type="button"
          className="cursor-pointer"
          onClick={handleSelect}
          aria-label={`Select folder ${node.name || 'root'}`}
        >
          {icon}
        </button>

        <button
          type="button"
          className={`text-sm truncate cursor-pointer text-left flex-1 ${
            node.isAlbum
              ? hasChildren
                ? 'font-medium text-purple-700 dark:text-purple-400'
                : 'font-medium text-green-700 dark:text-green-400'
              : ''
          }`}
          title={node.path || '/'}
          onClick={handleSelect}
        >
          {node.name || '(root)'}
        </button>

        {/* Album-count chip. A terminal album shows "1 album" — still useful
            for branch folders that span many albums. */}
        {node.albumIds.length > 0 && (
          <span className="ml-1 px-1.5 py-0.5 text-xs rounded bg-muted text-muted-foreground shrink-0">
            {node.albumIds.length} {node.albumIds.length === 1 ? 'album' : 'albums'}
          </span>
        )}

        {/* Delete button — floats right on single-album nodes only. */}
        {canDelete && onRequestDelete && (
          <button
            type="button"
            className="ml-1 p-1 rounded text-muted-foreground hover:text-destructive hover:bg-destructive/10 shrink-0 cursor-pointer"
            onClick={(e) => {
              e.stopPropagation()
              onRequestDelete(node)
            }}
            aria-label={`Delete album ${node.name || 'album'}`}
            title="Delete album"
          >
            <Trash2 className="h-3.5 w-3.5" />
          </button>
        )}
      </div>

      {isExpanded && hasChildren && (
        <div>
          {node.children.map((child) => (
            <TreeNode
              key={child.path}
              node={child}
              depth={depth + 1}
              expanded={expanded}
              onToggle={onToggle}
              onSelect={onSelect}
              onRequestDelete={onRequestDelete}
              selectedPath={selectedPath}
            />
          ))}
        </div>
      )}
    </div>
  )
}

export default function LibraryFolderTree({
  librarySlug,
  className,
  onSelect,
  selectedPath,
  selectedAlbumIds,
}: LibraryFolderTreeProps) {
  const { data, isLoading, error } = useLibraryTree(librarySlug)

  // By default expand the root — users usually want to see their artist
  // folders at a glance. Subfolders collapsed.
  const [expanded, setExpanded] = useState<Set<string>>(() => new Set(['']))

  // Album-delete confirmation. `deleteTarget` is the node awaiting a choice;
  // `pendingMode` is the action in flight (so we can spin the right button).
  const [deleteTarget, setDeleteTarget] = useState<LibraryFolderNode | null>(null)
  const [pendingMode, setPendingMode] = useState<DeleteAlbumMode | null>(null)
  const deleteMutation = useDeleteAlbum()

  const handleConfirmDelete = useCallback(
    async (mode: DeleteAlbumMode) => {
      if (!deleteTarget) return
      setPendingMode(mode)
      try {
        await deleteMutation.mutateAsync({
          slug: librarySlug,
          albumId: deleteTarget.albumIds[0],
          mode,
        })
        toast.success({
          title: 'Album removed',
          description:
            mode === 'delete_files'
              ? `Deleted “${deleteTarget.name}” from disk.`
              : `Moved “${deleteTarget.name}” back to the import folder.`,
        })
        // Clear the active batch-edit selection if the deleted album was part
        // of it — either the selected node itself, or an ancestor folder whose
        // album set still lists it. Otherwise the caller's stale snapshot
        // would leave a wrong track count / stuck progress bar.
        const deletedId = deleteTarget.albumIds[0]
        if (
          deleteTarget.path === selectedPath ||
          selectedAlbumIds?.includes(deletedId)
        ) {
          onSelect?.(null)
        }
        setDeleteTarget(null)
      } catch (err) {
        toast.error({
          title: 'Delete failed',
          description: err instanceof Error ? err.message : 'Unknown error',
        })
      } finally {
        setPendingMode(null)
      }
    },
    [deleteTarget, deleteMutation, librarySlug, selectedPath, selectedAlbumIds, onSelect]
  )

  const isDeleting = pendingMode !== null

  const handleToggle = useCallback((path: string) => {
    setExpanded((prev) => {
      const next = new Set(prev)
      if (next.has(path)) {
        next.delete(path)
      } else {
        next.add(path)
      }
      return next
    })
  }, [])

  // Render the tree starting from the root node's children when the root is
  // a pure container (typical), or from the root itself when it's a terminal
  // album (flat single-album library).
  const rootChildren = useMemo(() => {
    if (!data) return []
    // If the root has no children AND it's an album, render the root itself
    // so the user still has something selectable.
    if (data.root.children.length === 0) return [data.root]
    return data.root.children
  }, [data])

  if (isLoading) {
    return (
      <div className={`border rounded-md ${className || ''}`}>
        <div className="flex items-center justify-center py-12">
          <Loader2 className="h-6 w-6 animate-spin text-muted-foreground" />
          <span className="ml-2 text-sm text-muted-foreground">Loading library tree…</span>
        </div>
      </div>
    )
  }

  if (error) {
    return (
      <div className={`border rounded-md ${className || ''}`}>
        <div className="flex flex-col items-center justify-center py-12 text-center px-4">
          <FolderX className="h-10 w-10 text-destructive/70" />
          <p className="mt-3 text-sm text-destructive">Failed to load library tree</p>
          <p className="mt-1 text-xs text-muted-foreground">
            {error instanceof Error ? error.message : 'Unknown error'}
          </p>
        </div>
      </div>
    )
  }

  if (!data || data.root.albumIds.length === 0) {
    return (
      <div className={`border rounded-md ${className || ''}`}>
        <div className="flex flex-col items-center justify-center py-12 text-center px-4">
          <Folder className="h-10 w-10 text-muted-foreground/50" />
          <p className="mt-3 text-sm text-muted-foreground">No albums in this library yet</p>
          <p className="mt-1 text-xs text-muted-foreground">
            Run an import first to populate it.
          </p>
        </div>
      </div>
    )
  }

  return (
    <div className={`border rounded-md flex flex-col ${className || ''}`}>
      {/* Root header — shows the absolute library path + a "Select all"
          action that selects the root node for a whole-library batch. */}
      <div className="p-3 border-b bg-muted/30">
        <div className="flex items-center justify-between gap-2">
          <div className="min-w-0">
            <p className="text-xs text-muted-foreground">Library</p>
            <p className="text-sm font-mono truncate" title={data.libraryPath || ''}>
              {data.libraryPath}
            </p>
          </div>
          <button
            type="button"
            className={`shrink-0 text-xs px-2 py-1 rounded cursor-pointer ${
              selectedPath === ''
                ? 'bg-primary text-primary-foreground'
                : 'bg-muted hover:bg-muted/70'
            }`}
            onClick={() => onSelect?.(data.root)}
          >
            All {data.root.albumIds.length}
          </button>
        </div>
      </div>

      {/* flex-1 + min-h-0 lets ScrollArea fill the remaining height of the
          flex column instead of locking at 400px (which drifted out of sync
          with the 520px parent and left the last row half-clipped against
          the legend bar below). pb-2 inside the scroll content gives the
          last row breathing room when scrolled to the end. */}
      <ScrollArea className="flex-1 min-h-0">
        <div className="p-1 pb-2">
          {rootChildren.map((node) => (
            <TreeNode
              key={node.path}
              node={node}
              depth={0}
              expanded={expanded}
              onToggle={handleToggle}
              onSelect={onSelect}
              onRequestDelete={setDeleteTarget}
              selectedPath={selectedPath}
            />
          ))}
        </div>
      </ScrollArea>

      <div className="p-3 border-t bg-muted/30">
        <div className="flex flex-wrap gap-4 text-xs text-muted-foreground">
          <div className="flex items-center gap-1">
            <Folder className="h-3 w-3 text-blue-500" />
            <span>Folder</span>
          </div>
          <div className="flex items-center gap-1">
            <Music className="h-3 w-3 text-green-500" />
            <span>Album</span>
          </div>
          <div className="flex items-center gap-1">
            <Disc3 className="h-3 w-3 text-purple-500" />
            <span>Mixed</span>
          </div>
        </div>
      </div>

      <AlertDialog
        open={deleteTarget !== null}
        onOpenChange={(open) => {
          // Don't allow closing while a delete request is in flight.
          if (!isDeleting && !open) setDeleteTarget(null)
        }}
      >
        <AlertDialogContent>
          <AlertDialogHeader>
            <AlertDialogTitle className="flex items-center gap-2">
              <AlertTriangle className="h-5 w-5 text-destructive" />
              Delete album
            </AlertDialogTitle>
            <AlertDialogDescription>
              Remove{' '}
              <span className="font-medium text-foreground">
                {deleteTarget?.name}
              </span>{' '}
              from this library. Choose what happens to the files on disk:
              <span className="mt-2 block">
                <span className="font-medium text-foreground">Delete files</span>{' '}
                erases the album folder permanently — this cannot be undone.
              </span>
              <span className="mt-1 block">
                <span className="font-medium text-foreground">
                  Move to import
                </span>{' '}
                keeps the files, moving the folder back to the import area so
                you can re-import it.
              </span>
            </AlertDialogDescription>
          </AlertDialogHeader>
          <AlertDialogFooter className="gap-2 sm:gap-2">
            <AlertDialogCancel disabled={isDeleting}>Cancel</AlertDialogCancel>
            <AlertDialogAction
              onClick={(e) => {
                // Keep the dialog open; we close it ourselves after success.
                e.preventDefault()
                handleConfirmDelete('move_to_import')
              }}
              disabled={isDeleting}
              className="bg-secondary text-secondary-foreground hover:bg-secondary/80"
            >
              {pendingMode === 'move_to_import' ? (
                <>
                  <Loader2 className="h-4 w-4 animate-spin" />
                  Moving…
                </>
              ) : (
                <>
                  <Import className="h-4 w-4" />
                  Move to import
                </>
              )}
            </AlertDialogAction>
            <AlertDialogAction
              onClick={(e) => {
                e.preventDefault()
                handleConfirmDelete('delete_files')
              }}
              disabled={isDeleting}
              className="bg-destructive text-destructive-foreground hover:bg-destructive/90"
            >
              {pendingMode === 'delete_files' ? (
                <>
                  <Loader2 className="h-4 w-4 animate-spin" />
                  Deleting…
                </>
              ) : (
                <>
                  <Trash2 className="h-4 w-4" />
                  Delete files
                </>
              )}
            </AlertDialogAction>
          </AlertDialogFooter>
        </AlertDialogContent>
      </AlertDialog>
    </div>
  )
}
