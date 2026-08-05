import { useState } from 'react'
import {
  Music,
  Folder,
  Trash2,
  AlertTriangle,
  Loader2,
  FileDown,
  Play,
  ListOrdered,
  ChevronDown,
  ChevronRight,
  Disc,
  Disc3,
} from 'lucide-react'
import { Card, CardContent, CardHeader, CardTitle } from '@/components/ui/card'
import { Badge } from '@/components/ui/badge'
import { Button } from '@/components/ui/button'
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
import { cn } from '@/lib/utils'
import StageIndicator from './StageIndicator'
import type { AlbumListItem, AudioOpActiveStatus } from '@/types/beets-import'

// ============================================================================
// Types
// ============================================================================

interface AlbumListCardProps {
  /** List of albums to display */
  albums: AlbumListItem[]
  /** Currently selected album path */
  selectedPath: string | null
  /** Callback when an album is selected */
  onAlbumSelect: (path: string) => void
  /** Callback to trigger analysis for an album */
  onAnalyzeClick: (path: string) => void
  /** Delete an album folder by path; resolves when done, rejects on error */
  onDeleteAlbum?: (path: string) => Promise<void>
  /** Import an album as-is (no candidate, keep existing tags) */
  onImportAsIs?: (path: string) => void
  /** Whether an import request is currently in flight (disables as-is buttons) */
  isImporting?: boolean
  /** Whether the album list is loading */
  isLoading?: boolean
  /** Error message if loading failed */
  error?: string | null
  /** Optional additional CSS class */
  className?: string
  /** Map of album path to queue position (1-indexed) if queued */
  queueStatus?: Record<string, number>
  /** Map of album path to active audio-op status ('queued'/'running') if converting */
  convertStatus?: Record<string, AudioOpActiveStatus>
  /** Trigger bulk analysis of every album (the header "Analyze All" action) */
  onAnalyzeAll?: () => void
  /** Whether the bulk-analysis request is in flight */
  isAnalyzingAll?: boolean
  /** Number of albums currently queued for analysis (header indicator) */
  queueDepth?: number
  /** Number of albums currently being analyzed (header indicator) */
  activeCount?: number
  /** Analyze every album inside a folder group */
  onAnalyzeFolder?: (folder: string) => void
  /** Delete a whole folder group recursively; resolves when done, rejects on error */
  onDeleteFolder?: (folder: string) => Promise<void>
  /** Currently selected folder (relative path) — selecting a folder batch-shows its albums */
  selectedFolder?: string | null
  /** Select a folder group (click on the folder heading) */
  onFolderSelect?: (folder: string) => void
}

interface AlbumListItemRowProps {
  album: AlbumListItem
  isSelected: boolean
  onSelect: () => void
  onAnalyzeClick: () => void
  /** Open the delete confirmation for this album */
  onDeleteClick?: () => void
  /** Import this album as-is (no candidate, keep existing tags) */
  onImportAsIs?: () => void
  /** Whether an import request is in flight (disables the as-is button) */
  isImporting?: boolean
  /** Queue position if album is queued (1-indexed), undefined if not queued */
  queuePosition?: number
  /** Active audio-op status ('queued'/'running') if this album is converting */
  convertStatus?: AudioOpActiveStatus
}

interface AlbumGroup {
  /** Parent folder relative to import root; null for albums in the import root. */
  folder: string | null
  albums: AlbumListItem[]
}

interface FolderGroupHeadingProps {
  folder: string
  albumCount: number
  isExpanded: boolean
  isSelected: boolean
  onToggle: () => void
  onSelect?: () => void
  onAnalyze?: () => void
  onDelete?: () => void
}

// ============================================================================
// Helpers
// ============================================================================

/**
 * Group albums by the folder they're saved in, preserving the order albums
 * first appear (which follows the import-tree order). Albums sitting directly
 * in the import root (folder null/undefined) collapse into a single leading
 * untitled group, so the flat single-folder case renders exactly as before.
 */
function groupAlbumsByFolder(albums: AlbumListItem[]): AlbumGroup[] {
  const groups: AlbumGroup[] = []
  const byKey = new Map<string, AlbumGroup>()

  for (const album of albums) {
    const folder = album.folder ?? null
    const key = folder ?? ''
    let group = byKey.get(key)
    if (!group) {
      group = { folder, albums: [] }
      byKey.set(key, group)
      groups.push(group)
    }
    group.albums.push(album)
  }

  return groups
}

// ============================================================================
// Subcomponents
// ============================================================================

/**
 * Folder group heading with a collapse chevron, a click-to-select region, an
 * album-count pill and analyze/delete actions — mirroring the Import Folder
 * card from the Prepare tab. Clicking the chevron toggles the group; clicking
 * the name selects the whole folder for batch editing.
 */
function FolderGroupHeading({
  folder,
  albumCount,
  isExpanded,
  isSelected,
  onToggle,
  onSelect,
  onAnalyze,
  onDelete,
}: FolderGroupHeadingProps) {
  return (
    <div
      className={cn(
        'flex items-center gap-1.5 px-2 py-1.5 rounded-md transition-colors',
        isSelected
          ? 'bg-primary/10 ring-1 ring-primary/20'
          : 'hover:bg-muted/50'
      )}
      data-testid="album-folder-heading"
    >
      {/* Collapse toggle */}
      <button
        type="button"
        onClick={(e) => {
          e.stopPropagation()
          onToggle()
        }}
        className="p-0.5 rounded hover:bg-muted text-muted-foreground flex-shrink-0"
        aria-label={isExpanded ? `Collapse ${folder}` : `Expand ${folder}`}
        aria-expanded={isExpanded}
        data-testid="album-folder-toggle"
      >
        {isExpanded ? (
          <ChevronDown className="h-4 w-4" />
        ) : (
          <ChevronRight className="h-4 w-4" />
        )}
      </button>

      {/* Click-to-select region */}
      <button
        type="button"
        onClick={() => onSelect?.()}
        className="flex items-center gap-1.5 min-w-0 flex-1 text-left"
        aria-pressed={isSelected}
        data-testid="album-folder-select"
      >
        <Folder className="h-3.5 w-3.5 text-blue-500 flex-shrink-0" />
        <span
          className="truncate text-xs font-medium text-muted-foreground"
          title={folder}
        >
          {folder}
        </span>
        <Badge variant="secondary" className="ml-1 flex-shrink-0">
          {albumCount}
        </Badge>
      </button>

      {/* Folder actions */}
      {onAnalyze && (
        <button
          type="button"
          onClick={(e) => {
            e.stopPropagation()
            onAnalyze()
          }}
          className="p-0.5 rounded transition-colors text-muted-foreground/50 hover:text-primary hover:bg-muted cursor-pointer flex-shrink-0"
          aria-label={`Re-analyze all albums in folder ${folder}`}
          title="(Re-)analyze all albums in this folder"
          data-testid="album-folder-analyze-button"
        >
          <Disc className="h-3.5 w-3.5" />
        </button>
      )}
      {onDelete && (
        <button
          type="button"
          onClick={(e) => {
            e.stopPropagation()
            onDelete()
          }}
          className="p-0.5 rounded transition-colors text-muted-foreground/50 hover:text-destructive hover:bg-muted cursor-pointer flex-shrink-0"
          aria-label={`Delete folder ${folder}`}
          title="Delete this folder and everything in it"
          data-testid="album-folder-delete-button"
        >
          <Trash2 className="h-3.5 w-3.5" />
        </button>
      )}
    </div>
  )
}

function AlbumListItemRow({
  album,
  isSelected,
  onSelect,
  onAnalyzeClick,
  onDeleteClick,
  onImportAsIs,
  isImporting,
  queuePosition,
  convertStatus,
}: AlbumListItemRowProps) {
  // Check if this album is in the queue
  const isQueued = queuePosition !== undefined
  // Whether a WAV/WMA convert (or dedup) is queued/running for this album.
  const isConverting = convertStatus !== undefined

  // Stage colors match the disc icon colors in StageIndicator
  // Queued albums get amber styling
  const showQueuedStyle = album.stage === 'none' && isQueued
  const stageStyle = isSelected
    ? 'bg-primary/10 border-primary/30 ring-1 ring-primary/20'
    : album.stage === 'imported'
    ? 'bg-purple-500/5 border-purple-500/25 hover:bg-purple-500/10'
    : album.stage === 'chosen'
    ? 'bg-blue-500/5 border-blue-500/25 hover:bg-blue-500/10'
    : album.stage === 'analyzed'
    ? 'bg-green-500/5 border-green-500/25 hover:bg-green-500/10'
    : showQueuedStyle
    ? 'bg-amber-500/5 border-amber-500/25 hover:bg-amber-500/10'
    : 'bg-card hover:bg-muted/50 border-transparent hover:border-border'

  return (
    <div
      className={cn(
        'flex items-center gap-3 p-3 rounded-lg border cursor-pointer transition-colors',
        stageStyle
      )}
      onClick={onSelect}
      role="button"
      tabIndex={0}
      onKeyDown={(e) => {
        if (e.key === 'Enter' || e.key === ' ') {
          e.preventDefault()
          onSelect()
        }
      }}
      aria-selected={isSelected}
      data-testid="album-list-item"
    >
      {/* Album icon — a stacked disc marks a multi-disc album */}
      {album.isMultiDisc ? (
        <Disc3 className="h-5 w-5 text-green-500 flex-shrink-0" />
      ) : (
        <Music className="h-5 w-5 text-green-500 flex-shrink-0" />
      )}

      {/* Album info */}
      <div className="flex-1 min-w-0">
        <div className="font-medium text-sm truncate" title={album.name}>
          {album.name}
        </div>
        {(album.artist || album.album) && (
          <div className="text-xs text-muted-foreground truncate mt-0.5">
            {album.artist && album.album
              ? `${album.artist} - ${album.album}`
              : album.artist || album.album}
          </div>
        )}
      </div>

      {/* Convert/dedup in progress — spinner driven by the album's own job, so
          it stays on this row even after the user selects another album. */}
      {isConverting && (
        <Loader2
          className="h-4 w-4 flex-shrink-0 text-primary animate-spin"
          aria-label={
            convertStatus === 'queued' ? 'Queued to convert' : 'Converting'
          }
          data-testid="album-converting-spinner"
        />
      )}

      {/* Stage indicator */}
      <StageIndicator
        stage={album.stage}
        isAnalyzing={album.isAnalyzing}
        isQueued={isQueued}
        queuePosition={queuePosition}
        onAnalyzeClick={onAnalyzeClick}
      />

      {/* Import as-is — keep the files' existing tags, no candidate needed */}
      {onImportAsIs && (
        <button
          type="button"
          onClick={(e) => {
            e.stopPropagation()
            if (!isImporting && !album.isAnalyzing && !isQueued) onImportAsIs()
          }}
          disabled={isImporting || album.isAnalyzing || isQueued}
          className={cn(
            'p-0.5 rounded transition-colors text-muted-foreground/40 flex-shrink-0',
            isImporting || album.isAnalyzing || isQueued
              ? 'opacity-40 cursor-not-allowed'
              : 'hover:text-primary hover:bg-muted cursor-pointer'
          )}
          aria-label={`Import album ${album.name} as-is`}
          title="Import as-is (keep existing tags, no matching)"
          data-testid="album-import-as-is-button"
        >
          <FileDown className="h-3.5 w-3.5" />
        </button>
      )}

      {/* Delete album — disabled while the album is queued or being analyzed */}
      {onDeleteClick && (
        <button
          type="button"
          onClick={(e) => {
            e.stopPropagation()
            if (!album.isAnalyzing && !isQueued) onDeleteClick()
          }}
          disabled={album.isAnalyzing || isQueued}
          className={cn(
            'p-0.5 rounded transition-colors text-muted-foreground/40 flex-shrink-0',
            album.isAnalyzing || isQueued
              ? 'opacity-40 cursor-not-allowed'
              : 'hover:text-destructive hover:bg-muted cursor-pointer'
          )}
          aria-label={`Delete album ${album.name}`}
          title={
            album.isAnalyzing || isQueued
              ? 'Cannot delete while analysis is pending'
              : 'Delete from import folder and disk'
          }
          data-testid="album-delete-button"
        >
          <Trash2 className="h-3.5 w-3.5" />
        </button>
      )}
    </div>
  )
}

function AlbumListSkeleton() {
  return (
    <div className="space-y-2 p-1">
      {[1, 2, 3, 4, 5].map((i) => (
        <div
          key={i}
          className="flex items-center gap-3 p-3 rounded-lg border bg-card animate-pulse"
        >
          <div className="h-5 w-5 rounded bg-muted" />
          <div className="flex-1 space-y-2">
            <div className="h-4 w-3/4 rounded bg-muted" />
            <div className="h-3 w-1/2 rounded bg-muted" />
          </div>
          <div className="flex gap-0.5">
            <div className="h-4 w-4 rounded bg-muted" />
            <div className="h-4 w-4 rounded bg-muted" />
          </div>
        </div>
      ))}
    </div>
  )
}

function AlbumListEmpty() {
  return (
    <div className="flex flex-col items-center justify-center py-12 text-center px-4">
      <Folder className="h-12 w-12 text-muted-foreground/50" />
      <p className="mt-4 text-sm text-muted-foreground">
        No album folders found in the import directory.
      </p>
      <p className="mt-1 text-xs text-muted-foreground">
        Run a scan to discover albums, or upload files to the import folder.
      </p>
    </div>
  )
}

function AlbumListError({ message }: { message: string }) {
  return (
    <div className="flex flex-col items-center justify-center py-12 text-center px-4">
      <div className="text-destructive text-sm">{message}</div>
    </div>
  )
}

// ============================================================================
// Main Component
// ============================================================================

/**
 * Card displaying a list of albums discovered in the import folder.
 * Each album shows its name, detected metadata, a stage indicator, and a
 * delete action with confirmation. Albums grouped under a folder render with
 * a collapsible, selectable heading carrying its own analyze/delete actions.
 */
export default function AlbumListCard({
  albums,
  selectedPath,
  onAlbumSelect,
  onAnalyzeClick,
  onDeleteAlbum,
  onImportAsIs,
  isImporting = false,
  isLoading = false,
  error = null,
  className,
  queueStatus = {},
  convertStatus = {},
  onAnalyzeAll,
  isAnalyzingAll = false,
  queueDepth = 0,
  activeCount = 0,
  onAnalyzeFolder,
  onDeleteFolder,
  selectedFolder = null,
  onFolderSelect,
}: AlbumListCardProps) {
  const albumCount = albums.length

  // Album delete confirmation state (single dialog for the whole list)
  const [deleteTarget, setDeleteTarget] = useState<AlbumListItem | null>(null)
  const [isDeleting, setIsDeleting] = useState(false)
  const [deleteError, setDeleteError] = useState<string | null>(null)

  // Folder delete confirmation state
  const [deleteFolderTarget, setDeleteFolderTarget] = useState<{
    folder: string
    albumCount: number
  } | null>(null)
  const [isDeletingFolder, setIsDeletingFolder] = useState(false)
  const [deleteFolderError, setDeleteFolderError] = useState<string | null>(null)

  // Folders collapsed by the user. Folders default to expanded, so we only
  // track the ones explicitly collapsed.
  const [collapsedFolders, setCollapsedFolders] = useState<Set<string>>(new Set())

  const hasQueueActivity = queueDepth > 0 || activeCount > 0

  const handleConfirmDelete = async () => {
    if (!deleteTarget || !onDeleteAlbum) return
    setIsDeleting(true)
    setDeleteError(null)
    try {
      await onDeleteAlbum(deleteTarget.path)
      setDeleteTarget(null)
    } catch (err) {
      setDeleteError(
        err instanceof Error ? err.message : 'Failed to delete album. Please try again.'
      )
    } finally {
      setIsDeleting(false)
    }
  }

  const handleConfirmDeleteFolder = async () => {
    if (!deleteFolderTarget || !onDeleteFolder) return
    setIsDeletingFolder(true)
    setDeleteFolderError(null)
    try {
      await onDeleteFolder(deleteFolderTarget.folder)
      setDeleteFolderTarget(null)
    } catch (err) {
      setDeleteFolderError(
        err instanceof Error ? err.message : 'Failed to delete folder. Please try again.'
      )
    } finally {
      setIsDeletingFolder(false)
    }
  }

  const toggleFolder = (folder: string) => {
    setCollapsedFolders((prev) => {
      const next = new Set(prev)
      if (next.has(folder)) next.delete(folder)
      else next.add(folder)
      return next
    })
  }

  return (
    <Card className={cn('flex flex-col', className)} data-testid="album-list-card">
      <CardHeader className="pb-3">
        <div className="flex items-center justify-between gap-3">
          <CardTitle className="text-lg">
            Albums
            {albumCount > 0 && (
              <Badge variant="secondary" className="ml-2">
                {albumCount}
              </Badge>
            )}
          </CardTitle>

          <div className="flex items-center gap-2">
            {/* Queue depth indicator */}
            {hasQueueActivity && (
              <div
                className="flex items-center gap-1.5 px-2 py-1 rounded-md bg-amber-500/10 border border-amber-500/30"
                data-testid="queue-depth-indicator"
              >
                <ListOrdered className="h-4 w-4 text-amber-500" />
                <span className="text-sm font-medium text-amber-600 dark:text-amber-400">
                  {queueDepth > 0 ? `${queueDepth} queued` : ''}
                  {queueDepth > 0 && activeCount > 0 ? ', ' : ''}
                  {activeCount > 0 ? `${activeCount} analyzing` : ''}
                </span>
              </div>
            )}

            {/* Analyze All — moved here from the panel header */}
            {onAnalyzeAll && (
              <Button
                onClick={onAnalyzeAll}
                disabled={isAnalyzingAll || albumCount === 0}
                size="sm"
                variant="outline"
                data-testid="analyze-all-button"
              >
                {isAnalyzingAll ? (
                  <>
                    <Loader2 className="h-4 w-4 mr-2 animate-spin" />
                    Analyzing...
                  </>
                ) : (
                  <>
                    <Play className="h-4 w-4 mr-2" />
                    Analyze All
                  </>
                )}
              </Button>
            )}
          </div>
        </div>
        <p className="text-xs text-muted-foreground">
          Click an album to view details. Click the disc to analyze, the
          download icon to import as-is, the trash icon to delete.
        </p>
        {/* Icon legend */}
        <div
          className="flex flex-wrap items-center gap-x-4 gap-y-1 pt-1 text-xs text-muted-foreground"
          data-testid="album-list-legend"
        >
          <span className="flex items-center gap-1">
            <Music className="h-3.5 w-3.5 text-green-500" />
            Album
          </span>
          <span className="flex items-center gap-1">
            <Disc3 className="h-3.5 w-3.5 text-green-500" />
            Multi-disc
          </span>
          <span className="flex items-center gap-1">
            <Folder className="h-3.5 w-3.5 text-blue-500" />
            Folder
          </span>
        </div>
      </CardHeader>

      <CardContent className="flex-1">
        {isLoading ? (
          <AlbumListSkeleton />
        ) : error ? (
          <AlbumListError message={error} />
        ) : albums.length === 0 ? (
          <AlbumListEmpty />
        ) : (
          // pt-1 keeps the first folder group's selection ring from being
          // clipped where the card header meets the scroll area.
          <div className="max-h-[400px] overflow-y-auto pr-2 pt-1">
            <div className="space-y-3">
              {groupAlbumsByFolder(albums).map((group) => {
                const isExpanded = group.folder
                  ? !collapsedFolders.has(group.folder)
                  : true
                return (
                  <div
                    key={group.folder ?? '__root__'}
                    data-testid="album-folder-group"
                  >
                    {/* Folder heading — collapsible + selectable, with folder
                        actions. Albums directly in the import root render
                        without a header. */}
                    {group.folder && (
                      <div className="pb-1">
                        <FolderGroupHeading
                          folder={group.folder}
                          albumCount={group.albums.length}
                          isExpanded={isExpanded}
                          isSelected={selectedFolder === group.folder}
                          onToggle={() => toggleFolder(group.folder as string)}
                          onSelect={
                            onFolderSelect
                              ? () => onFolderSelect(group.folder as string)
                              : undefined
                          }
                          onAnalyze={
                            onAnalyzeFolder
                              ? () => onAnalyzeFolder(group.folder as string)
                              : undefined
                          }
                          onDelete={
                            onDeleteFolder
                              ? () => {
                                  setDeleteFolderError(null)
                                  setDeleteFolderTarget({
                                    folder: group.folder as string,
                                    albumCount: group.albums.length,
                                  })
                                }
                              : undefined
                          }
                        />
                      </div>
                    )}
                    {isExpanded && (
                      <div
                        className={cn(
                          'space-y-1.5',
                          // Indent albums under a folder heading so the
                          // hierarchy reads; root-level albums stay flush.
                          group.folder && 'ml-2 border-l border-border/60 pl-3'
                        )}
                      >
                        {group.albums.map((album) => (
                          <AlbumListItemRow
                            key={album.id}
                            album={album}
                            isSelected={selectedPath === album.path}
                            onSelect={() => onAlbumSelect(album.path)}
                            onAnalyzeClick={() => onAnalyzeClick(album.path)}
                            onDeleteClick={
                              onDeleteAlbum
                                ? () => {
                                    setDeleteError(null)
                                    setDeleteTarget(album)
                                  }
                                : undefined
                            }
                            onImportAsIs={
                              onImportAsIs ? () => onImportAsIs(album.path) : undefined
                            }
                            isImporting={isImporting}
                            queuePosition={queueStatus[album.path]}
                            convertStatus={convertStatus[album.path]}
                          />
                        ))}
                      </div>
                    )}
                  </div>
                )
              })}
            </div>
          </div>
        )}
      </CardContent>

      {/* Album delete confirmation dialog */}
      <AlertDialog
        open={deleteTarget !== null}
        onOpenChange={(open) => {
          // Don't allow closing while the delete request is in flight.
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
              This permanently deletes{' '}
              <span className="font-medium text-foreground">
                {deleteTarget?.name}
              </span>{' '}
              from disk and removes it from all import lists. This cannot be
              undone.
            </AlertDialogDescription>
          </AlertDialogHeader>
          {deleteError && <p className="text-sm text-destructive">{deleteError}</p>}
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

      {/* Folder delete confirmation dialog */}
      <AlertDialog
        open={deleteFolderTarget !== null}
        onOpenChange={(open) => {
          if (!isDeletingFolder && !open) setDeleteFolderTarget(null)
        }}
      >
        <AlertDialogContent>
          <AlertDialogHeader>
            <AlertDialogTitle className="flex items-center gap-2">
              <AlertTriangle className="h-5 w-5 text-destructive" />
              Delete folder
            </AlertDialogTitle>
            <AlertDialogDescription>
              This permanently deletes the folder{' '}
              <span className="font-medium text-foreground">
                {deleteFolderTarget?.folder}
              </span>{' '}
              and all{' '}
              {deleteFolderTarget?.albumCount === 1
                ? '1 album'
                : `${deleteFolderTarget?.albumCount ?? 0} albums`}{' '}
              inside it from disk. This cannot be undone.
            </AlertDialogDescription>
          </AlertDialogHeader>
          {deleteFolderError && (
            <p className="text-sm text-destructive">{deleteFolderError}</p>
          )}
          <AlertDialogFooter>
            <AlertDialogCancel disabled={isDeletingFolder}>Cancel</AlertDialogCancel>
            <AlertDialogAction
              onClick={(e) => {
                e.preventDefault()
                handleConfirmDeleteFolder()
              }}
              disabled={isDeletingFolder}
              className="bg-destructive text-destructive-foreground hover:bg-destructive/90"
            >
              {isDeletingFolder ? (
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
    </Card>
  )
}
