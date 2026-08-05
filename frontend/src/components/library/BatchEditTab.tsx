import { useCallback, useMemo, useState } from 'react'
import { useQueryClient } from '@tanstack/react-query'
import { Loader2, X } from 'lucide-react'

import type { Library } from '@/api/libraries'
import type { ItemPreview, TagName } from '@/types/batch-tag-editor'
import type { LibraryFolderNode } from '@/types/library-tree'

import { libraryItemsKeys, useLibraryItems } from '@/hooks/useLibraryItems'
import { libraryTreeKeys } from '@/hooks/useLibraryTree'
import {
  naturalReorderIds,
  computeReorderChanges,
  buildReorderRules,
  mergeReorderPreview,
  type ReorderChange,
} from '@/lib/reorder'

import { Button } from '@/components/ui/button'
import { Progress } from '@/components/ui/progress'

import LibraryFolderTree from './LibraryFolderTree'
import LibraryItemsTable from './LibraryItemsTable'
import LibraryBatchTagEditorForm from './LibraryBatchTagEditorForm'
import BatchUpdateStatusCard from './BatchUpdateStatusCard'
import {
  DistinctValuesPanel,
  EMPTY_DISTINCT_FILTERS,
  DISTINCT_FILTER_LABELS,
  EMPTY_LABEL,
  itemMatchesFilters,
  type DistinctField,
  type DistinctFilters,
} from './DistinctValuesPanel'

// ============================================================================
// Batch Edit Tab
// ============================================================================
//
// The user picks a folder in the library's on-disk tree. The component loads
// items for every album under that folder in one multi-album request and
// renders the batch editor across all of them. Rules apply to the full union
// of tracks; the post-apply `beet update -a` sync already iterates over the
// unique album names so everything stays coherent.
//
// The progress bar surfaces the request state for folders with many albums —
// a whole-library fetch can pull thousands of tracks and users want to know
// they aren't hanging.
// ============================================================================

interface BatchEditTabProps {
  library: Library
}

export default function BatchEditTab({ library }: BatchEditTabProps) {
  const queryClient = useQueryClient()

  const [selectedFolder, setSelectedFolder] = useState<LibraryFolderNode | null>(null)
  // Preview map coming from the batch-tag editor form (server-computed). The
  // map actually rendered in the table is this merged with reorder changes.
  const [formPreviewData, setFormPreviewData] = useState<Map<number, ItemPreview>>(new Map())

  // Reorder mode state. `order` is the working item-id order; empty until the
  // user enters reorder mode (seeded from the natural display order then).
  const [reorderMode, setReorderMode] = useState(false)
  const [keepTitles, setKeepTitles] = useState(false)
  const [order, setOrder] = useState<number[]>([])

  const [activeJobId, setActiveJobId] = useState<string | null>(null)
  const [albumsToSync, setAlbumsToSync] = useState<string[]>([])
  // Hide the status card after the user clicks its close button. Reset on
  // every new batch update so the next run shows progress fresh.
  const [statusCardDismissed, setStatusCardDismissed] = useState(false)

  // Fetch items for every album below the selected folder in one request.
  // `useLibraryItems` emits repeated `album_id=` params which the backend
  // turns into a `WHERE items.album_id IN (...)` query. perPage is set high
  // enough to cover large libraries in one shot — e.g. 255 albums
  // × ~12 tracks = ~3000 items; a big audiobook library runs ~26k. The
  // backend caps at 50000; if any folder grows past that we'll need real
  // pagination here. (Same caveat as the AlbumsTab fix on 2026-04-27.)
  const {
    data: itemsData,
    isLoading: itemsLoading,
    isFetching: itemsFetching,
    error: itemsError,
  } = useLibraryItems(library.slug, {
    albumIds: selectedFolder?.albumIds,
    perPage: 50000,
    enabled: !!selectedFolder && selectedFolder.albumIds.length > 0,
  })

  // Filters drive both the visible items table and the batch-edit form's
  // itemIds — applying a tag rule with an active filter only touches the
  // matching subset, which is the whole point of being able to filter.
  const [filters, setFilters] = useState<DistinctFilters>(EMPTY_DISTINCT_FILTERS)

  // "Use as template" seed for the batch editor. Clicking the arrow on a
  // distinct value pushes it into the editor as a fixed value for that field.
  // `token` is an incrementing nonce so clicking the same value twice still
  // re-applies (a new object reference alone wouldn't, since value is equal).
  const [seedFixedValue, setSeedFixedValue] = useState<{
    tag: TagName
    value: string
    token: number
  } | null>(null)

  const filteredItems = useMemo(() => {
    const all = itemsData?.items ?? []
    const hasActive = Object.values(filters).some((v) => v != null)
    return hasActive ? all.filter((item) => itemMatchesFilters(item, filters)) : all
  }, [itemsData?.items, filters])

  const itemIds = useMemo(
    () => filteredItems.map((item) => item.id),
    [filteredItems]
  )

  const handleFolderSelect = useCallback((node: LibraryFolderNode | null) => {
    setSelectedFolder(node)
    setFormPreviewData(new Map())
    setActiveJobId(null)
    setAlbumsToSync([])
    setStatusCardDismissed(false)
    setFilters(EMPTY_DISTINCT_FILTERS)
    // A new selection invalidates any in-progress reorder.
    setReorderMode(false)
    setOrder([])
  }, [])

  const handleFilterToggle = useCallback(
    (field: DistinctField, value: string) => {
      setFilters((prev) => ({
        ...prev,
        [field]: prev[field] === value ? null : value,
      }))
      // Active rule previews are computed against itemIds, which are about to
      // change — clear the preview to avoid stale highlights on rows that
      // just dropped out (or are about to enter) the filtered set.
      setFormPreviewData(new Map())
      // Reorder operates on the full, unfiltered album; a filter change exits it.
      setReorderMode(false)
      setOrder([])
    },
    []
  )

  const handleUseAsFixed = useCallback((field: DistinctField, value: string) => {
    setSeedFixedValue((prev) => ({
      // The three DistinctFields (artist/album_artist/genre) are all valid
      // TagNames, so the field name doubles as the editor tag.
      tag: field,
      // EMPTY_LABEL marks tracks that have no value in this field; seed an
      // empty string so applying the template *clears* the tag across the
      // selection (Fixed mode treats "" as a clear).
      value: value === EMPTY_LABEL ? '' : value,
      token: (prev?.token ?? 0) + 1,
    }))
  }, [])

  const handleFilterClear = useCallback((field: DistinctField) => {
    setFilters((prev) => ({ ...prev, [field]: null }))
    setFormPreviewData(new Map())
    setReorderMode(false)
    setOrder([])
  }, [])

  const handleFilterClearAll = useCallback(() => {
    setFilters(EMPTY_DISTINCT_FILTERS)
    setFormPreviewData(new Map())
    setReorderMode(false)
    setOrder([])
  }, [])

  const activeFilterEntries = useMemo(
    () =>
      (Object.entries(filters) as Array<[DistinctField, string | null]>)
        .filter(([, value]) => value != null)
        .map(([field, value]) => ({ field, value: value as string })),
    [filters]
  )

  // --- Reorder derivations ------------------------------------------------
  const albumCount = useMemo(
    () => new Set(filteredItems.map((i) => i.album_id)).size,
    [filteredItems]
  )

  // Reorder is offered only for a single album, unfiltered, with >1 track —
  // it renumbers within the album and within each disc (#104).
  const canReorder =
    albumCount === 1 && activeFilterEntries.length === 0 && filteredItems.length > 1

  const reorderChanges = useMemo(
    () =>
      reorderMode && order.length
        ? computeReorderChanges(filteredItems, order, keepTitles)
        : new Map<number, ReorderChange>(),
    [reorderMode, order, filteredItems, keepTitles]
  )

  const reorderRules = useMemo(() => buildReorderRules(reorderChanges), [reorderChanges])

  // The map the table actually renders: form preview overlaid with reorder
  // changes, so a single "Apply Changes" commits — and previews — both.
  const previewData = useMemo(
    () => mergeReorderPreview(formPreviewData, reorderChanges),
    [formPreviewData, reorderChanges]
  )

  const handleToggleReorder = useCallback(() => {
    setReorderMode((prev) => {
      const next = !prev
      // Seed the working order from the natural display order on entry; clear
      // it on exit so no stale changes linger.
      setOrder(next ? naturalReorderIds(filteredItems) : [])
      return next
    })
  }, [filteredItems])

  const handleReorder = useCallback((next: number[]) => {
    setOrder(next)
  }, [])

  const handlePreviewChange = useCallback((next: Map<number, ItemPreview>) => {
    setFormPreviewData(next)
  }, [])

  const handleBatchUpdateComplete = useCallback((jobId: string, albums: string[]) => {
    setActiveJobId(jobId)
    setAlbumsToSync(albums)
    setStatusCardDismissed(false)
  }, [])

  const handleJobComplete = useCallback(
    (allSucceeded: boolean) => {
      // The Celery sync just rewrote albums.* / items.* in the beets DB,
      // and `beet move` may have relocated files on disk too — that means
      // every cached items_path entry is stale, AND the folder tree we
      // built from those paths is stale. Refetch both so the
      // distinct-values panel, the items table, and the folder tree all
      // reflect the new layout without needing a full page reload.
      //
      // refetchType: 'active' forces an immediate refetch of any query
      // that has a mounted observer, instead of just marking it stale and
      // waiting for the next mount/window-focus event. Without it the
      // tree refresh sometimes lagged behind the move in real
      // sessions.
      queryClient.invalidateQueries({
        queryKey: libraryItemsKeys.lists(),
        refetchType: 'active',
      })
      queryClient.invalidateQueries({
        queryKey: libraryTreeKeys.byLibrary(library.slug),
        refetchType: 'active',
      })
      // Stale active filters often pin the *old* value (e.g. "Artist:
      // André Marx" right after we just renamed those tracks to "Die
      // drei ???"), which would show an empty table. Drop them.
      if (allSucceeded) {
        setFilters(EMPTY_DISTINCT_FILTERS)
        setFormPreviewData(new Map())
        // The committed reorder is now the on-disk truth; drop the working
        // order so the refetched tracks render in their new natural order.
        setReorderMode(false)
        setOrder([])
      }
    },
    [queryClient, library.slug]
  )

  const handleStatusCardDismiss = useCallback(() => {
    setStatusCardDismissed(true)
    setActiveJobId(null)
    setAlbumsToSync([])
  }, [])

  // "Selected album" header text for the tracks table. For a single-album
  // leaf we still show the real album name; for a branch folder we show its
  // path so users can tell what scope their edits will touch.
  const headerLabel = useMemo(() => {
    if (!selectedFolder) return null
    if (selectedFolder.path === '' || selectedFolder.path == null) {
      return `All albums (${selectedFolder.albumIds.length})`
    }
    if (selectedFolder.albumIds.length === 1 && !selectedFolder.children.length) {
      return selectedFolder.name
    }
    const n = selectedFolder.albumIds.length
    return `${selectedFolder.path} · ${n} ${n === 1 ? 'album' : 'albums'}`
  }, [selectedFolder])

  // Loading-progress display above the table. `useLibraryItems` is a single
  // React Query request, so "processed / total albums" isn't directly
  // observable — but we can reflect the intent: before the response lands
  // we show indeterminate progress; after, we show how many albums the
  // response actually contained vs. how many we asked for.
  const loadedAlbumCount = useMemo(() => {
    if (!itemsData?.items) return 0
    return new Set(itemsData.items.map((i) => i.album_id)).size
  }, [itemsData?.items])

  const totalAlbumCount = selectedFolder?.albumIds.length ?? 0
  const isActivelyLoading = itemsLoading || itemsFetching

  return (
    <div className="space-y-6">
      {/* Top section: stacked full-width cards — the library folder tree
          first, then the batch-tag editor below it. */}
      <div className="space-y-4">
        <div className="h-[400px]">
          <LibraryFolderTree
            librarySlug={library.slug}
            onSelect={handleFolderSelect}
            selectedPath={selectedFolder?.path ?? null}
            selectedAlbumIds={selectedFolder?.albumIds}
            className="h-full"
          />
        </div>

        <div>
          <LibraryBatchTagEditorForm
            librarySlug={library.slug}
            itemIds={itemIds}
            onPreviewChange={handlePreviewChange}
            onBatchUpdateComplete={handleBatchUpdateComplete}
            disabled={!selectedFolder || itemIds.length === 0}
            extraRules={reorderRules}
            extraChangedItemCount={reorderChanges.size}
            seedFixedValue={seedFixedValue}
          />
        </div>
      </div>

      {activeJobId && albumsToSync.length > 0 && !statusCardDismissed && (
        <BatchUpdateStatusCard
          librarySlug={library.slug}
          jobId={activeJobId}
          albumsToSync={albumsToSync}
          onComplete={handleJobComplete}
          onDismiss={handleStatusCardDismiss}
        />
      )}

      {/* Loading progress — shown whenever we have a selected folder and
          either the request is in flight or the response is still partial. */}
      {selectedFolder && (isActivelyLoading || loadedAlbumCount < totalAlbumCount) && (
        <div className="rounded-md border bg-muted/30 p-3 space-y-2">
          <div className="flex items-center gap-2 text-sm text-muted-foreground">
            <Loader2 className="h-4 w-4 animate-spin shrink-0" />
            <span className="truncate">
              Loading albums… {loadedAlbumCount} / {totalAlbumCount}
            </span>
          </div>
          <Progress
            value={
              totalAlbumCount === 0
                ? 0
                : Math.round((loadedAlbumCount / totalAlbumCount) * 100)
            }
            className="h-2"
          />
        </div>
      )}

      {itemsData && itemsData.items.length > 0 && (
        <DistinctValuesPanel
          items={itemsData.items}
          activeFilters={filters}
          onValueClick={handleFilterToggle}
          onUseAsFixed={handleUseAsFixed}
        />
      )}

      {/* Active-filters bar — surfaces the chosen filter chips with one-click
          clear + a "Clear all" escape hatch. Hidden when nothing is filtered. */}
      {activeFilterEntries.length > 0 && (
        <div className="flex flex-wrap items-center gap-2 rounded-md border bg-muted/30 px-3 py-2 text-sm">
          <span className="text-muted-foreground">Active filters:</span>
          {activeFilterEntries.map(({ field, value }) => (
            <button
              key={field}
              type="button"
              onClick={() => handleFilterClear(field)}
              className="inline-flex items-center gap-1 rounded-full border bg-background px-2 py-0.5 text-xs hover:bg-accent transition-colors"
              title={`Clear ${DISTINCT_FILTER_LABELS[field]} filter`}
            >
              <span className="font-medium">
                {DISTINCT_FILTER_LABELS[field]}:
              </span>
              <span className="max-w-[16rem] truncate">{value}</span>
              <X className="h-3 w-3 shrink-0 opacity-70" />
            </button>
          ))}
          <span className="ml-auto text-xs text-muted-foreground">
            {filteredItems.length} of {itemsData?.items.length ?? 0} tracks
          </span>
          <Button
            variant="ghost"
            size="sm"
            className="h-7 px-2 text-xs"
            onClick={handleFilterClearAll}
          >
            Clear all
          </Button>
        </div>
      )}

      <LibraryItemsTable
        librarySlug={library.slug}
        items={filteredItems}
        isLoading={itemsLoading && !itemsData}
        error={itemsError as Error | null}
        selectedAlbum={headerLabel}
        total={filteredItems.length}
        previewData={previewData}
        canReorder={canReorder}
        reorderMode={reorderMode}
        onToggleReorder={handleToggleReorder}
        keepTitles={keepTitles}
        onKeepTitlesChange={setKeepTitles}
        order={order}
        onReorder={handleReorder}
      />
    </div>
  )
}
