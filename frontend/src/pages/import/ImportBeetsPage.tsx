import { useCallback, useEffect, useMemo, useRef, useState, type ReactNode } from 'react'
import { useOutletContext } from 'react-router-dom'
import { ChevronDown, ChevronRight } from 'lucide-react'

import { Card, CardContent, CardHeader, CardTitle } from '@/components/ui/card'
import { Badge } from '@/components/ui/badge'
import { BeetsImportPanel, AudioOpJobsProvider } from '@/components/beets-import'
import { ImportFolderTable } from '@/components/import'
import { BatchTagEditorForm } from '@/components/batch-editor'

import { useImportTree } from '@/hooks/useImportTree'
import type { ItemPreview } from '@/types/batch-tag-editor'
import type { ImportFolderNode } from '@/types/import-tree'

import type { ImportDetailContext } from '../ImportDetailLayout'

// ============================================================================
// Helpers
// ============================================================================

/** Collect every album's import-root-relative path from the import tree. */
function collectAlbumPaths(nodes: ImportFolderNode[]): string[] {
  const out: string[] = []
  const walk = (list: ImportFolderNode[]) => {
    for (const node of list) {
      if (node.isAlbum || node.isMultiDiscParent) out.push(node.path)
      if (node.children.length > 0) walk(node.children)
    }
  }
  walk(nodes)
  return out
}

/** The folder an album path lives in (everything up to the last segment), or null. */
function folderOf(path: string): string | null {
  const slash = path.lastIndexOf('/')
  return slash > 0 ? path.slice(0, slash) : null
}

// ============================================================================
// Collapsible Card
// ============================================================================

interface CollapsibleCardProps {
  title: string
  /** Optional count rendered as a pill next to the title. */
  count?: number
  /** Muted secondary text rendered inline after the title (e.g. folder info). */
  subtitle?: ReactNode
  defaultCollapsed?: boolean
  /** Render the body flush (no padding) — used when the child brings its own frame. */
  flush?: boolean
  children: ReactNode
}

/**
 * A Card whose body collapses behind a chevron toggle in the header. Mirrors the
 * Discovered Items pattern used elsewhere on this page.
 */
function CollapsibleCard({
  title,
  count,
  subtitle,
  defaultCollapsed = false,
  flush = false,
  children,
}: CollapsibleCardProps) {
  const [isCollapsed, setIsCollapsed] = useState(defaultCollapsed)

  return (
    <Card>
      <CardHeader className="pb-3">
        <button
          type="button"
          onClick={() => setIsCollapsed((v) => !v)}
          className="flex items-center gap-2 hover:text-foreground transition-colors text-left"
          aria-expanded={!isCollapsed}
        >
          {isCollapsed ? (
            <ChevronRight className="h-4 w-4 flex-shrink-0" />
          ) : (
            <ChevronDown className="h-4 w-4 flex-shrink-0" />
          )}
          <CardTitle className="text-lg min-w-0">
            {title}
            {count !== undefined && count > 0 && (
              <Badge variant="secondary" className="ml-2">
                {count}
              </Badge>
            )}
            {subtitle && (
              <span className="ml-2 text-sm font-normal text-muted-foreground">
                {subtitle}
              </span>
            )}
          </CardTitle>
        </button>
      </CardHeader>
      {!isCollapsed && (
        <CardContent className={flush ? 'p-0' : undefined}>{children}</CardContent>
      )}
    </Card>
  )
}

// ============================================================================
// Local Album Section — one collapsible album block (folder mode)
// ============================================================================

interface LocalAlbumSectionProps {
  slug: string
  /** Album path relative to the import root. */
  path: string
  /** Heading shown in the collapse toggle (typically the album folder name). */
  heading: string
  /** Loaded track count for the count pill (undefined until the table loads). */
  trackCount?: number
  previewData: Map<number, ItemPreview>
  onItemsLoaded: (ids: number[]) => void
  defaultCollapsed?: boolean
  manualTrackNumbers?: boolean
  onManualNumbersChange?: (values: Record<number, string>) => void
}

/**
 * A collapsible album block for folder mode: a toggle header plus the album's
 * track table (with its Local Album summary). The table stays mounted while
 * collapsed — only hidden — so its item IDs keep feeding the batch editor.
 */
function LocalAlbumSection({
  slug,
  path,
  heading,
  trackCount,
  previewData,
  onItemsLoaded,
  defaultCollapsed = false,
  manualTrackNumbers = false,
  onManualNumbersChange,
}: LocalAlbumSectionProps) {
  const [collapsed, setCollapsed] = useState(defaultCollapsed)

  return (
    <div className="border-b last:border-b-0" data-testid="local-album-section">
      <button
        type="button"
        onClick={() => setCollapsed((v) => !v)}
        className="flex w-full items-center gap-2 px-4 py-2 text-left hover:bg-muted/50 transition-colors"
        aria-expanded={!collapsed}
      >
        {collapsed ? (
          <ChevronRight className="h-4 w-4 text-muted-foreground flex-shrink-0" />
        ) : (
          <ChevronDown className="h-4 w-4 text-muted-foreground flex-shrink-0" />
        )}
        <span className="text-sm font-medium truncate" title={path}>
          {heading}
        </span>
        {trackCount !== undefined && trackCount > 0 && (
          <Badge variant="secondary">{trackCount}</Badge>
        )}
      </button>
      <div className={collapsed ? 'hidden' : 'px-2 pb-3'}>
        <ImportFolderTable
          librarySlug={slug}
          path={path}
          showSummary
          previewData={previewData}
          onItemsLoaded={onItemsLoaded}
          manualTrackNumbers={manualTrackNumbers}
          onManualNumbersChange={onManualNumbersChange}
        />
      </div>
    </div>
  )
}

// ============================================================================
// Main Component — Beets import workspace (albums, candidates, batch editing)
// ============================================================================

export default function ImportBeetsPage() {
  const { slug } = useOutletContext<ImportDetailContext>()

  // Selected album path (absolute) — shared by the album list and candidate
  // details (inside BeetsImportPanel). A folder selection (relative) is the
  // alternative: it batch-shows every album in that folder. The two are
  // mutually exclusive.
  const [selectedPath, setSelectedPath] = useState<string | null>(null)
  const [selectedFolder, setSelectedFolder] = useState<string | null>(null)

  // Loaded track item IDs, keyed by the album's relative path. Multiple tables
  // (one per album in a selected folder) each report into their own slot.
  const [itemIdsByPath, setItemIdsByPath] = useState<Record<string, number[]>>({})
  // Preview changes from the batch editor, fed back into the track table(s).
  const [previewData, setPreviewData] = useState<Map<number, ItemPreview>>(new Map())

  const handlePreviewChange = useCallback(
    (data: Map<number, ItemPreview>) => setPreviewData(data),
    []
  )

  // Manual track numbering: on while the batch editor's Track Number field is
  // in Manual mode. Each album table reports its typed/dragged numbers into
  // its own per-path slot; the merged map feeds the editor's explicit rule.
  const [manualTrackNumbers, setManualTrackNumbers] = useState(false)
  const [manualValuesByPath, setManualValuesByPath] = useState<
    Record<string, Record<number, string>>
  >({})

  const handleTrackNumberManualChange = useCallback((manual: boolean) => {
    setManualTrackNumbers(manual)
    if (!manual) setManualValuesByPath({})
  }, [])

  const handleManualNumbersChange = useCallback(
    (path: string, values: Record<number, string>) => {
      setManualValuesByPath((prev) => {
        const existing = prev[path]
        if (
          existing &&
          Object.keys(existing).length === Object.keys(values).length &&
          Object.entries(values).every(([id, v]) => existing[Number(id)] === v)
        ) {
          return prev
        }
        return { ...prev, [path]: values }
      })
    },
    []
  )

  // Stable per-path onManualNumbersChange wrappers (same pattern as the
  // onItemsLoaded handlers below).
  const manualHandlersRef = useRef<Map<string, (values: Record<number, string>) => void>>(
    new Map()
  )
  const getManualNumbersHandler = useCallback(
    (path: string) => {
      const cache = manualHandlersRef.current
      let handler = cache.get(path)
      if (!handler) {
        handler = (values: Record<number, string>) => handleManualNumbersChange(path, values)
        cache.set(path, handler)
      }
      return handler
    },
    [handleManualNumbersChange]
  )

  // Selecting an album clears any folder selection, and vice versa.
  const handleSelectPath = useCallback((path: string | null) => {
    setSelectedPath(path)
    if (path) setSelectedFolder(null)
  }, [])
  const handleSelectFolder = useCallback((folder: string) => {
    setSelectedFolder(folder)
    setSelectedPath(null)
  }, [])

  // The album list reports absolute paths; the folder-items table keys off
  // import-root-relative paths. Bridge the two using the import base path.
  const { data: importTree } = useImportTree(slug)
  const importBasePath = (importTree?.importPath ?? '').replace(/\/$/, '')
  const relativeSelectedPath = useMemo(() => {
    if (!selectedPath) return null
    const prefix = importBasePath ? `${importBasePath}/` : ''
    return prefix && selectedPath.startsWith(prefix)
      ? selectedPath.slice(prefix.length)
      : selectedPath
  }, [selectedPath, importBasePath])

  // Relative paths of every album inside the selected folder.
  const folderAlbumPaths = useMemo(() => {
    if (!selectedFolder || !importTree?.children) return []
    return collectAlbumPaths(importTree.children).filter(
      (p) => folderOf(p) === selectedFolder
    )
  }, [selectedFolder, importTree?.children])

  // The album(s) currently shown in the Local Album card: a single selected
  // album, or every album inside a selected folder.
  const activePaths = useMemo(() => {
    if (selectedFolder) return folderAlbumPaths
    if (relativeSelectedPath) return [relativeSelectedPath]
    return []
  }, [selectedFolder, folderAlbumPaths, relativeSelectedPath])

  // The batch editor operates on the union of all shown tracks.
  const tableItemIds = useMemo(() => {
    const ids = new Set<number>()
    for (const p of activePaths) {
      for (const id of itemIdsByPath[p] ?? []) ids.add(id)
    }
    return Array.from(ids)
  }, [activePaths, itemIdsByPath])

  // Record a table's loaded IDs, skipping no-op updates so the per-table
  // onItemsLoaded effect can't drive a render loop.
  const handleItemsLoaded = useCallback((path: string, ids: number[]) => {
    setItemIdsByPath((prev) => {
      const existing = prev[path]
      if (
        existing &&
        existing.length === ids.length &&
        existing.every((v, i) => v === ids[i])
      ) {
        return prev
      }
      return { ...prev, [path]: ids }
    })
  }, [])

  // Stable per-path onItemsLoaded wrappers so each table keeps a constant
  // callback identity across renders.
  const itemsLoadedHandlersRef = useRef<Map<string, (ids: number[]) => void>>(new Map())
  const getItemsLoadedHandler = useCallback(
    (path: string) => {
      const cache = itemsLoadedHandlersRef.current
      let handler = cache.get(path)
      if (!handler) {
        handler = (ids: number[]) => handleItemsLoaded(path, ids)
        cache.set(path, handler)
      }
      return handler
    },
    [handleItemsLoaded]
  )

  // The merged manual numbers of every album currently shown, for the batch
  // editor's explicit rule. Item IDs are globally unique, so a plain merge is
  // safe across albums.
  const mergedManualValues = useMemo(() => {
    const merged: Record<number, string> = {}
    for (const p of activePaths) {
      Object.assign(merged, manualValuesByPath[p] ?? {})
    }
    return merged
  }, [activePaths, manualValuesByPath])

  // Clear stale per-album IDs, previews and manual numbers when the active
  // selection changes so data from a previous album/folder doesn't bleed
  // across.
  const activeKey = activePaths.join('|')
  useEffect(() => {
    setItemIdsByPath({})
    setPreviewData(new Map())
    setManualValuesByPath({})
  }, [activeKey])

  // Cards slotted between the album list and the candidate details, matching the
  // designed order: a (self-framed) batch tag editor, then the Local Album card.
  // The Local Album summary is derived from scanned tags, so it shows whether or
  // not the album has been beets-analyzed. Single album → one summarised table;
  // folder → the folder info once, then one collapsible album block each.
  const middleSlot = (
    <>
      <BatchTagEditorForm
        librarySlug={slug}
        itemIds={tableItemIds}
        onPreviewChange={handlePreviewChange}
        disabled={tableItemIds.length === 0}
        collapsible
        defaultCollapsed
        manualTrackNumbers={mergedManualValues}
        onTrackNumberManualChange={handleTrackNumberManualChange}
      />

      <CollapsibleCard
        title="Local Album"
        subtitle={
          selectedFolder ? (
            <>
              · Folder: {selectedFolder} · {tableItemIds.length} track
              {tableItemIds.length !== 1 ? 's' : ''} in {folderAlbumPaths.length}{' '}
              album{folderAlbumPaths.length !== 1 ? 's' : ''}
            </>
          ) : undefined
        }
        flush
      >
        {activePaths.length === 0 ? (
          <div className="p-6 text-center text-sm text-muted-foreground">
            Select an album or a folder above to view and edit its tracks.
          </div>
        ) : selectedFolder ? (
          <>
            {activePaths.map((path) => (
              <LocalAlbumSection
                key={path}
                slug={slug}
                path={path}
                heading={path.split('/').pop() || path}
                trackCount={itemIdsByPath[path]?.length}
                previewData={previewData}
                onItemsLoaded={getItemsLoadedHandler(path)}
                manualTrackNumbers={manualTrackNumbers}
                onManualNumbersChange={getManualNumbersHandler(path)}
              />
            ))}
          </>
        ) : (
          <ImportFolderTable
            librarySlug={slug}
            path={activePaths[0]}
            showSummary
            previewData={previewData}
            onItemsLoaded={getItemsLoadedHandler(activePaths[0])}
            manualTrackNumbers={manualTrackNumbers}
            onManualNumbersChange={getManualNumbersHandler(activePaths[0])}
          />
        )}
      </CollapsibleCard>
    </>
  )

  return (
    <div className="space-y-6">
      {/* Albums + Candidate Details (with batch editor + local album injected).
          Wrapped in the audio-op registry so WAV/WMA conversions run as true
          background jobs — per-album spinners (tree + buttons) and completion
          toasts that survive album switches and component unmounts. */}
      <AudioOpJobsProvider
        librarySlug={slug}
        importBasePath={importBasePath}
        onSelectAlbum={handleSelectPath}
      >
        <BeetsImportPanel
          librarySlug={slug}
          selectedPath={selectedPath}
          onSelectPath={handleSelectPath}
          selectedFolder={selectedFolder}
          onSelectFolder={handleSelectFolder}
          middleSlot={middleSlot}
        />
      </AudioOpJobsProvider>
    </div>
  )
}
