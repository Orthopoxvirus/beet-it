import { useState, useCallback } from 'react'
import {
  ChevronRight,
  ChevronDown,
  Folder,
  FolderOpen,
  Disc3,
  Music,
  Loader2,
  FolderX,
  Trash2,
  AlertTriangle,
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
import { useImportTree, useDeleteImportFolder } from '@/hooks/useImportTree'
import { ImportTreeApiError } from '@/api/import-tree'
import type { ImportFolderNode } from '@/types/import-tree'

// ============================================================================
// Helpers
// ============================================================================

/** Count all descendant folders below a node (excludes the node itself). */
function countDescendantFolders(node: ImportFolderNode): number {
  return node.children.reduce(
    (sum, child) => sum + 1 + countDescendantFolders(child),
    0
  )
}

// ============================================================================
// Types
// ============================================================================

interface ImportFolderTreeProps {
  /** Library slug to fetch import tree for */
  librarySlug: string
  /** Optional CSS class name */
  className?: string
  /** Callback when a folder is selected */
  onFolderSelect?: (path: string) => void
  /** Currently selected folder path */
  selectedPath?: string | null
  /** Callback after a folder is successfully deleted (passed its relative path) */
  onFolderDeleted?: (path: string) => void
}

interface FolderNodeProps {
  node: ImportFolderNode
  depth: number
  expandedPaths: Set<string>
  onToggle: (path: string) => void
  /** Callback when a folder is selected */
  onSelect?: (path: string) => void
  /** Currently selected folder path */
  selectedPath?: string | null
  /** Delete a folder by its relative path; resolves when done, rejects on error */
  onDelete: (path: string) => Promise<void>
}

// ============================================================================
// Helper Components
// ============================================================================

function FolderNode({ node, depth, expandedPaths, onToggle, onSelect, selectedPath, onDelete }: FolderNodeProps) {
  const isExpanded = expandedPaths.has(node.path)
  const hasChildren = node.children.length > 0
  const isSelected = selectedPath === node.path

  // Delete confirmation state (per node)
  const [confirmOpen, setConfirmOpen] = useState(false)
  const [isDeleting, setIsDeleting] = useState(false)
  const [deleteError, setDeleteError] = useState<string | null>(null)

  const subfolderCount = countDescendantFolders(node)

  const handleConfirmDelete = async () => {
    setIsDeleting(true)
    setDeleteError(null)
    try {
      await onDelete(node.path)
      setConfirmOpen(false)
    } catch (err) {
      setDeleteError(
        err instanceof ImportTreeApiError
          ? err.message
          : 'Failed to delete folder. Please try again.'
      )
    } finally {
      setIsDeleting(false)
    }
  }

  // Determine icon based on folder type
  const renderIcon = () => {
    if (node.isMultiDiscParent) {
      // Multi-disc parent folder
      return <Disc3 className="h-4 w-4 text-purple-500 shrink-0" />
    }
    if (node.isAlbum) {
      // Regular album folder
      return <Music className="h-4 w-4 text-green-500 shrink-0" />
    }
    // Regular folder
    return isExpanded ? (
      <FolderOpen className="h-4 w-4 text-blue-500 shrink-0" />
    ) : (
      <Folder className="h-4 w-4 text-blue-500 shrink-0" />
    )
  }

  // Handle click on folder name/icon (not the chevron)
  const handleFolderClick = (e: React.MouseEvent) => {
    e.stopPropagation()
    if (onSelect) {
      onSelect(node.path)
    }
  }

  return (
    <div>
      <div
        className={`flex items-center gap-1 py-1.5 px-2 rounded-sm ${
          isSelected
            ? 'bg-primary/15 ring-1 ring-primary/30'
            : node.isAlbum
              ? 'bg-green-500/5 hover:bg-green-500/10'
              : node.isMultiDiscParent
                ? 'bg-purple-500/5 hover:bg-purple-500/10'
                : 'hover:bg-accent'
        }`}
        style={{ paddingLeft: `${depth * 16 + 8}px` }}
      >
        {/* Chevron for expand/collapse - only shown if folder has children */}
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
          // Spacer for alignment when no chevron
          <span className="w-4 h-4" />
        )}

        {/* Folder/Album icon - clickable to select */}
        <button
          type="button"
          className="cursor-pointer"
          onClick={handleFolderClick}
          aria-label={`Select folder ${node.name}`}
        >
          {renderIcon()}
        </button>

        {/* Folder name - clickable to select */}
        <button
          type="button"
          className={`text-sm truncate cursor-pointer text-left ${
            node.isAlbum ? 'font-medium text-green-700 dark:text-green-400' : ''
          } ${node.isMultiDiscParent ? 'font-medium text-purple-700 dark:text-purple-400' : ''}`}
          title={node.path}
          onClick={handleFolderClick}
        >
          {node.name}
        </button>

        {/* Multi-disc badge */}
        {node.isMultiDiscParent && (
          <span className="ml-1 px-1.5 py-0.5 text-xs rounded bg-purple-500/20 text-purple-700 dark:text-purple-300">
            Multi-disc
          </span>
        )}

        {/* Delete button - right-aligned, deletes this folder after confirmation */}
        <button
          type="button"
          className="ml-auto p-1 rounded text-muted-foreground hover:text-destructive hover:bg-destructive/10 shrink-0"
          onClick={(e) => {
            e.stopPropagation()
            setDeleteError(null)
            setConfirmOpen(true)
          }}
          aria-label={`Delete folder ${node.name}`}
        >
          <Trash2 className="h-3.5 w-3.5" />
        </button>
      </div>

      {/* Delete confirmation dialog */}
      <AlertDialog
        open={confirmOpen}
        onOpenChange={(open) => {
          // Don't allow closing while the delete request is in flight.
          if (!isDeleting) setConfirmOpen(open)
        }}
      >
        <AlertDialogContent>
          <AlertDialogHeader>
            <AlertDialogTitle className="flex items-center gap-2">
              <AlertTriangle className="h-5 w-5 text-destructive" />
              Delete folder
            </AlertDialogTitle>
            <AlertDialogDescription>
              This permanently deletes <span className="font-medium text-foreground">{node.name}</span>
              {subfolderCount > 0
                ? ` and its ${subfolderCount} subfolder${subfolderCount === 1 ? '' : 's'} and all their tracks`
                : ' and all its tracks'}{' '}
              from disk and from beet-it. This cannot be undone.
            </AlertDialogDescription>
          </AlertDialogHeader>
          {deleteError && (
            <p className="text-sm text-destructive">{deleteError}</p>
          )}
          <AlertDialogFooter>
            <AlertDialogCancel disabled={isDeleting}>Cancel</AlertDialogCancel>
            <AlertDialogAction
              onClick={(e) => {
                // Keep the dialog open; we close it ourselves after success.
                e.preventDefault()
                handleConfirmDelete()
              }}
              disabled={isDeleting}
              className="bg-destructive text-destructive-foreground hover:bg-destructive/90"
            >
              {isDeleting ? (
                <>
                  <Loader2 className="h-4 w-4 animate-spin" />
                  Deleting...
                </>
              ) : (
                'Delete'
              )}
            </AlertDialogAction>
          </AlertDialogFooter>
        </AlertDialogContent>
      </AlertDialog>

      {/* Render children recursively when expanded */}
      {isExpanded && hasChildren && (
        <div>
          {node.children.map((child) => (
            <FolderNode
              key={child.path}
              node={child}
              depth={depth + 1}
              expandedPaths={expandedPaths}
              onToggle={onToggle}
              onSelect={onSelect}
              selectedPath={selectedPath}
              onDelete={onDelete}
            />
          ))}
        </div>
      )}
    </div>
  )
}

// ============================================================================
// Main Component
// ============================================================================

export default function ImportFolderTree({
  librarySlug,
  className,
  onFolderSelect,
  selectedPath,
  onFolderDeleted,
}: ImportFolderTreeProps) {
  const [expandedPaths, setExpandedPaths] = useState<Set<string>>(new Set())

  const { data, isLoading, error } = useImportTree(librarySlug)
  const deleteFolder = useDeleteImportFolder(librarySlug)

  const handleDelete = useCallback(
    async (path: string) => {
      await deleteFolder.mutateAsync(path)
      onFolderDeleted?.(path)
    },
    [deleteFolder, onFolderDeleted]
  )

  const handleToggle = useCallback((path: string) => {
    setExpandedPaths((prev) => {
      const next = new Set(prev)
      if (next.has(path)) {
        next.delete(path)
      } else {
        next.add(path)
      }
      return next
    })
  }, [])

  // Loading state
  if (isLoading) {
    return (
      <div className={`border rounded-md ${className || ''}`}>
        <div className="flex items-center justify-center py-12">
          <Loader2 className="h-6 w-6 animate-spin text-muted-foreground" />
          <span className="ml-2 text-sm text-muted-foreground">
            Loading folder tree...
          </span>
        </div>
      </div>
    )
  }

  // Error state
  if (error) {
    return (
      <div className={`border rounded-md ${className || ''}`}>
        <div className="flex flex-col items-center justify-center py-12 text-center px-4">
          <FolderX className="h-10 w-10 text-destructive/70" />
          <p className="mt-3 text-sm text-destructive">
            Failed to load import folder
          </p>
          <p className="mt-1 text-xs text-muted-foreground">
            {error instanceof Error ? error.message : 'Unknown error'}
          </p>
        </div>
      </div>
    )
  }

  // Empty state - no import path configured or no folders
  if (!data?.children.length) {
    return (
      <div className={`border rounded-md ${className || ''}`}>
        <div className="flex flex-col items-center justify-center py-12 text-center px-4">
          <Folder className="h-10 w-10 text-muted-foreground/50" />
          <p className="mt-3 text-sm text-muted-foreground">
            {data?.importPath
              ? 'No folders found in import directory'
              : 'No import path configured for this library'}
          </p>
        </div>
      </div>
    )
  }

  return (
    <div className={`border rounded-md ${className || ''}`}>
      {/* Header showing import path */}
      <div className="p-3 border-b bg-muted/30">
        <p className="text-xs text-muted-foreground">Import folder</p>
        <p className="text-sm font-mono truncate" title={data.importPath || ''}>
          {data.importPath}
        </p>
      </div>

      {/* Tree View */}
      <ScrollArea className="h-[400px]">
        <div className="p-1">
          {data.children.map((node) => (
            <FolderNode
              key={node.path}
              node={node}
              depth={0}
              expandedPaths={expandedPaths}
              onToggle={handleToggle}
              onSelect={onFolderSelect}
              selectedPath={selectedPath}
              onDelete={handleDelete}
            />
          ))}
        </div>
      </ScrollArea>

      {/* Legend */}
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
            <span>Multi-disc</span>
          </div>
        </div>
      </div>
    </div>
  )
}
