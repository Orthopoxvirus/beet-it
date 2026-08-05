import { Fragment, useState, useRef, useEffect, useCallback, useMemo } from 'react'
import { Link, useSearchParams, useLocation } from 'react-router-dom'
import { Music, Disc3, X, Users, Folder as FolderIcon, MoreVertical, Image as ImageIcon, ArrowRightLeft, Download, Plus, Check } from 'lucide-react'

import { Button } from '@/components/ui/button'
import { Card } from '@/components/ui/card'
import { Badge } from '@/components/ui/badge'
import { AlphabetNav } from '@/components/ui/AlphabetNav'
import {
  DropdownMenu,
  DropdownMenuTrigger,
  DropdownMenuContent,
  DropdownMenuItem,
  DropdownMenuSeparator,
} from '@/components/ui/dropdown-menu'
import { cn } from '@/lib/utils'

import { useLibraryAlbums, useAlbumLetters } from '@/hooks/useAlbums'
import { useLibraryTree } from '@/hooks/useLibraryTree'
import { getAlbumCoverUrl, getAlbumDownloadUrl, type Album } from '@/api/albums'
import { fetchAlbumSize } from '@/api/downloads'
import { useDownloadGather } from '@/contexts/DownloadGatherContext'
import { CoverArtUpload } from '@/components/album/CoverArtUpload'
import { MoveAlbumDialog } from '@/components/album/MoveAlbumDialog'
import type { Library } from '@/api/libraries'
import type { LibraryFolderNode } from '@/types/library-tree'

type ViewMode = 'albums' | 'artists' | 'folders'

const VIEW_MODES: readonly ViewMode[] = ['albums', 'artists', 'folders'] as const
const VIEW_LABELS: Record<ViewMode, string> = {
  albums: 'Albums',
  artists: 'Album Artists',
  folders: 'Folders',
}

const VIEW_MODE_STORAGE_PREFIX = 'library-albums-view-mode:'

function readStoredViewMode(slug: string): ViewMode {
  try {
    const stored = localStorage.getItem(VIEW_MODE_STORAGE_PREFIX + slug)
    if (stored && (VIEW_MODES as readonly string[]).includes(stored)) {
      return stored as ViewMode
    }
    return 'albums'
  } catch {
    return 'albums'
  }
}

function writeStoredViewMode(slug: string, mode: ViewMode): void {
  try {
    localStorage.setItem(VIEW_MODE_STORAGE_PREFIX + slug, mode)
  } catch {
    // localStorage can throw in private mode / when full — best-effort persist
  }
}

const UNKNOWN_ARTIST_LABEL = '(Unknown Artist)'

interface ArtistGroup {
  /** Display name; '(Unknown Artist)' for empty albumartist values. */
  name: string
  /** Lower-cased name used for sorting. */
  sortKey: string
  /** All albums by this artist. */
  albums: Album[]
}

function groupAlbumsByArtist(albums: Album[]): ArtistGroup[] {
  const map = new Map<string, ArtistGroup>()
  for (const album of albums) {
    const trimmed = (album.artist || '').trim()
    const display = trimmed === '' ? UNKNOWN_ARTIST_LABEL : trimmed
    const key = display.toLowerCase()
    let group = map.get(key)
    if (!group) {
      group = { name: display, sortKey: key, albums: [] }
      map.set(key, group)
    }
    group.albums.push(album)
  }
  // Stable sort within each group by album title for deterministic display.
  for (const group of map.values()) {
    group.albums.sort((a, b) =>
      a.title.localeCompare(b.title, undefined, { sensitivity: 'base' })
    )
  }
  return Array.from(map.values()).sort((a, b) =>
    a.sortKey.localeCompare(b.sortKey, undefined, { sensitivity: 'base' })
  )
}

// ============================================================================
// Helper Functions
// ============================================================================

/**
 * Get the letter group for a title-ish string.
 * Returns A-Z for alphabetic first characters, '#' for numbers/special chars.
 */
function getLetterGroup(value: string): string {
  if (!value || value.length === 0) return '#'
  const firstChar = value.charAt(0).toUpperCase()
  if (firstChar >= 'A' && firstChar <= 'Z') {
    return firstChar
  }
  return '#'
}

/**
 * Sort comparator that puts A-Z first and '#' (non-alpha bucket) last.
 */
function compareLetters(a: string, b: string): number {
  if (a === '#') return 1
  if (b === '#') return -1
  return a.localeCompare(b)
}

/**
 * Group items by the first letter of `getKey(item)`. Buckets are ordered
 * A-Z then '#'. Items inside each bucket retain their input order — sort
 * before calling if a specific within-bucket order matters.
 */
function groupByFirstLetter<T>(
  items: T[],
  getKey: (item: T) => string,
): Map<string, T[]> {
  const buckets = new Map<string, T[]>()
  for (const item of items) {
    const letter = getLetterGroup(getKey(item))
    let bucket = buckets.get(letter)
    if (!bucket) {
      bucket = []
      buckets.set(letter, bucket)
    }
    bucket.push(item)
  }
  const ordered = new Map<string, T[]>()
  for (const letter of Array.from(buckets.keys()).sort(compareLetters)) {
    ordered.set(letter, buckets.get(letter)!)
  }
  return ordered
}

/**
 * Group albums by their starting letter (album title). Sorted alphabetically
 * by title before bucketing so within-letter order is stable.
 */
function groupAlbumsByLetter(albums: Album[]): Map<string, Album[]> {
  const sorted = [...albums].sort((a, b) =>
    a.title.localeCompare(b.title, undefined, { sensitivity: 'base' })
  )
  return groupByFirstLetter(sorted, (a) => a.title)
}

// ============================================================================
// Album Card Component
// ============================================================================

interface AlbumCardProps {
  album: Album
  slug: string
  /**
   * URL of the originating albums grid (incl. view/filter query string).
   * Passed as router state so the album detail's "Back to Albums" control
   * can return to the exact filtered grid the user came from.
   */
  fromUrl: string
}

function AlbumCard({ album, slug, fromUrl }: AlbumCardProps) {
  const [imgError, setImgError] = useState(false)
  const [showCover, setShowCover] = useState(false)
  const [showMove, setShowMove] = useState(false)
  const { count, isGathered, addAlbum, removeAlbum } = useDownloadGather()
  const gathered = isGathered(album.id)
  // Once any album is gathered we're in "select mode": cards turn the cover
  // into a one-click select toggle and hide the per-card actions menu.
  const selectMode = count > 0

  // 384px hits ~retina @ 192px tile. Original artwork can be multi-MB; using
  // the cached WebP thumbnail keeps the grid view responsive on mobile.
  const coverUrl = album.cover_art_path
    ? getAlbumCoverUrl(slug, album.id, 384, album.cover_version)
    : null

  const detailTo = `/libraries/${slug}/albums/${album.id}`

  const handleGather = async () => {
    if (gathered) {
      removeAlbum(album.id)
      return
    }
    // Add immediately (unknown size), then fill in the size so the gathering
    // bar's running total stays accurate without blocking the click.
    const base = { id: album.id, title: album.title, artist: album.artist }
    addAlbum(slug, { ...base, sizeBytes: null })
    try {
      const { size_bytes } = await fetchAlbumSize(slug, album.id)
      addAlbum(slug, { ...base, sizeBytes: size_bytes })
    } catch {
      // Keep it gathered with an unknown size — the backend sizes it for real.
    }
  }

  const coverArt =
    coverUrl && !imgError ? (
      <img
        src={coverUrl}
        alt={`${album.title} by ${album.artist}`}
        className="w-full h-full object-cover"
        loading="lazy"
        onError={() => setImgError(true)}
      />
    ) : (
      <div className="w-full h-full flex items-center justify-center bg-muted">
        <Music className="h-12 w-12 text-muted-foreground" />
      </div>
    )

  const albumInfo = (
    <>
      <h3
        className="font-medium text-sm truncate group-hover:text-primary transition-colors"
        title={album.title}
      >
        {album.title}
      </h3>
      <p className="text-xs text-muted-foreground truncate mt-0.5" title={album.artist}>
        {album.artist}
      </p>
    </>
  )

  // ── Select mode: cover toggles selection, title/artist opens the album ──
  if (selectMode) {
    return (
      <div className="relative">
        <Card className="overflow-hidden group hover:shadow-md transition-all duration-200">
          <button
            type="button"
            onClick={handleGather}
            aria-pressed={gathered}
            aria-label={`${gathered ? 'Deselect' : 'Select'} ${album.title} for download`}
            className="block w-full aspect-square bg-muted relative cursor-pointer focus:outline-none focus:ring-2 focus:ring-ring focus:ring-inset"
          >
            {coverArt}
            {gathered && <span className="absolute inset-0 bg-primary/30" aria-hidden="true" />}
            {/* Circular checkbox indicator. */}
            <span
              aria-hidden="true"
              className={cn(
                'absolute top-2 left-2 flex h-6 w-6 items-center justify-center rounded-full border-2 shadow-sm transition-colors',
                gathered
                  ? 'bg-primary border-primary text-primary-foreground'
                  : 'bg-background/70 border-foreground/40'
              )}
            >
              {gathered && <Check className="h-4 w-4" />}
            </span>
          </button>
          <Link
            to={detailTo}
            state={{ from: fromUrl }}
            className="block p-3 focus:outline-none focus:ring-2 focus:ring-ring focus:ring-inset"
          >
            {albumInfo}
          </Link>
        </Card>
      </div>
    )
  }

  // ── Normal mode: whole card opens the album; 3-dots actions menu ──
  return (
    <div className="relative">
      <Link
        to={detailTo}
        state={{ from: fromUrl }}
        className="block focus:outline-none focus:ring-2 focus:ring-ring focus:ring-offset-2 rounded-lg"
      >
        <Card className="overflow-hidden group hover:shadow-md hover:scale-[1.02] transition-all duration-200 cursor-pointer">
          <div className="aspect-square bg-muted relative">{coverArt}</div>
          <div className="p-3">{albumInfo}</div>
        </Card>
      </Link>

      {/* 3-dots actions menu. A sibling of the Link (not nested) so its clicks
          never trigger card navigation. */}
      <div className="absolute top-2 right-2">
        <DropdownMenu>
          <DropdownMenuTrigger asChild>
            <Button
              size="icon"
              variant="secondary"
              className="h-7 w-7 opacity-80 hover:opacity-100 shadow-sm"
              aria-label={`Actions for ${album.title}`}
            >
              <MoreVertical className="h-4 w-4" />
            </Button>
          </DropdownMenuTrigger>
          <DropdownMenuContent align="end">
            <DropdownMenuItem onClick={() => setShowCover(true)}>
              <ImageIcon className="mr-2 h-4 w-4" /> Change cover
            </DropdownMenuItem>
            <DropdownMenuItem onClick={() => setShowMove(true)}>
              <ArrowRightLeft className="mr-2 h-4 w-4" /> Move to library
            </DropdownMenuItem>
            <DropdownMenuItem asChild>
              <a href={getAlbumDownloadUrl(slug, album.id)} download>
                <Download className="mr-2 h-4 w-4" /> Download zip
              </a>
            </DropdownMenuItem>
            <DropdownMenuSeparator />
            <DropdownMenuItem onClick={handleGather}>
              <Plus className="mr-2 h-4 w-4" /> Add to download
            </DropdownMenuItem>
          </DropdownMenuContent>
        </DropdownMenu>
      </div>

      {showCover && (
        <CoverArtUpload
          slug={slug}
          albumId={album.id}
          isOpen={showCover}
          onClose={() => setShowCover(false)}
          onSuccess={() => setImgError(false)}
        />
      )}
      {showMove && (
        // No `onMoved`: we're already on the overview, so stay put and keep the
        // current view/folder/artist filters. The move invalidates the album
        // list query, so the source row refreshes in place on its own.
        <MoveAlbumDialog
          sourceSlug={slug}
          albumId={album.id}
          albumTitle={album.title}
          albumArtist={album.artist}
          isOpen={showMove}
          onClose={() => setShowMove(false)}
        />
      )}
    </div>
  )
}

// ============================================================================
// Cover Mosaic — single cover for one album, otherwise a 2x2 of up to four
// representative covers. Used for both Album-Artist and Folder cards.
// ============================================================================

interface CoverMosaicProps {
  /** Albums this card represents, ordered by relevance (e.g. by title). */
  albums: Album[]
  slug: string
  /** Icon to show when no album under this card has cover art. */
  fallbackIcon: React.ReactNode
}

function CoverTile({
  album,
  slug,
  size,
  className,
}: {
  album: Album
  slug: string
  size: number
  className?: string
}) {
  const [imgError, setImgError] = useState(false)
  const url = album.cover_art_path
    ? getAlbumCoverUrl(slug, album.id, size, album.cover_version)
    : null
  if (!url || imgError) {
    return (
      <div className={cn('w-full h-full bg-muted', className)} aria-hidden />
    )
  }
  return (
    <img
      src={url}
      alt=""
      className={cn('w-full h-full object-cover', className)}
      loading="lazy"
      onError={() => setImgError(true)}
    />
  )
}

function CoverMosaic({ albums, slug, fallbackIcon }: CoverMosaicProps) {
  // Pick up to four albums with covers; fall back to first four albums
  // overall if fewer have art (still gives the mosaic a deterministic
  // shape rather than empty rectangles).
  const withCovers = albums.filter((a) => a.cover_art_path)
  const picks = (withCovers.length ? withCovers : albums).slice(0, 4)

  if (picks.length === 0) {
    return (
      <div className="w-full h-full flex items-center justify-center bg-muted">
        {fallbackIcon}
      </div>
    )
  }

  if (picks.length === 1) {
    return <CoverTile album={picks[0]} slug={slug} size={384} />
  }

  // 2x2 grid for 2-4 covers. With only 2 we duplicate one to keep the
  // shape; with 3 we leave the bottom-right blank (muted). Tiles are
  // requested at 192px since each one renders at half the card size.
  const tileSize = 192
  const cells: (Album | null)[] = [...picks]
  while (cells.length < 4) cells.push(null)
  return (
    <div className="grid grid-cols-2 grid-rows-2 w-full h-full gap-px bg-border">
      {cells.map((album, idx) =>
        album ? (
          <CoverTile
            key={`${album.id}-${idx}`}
            album={album}
            slug={slug}
            size={tileSize}
          />
        ) : (
          <div key={`empty-${idx}`} className="w-full h-full bg-muted" />
        )
      )}
    </div>
  )
}

// ============================================================================
// Artist Card Component
// ============================================================================

interface ArtistCardProps {
  group: ArtistGroup
  slug: string
  onClick: (artist: string) => void
}

function ArtistCard({ group, slug, onClick }: ArtistCardProps) {
  const albumCount = group.albums.length
  const isUnknown = group.name === UNKNOWN_ARTIST_LABEL

  return (
    <button
      type="button"
      onClick={() => onClick(group.name)}
      className="block w-full text-left focus:outline-none focus:ring-2 focus:ring-ring focus:ring-offset-2 rounded-lg"
      aria-label={`${group.name}, ${albumCount} album${albumCount === 1 ? '' : 's'}`}
    >
      <Card className="overflow-hidden group hover:shadow-md hover:scale-[1.02] transition-all duration-200 cursor-pointer">
        <div className="aspect-square bg-muted relative">
          <CoverMosaic
            albums={group.albums}
            slug={slug}
            fallbackIcon={<Users className="h-12 w-12 text-muted-foreground" />}
          />
          <Badge
            variant="secondary"
            className="absolute top-2 right-2 backdrop-blur bg-background/80"
          >
            {albumCount}
          </Badge>
        </div>
        <div className="p-3">
          <h3
            className={cn(
              'font-medium text-sm truncate group-hover:text-primary transition-colors',
              isUnknown && 'italic text-muted-foreground'
            )}
            title={group.name}
          >
            {group.name}
          </h3>
          <p className="text-xs text-muted-foreground truncate mt-0.5">
            {albumCount} album{albumCount === 1 ? '' : 's'}
          </p>
        </div>
      </Card>
    </button>
  )
}

// ============================================================================
// Folder Card Component
// ============================================================================

/** Top-level folder summary as rendered in the Folders view. */
interface TopLevelFolder {
  /** Display name (folder basename). */
  name: string
  /** Path relative to the library root. */
  path: string
  /** Distinct album_ids living under this folder (any depth). */
  albumIds: number[]
  /** Albums under this folder, for the 2x2 cover mosaic. */
  albums: Album[]
}

interface FolderCardProps {
  folder: TopLevelFolder
  slug: string
  onClick: (folder: TopLevelFolder) => void
}

function FolderCard({ folder, slug, onClick }: FolderCardProps) {
  const albumCount = folder.albumIds.length
  return (
    <button
      type="button"
      onClick={() => onClick(folder)}
      className="block w-full text-left focus:outline-none focus:ring-2 focus:ring-ring focus:ring-offset-2 rounded-lg"
      aria-label={`Folder ${folder.name}, ${albumCount} album${albumCount === 1 ? '' : 's'}`}
    >
      <Card className="overflow-hidden group hover:shadow-md hover:scale-[1.02] transition-all duration-200 cursor-pointer">
        <div className="aspect-square bg-muted relative">
          <CoverMosaic
            albums={folder.albums}
            slug={slug}
            fallbackIcon={<FolderIcon className="h-12 w-12 text-muted-foreground" />}
          />
          <Badge
            variant="secondary"
            className="absolute top-2 right-2 backdrop-blur bg-background/80"
          >
            {albumCount}
          </Badge>
        </div>
        <div className="p-3">
          <h3
            className="font-medium text-sm truncate group-hover:text-primary transition-colors"
            title={folder.path || folder.name}
          >
            {folder.name}
          </h3>
          <p className="text-xs text-muted-foreground truncate mt-0.5">
            {albumCount} album{albumCount === 1 ? '' : 's'}
          </p>
        </div>
      </Card>
    </button>
  )
}

// ============================================================================
// View-mode pills + active artist filter chip
// ============================================================================

interface ViewModePillsProps {
  mode: ViewMode
  onChange: (mode: ViewMode) => void
  activeArtist: string | null
  activeFolder: string | null
  onClearArtistFilter: () => void
  onClearFolderFilter: () => void
}

function ViewModePills({
  mode,
  onChange,
  activeArtist,
  activeFolder,
  onClearArtistFilter,
  onClearFolderFilter,
}: ViewModePillsProps) {
  return (
    <div className="flex flex-wrap items-center gap-3">
      {/* Pill group */}
      <div
        role="tablist"
        aria-label="Albums view mode"
        className="inline-flex items-center rounded-full border bg-muted/40 p-0.5"
      >
        {VIEW_MODES.map((value) => {
          const active = value === mode
          return (
            <button
              key={value}
              type="button"
              role="tab"
              aria-selected={active}
              onClick={() => onChange(value)}
              className={cn(
                'px-3 py-1 text-sm rounded-full transition-colors',
                active
                  ? 'bg-background shadow-sm text-foreground'
                  : 'text-muted-foreground hover:text-foreground'
              )}
            >
              {VIEW_LABELS[value]}
            </button>
          )
        })}
      </div>

      {activeArtist && (
        <button
          type="button"
          onClick={onClearArtistFilter}
          className="inline-flex items-center gap-1 rounded-full border bg-background px-2 py-0.5 text-xs hover:bg-accent transition-colors"
          title="Clear artist filter"
        >
          <span className="font-medium">Artist:</span>
          <span className="max-w-[16rem] truncate">{activeArtist}</span>
          <X className="h-3 w-3 shrink-0 opacity-70" />
        </button>
      )}

      {activeFolder && (
        <button
          type="button"
          onClick={onClearFolderFilter}
          className="inline-flex items-center gap-1 rounded-full border bg-background px-2 py-0.5 text-xs hover:bg-accent transition-colors"
          title="Clear folder filter"
        >
          <span className="font-medium">Folder:</span>
          <span className="max-w-[16rem] truncate">{activeFolder}</span>
          <X className="h-3 w-3 shrink-0 opacity-70" />
        </button>
      )}
    </div>
  )
}

// ============================================================================
// Loading Skeleton Component
// ============================================================================

function AlbumCardSkeleton() {
  return (
    <Card className="overflow-hidden">
      {/* Cover Art Skeleton */}
      <div className="aspect-square bg-muted animate-pulse" />

      {/* Album Info Skeleton */}
      <div className="p-3 space-y-2">
        <div className="h-4 bg-muted animate-pulse rounded w-3/4" />
        <div className="h-3 bg-muted animate-pulse rounded w-1/2" />
      </div>
    </Card>
  )
}

function LoadingSkeleton() {
  return (
    <div className="grid grid-cols-2 sm:grid-cols-3 md:grid-cols-4 lg:grid-cols-5 xl:grid-cols-6 gap-4 pr-8">
      {Array.from({ length: 12 }).map((_, i) => (
        <AlbumCardSkeleton key={i} />
      ))}
    </div>
  )
}

// ============================================================================
// Letter anchor — invisible element used as a scroll target by the alphabet
// nav. Sized as col-span-full so it inserts cleanly between rows of any
// grid we render (albums, artists, folders). One instance per letter
// bucket; the parent threads a ref into it for handleLetterSelect.
// ============================================================================

interface LetterAnchorProps {
  letter: string
  anchorRef: (element: HTMLDivElement | null) => void
}

function LetterAnchor({ letter, anchorRef }: LetterAnchorProps) {
  return (
    <div
      ref={anchorRef}
      id={`letter-${letter}`}
      data-letter={letter}
      className="col-span-full scroll-mt-20"
      aria-hidden="true"
    />
  )
}

// ============================================================================
// Albums Tab Component
// ============================================================================

interface AlbumsTabProps {
  library: Library
}

export default function AlbumsTab({ library }: AlbumsTabProps) {
  const {
    data: albumsData,
    isLoading: albumsLoading,
    error: albumsError,
  } = useLibraryAlbums(library.slug)

  const {
    data: availableLetters = [],
    isLoading: lettersLoading,
  } = useAlbumLetters(library.slug)

  // Folder data — only used by the Folders view + the folder-filter
  // path lookup. Failures are silent; the folders pill just shows an
  // empty state.
  const { data: treeData } = useLibraryTree(library.slug)

  const [currentLetter, setCurrentLetter] = useState<string | null>(null)
  const anchorRefs = useRef<Map<string, HTMLDivElement>>(new Map())
  const observerRef = useRef<IntersectionObserver | null>(null)

  // View + filter state lives in the URL query string so back-navigation,
  // refresh and link-sharing all restore the same drill-down (issue #98).
  // The originating grid URL is also threaded into each album card as router
  // state, so the album detail's "Back to Albums" returns to this exact view.
  const [searchParams, setSearchParams] = useSearchParams()
  const location = useLocation()
  const fromUrl = location.pathname + location.search

  // View mode (albums / album-artists / folders) comes from `?view=`,
  // falling back to the per-library stored preference when the URL is bare
  // (so a freshly-opened library still honours what the user last picked).
  const viewParam = searchParams.get('view')
  const viewMode: ViewMode =
    viewParam && (VIEW_MODES as readonly string[]).includes(viewParam)
      ? (viewParam as ViewMode)
      : readStoredViewMode(library.slug)

  // Persist the active view as this library's default for next time.
  useEffect(() => {
    writeStoredViewMode(library.slug, viewMode)
  }, [library.slug, viewMode])

  // Albums-grid filters, URL-encoded. For artist, `null` (param absent) means
  // "no filter" while `''` (`?artist=`) is the explicit Unknown-Artist bucket.
  // For folder we carry the readable folder name and re-resolve the full node
  // (with its albumIds) from the loaded tree below.
  const filterArtist = searchParams.get('artist')
  const folderParam = searchParams.get('folder')

  // Track the last update time to throttle state changes
  const lastUpdateRef = useRef<number>(0)
  const THROTTLE_MS = 100

  const allAlbums = albumsData?.items ?? []

  // Top-level folders for the Folders view. Each card represents one direct
  // child of the library root — typically the per-artist
  // folder. The albumIds list comes straight from the tree node so we can
  // filter the Albums view by exactly the same set when the user clicks.
  const topLevelFolders = useMemo<TopLevelFolder[]>(() => {
    if (!treeData?.root?.children?.length) return []
    const albumsById = new Map(allAlbums.map((a) => [a.id, a]))
    const buildFolder = (node: LibraryFolderNode): TopLevelFolder => {
      const albumIds = node.albumIds ?? []
      const albums = albumIds
        .map((id) => albumsById.get(id))
        .filter((a): a is Album => Boolean(a))
      return {
        name: node.name,
        path: node.path || node.name,
        albumIds,
        albums,
      }
    }
    return treeData.root.children
      .map(buildFolder)
      .filter((f) => f.albumIds.length > 0)
      .sort((a, b) =>
        a.name.localeCompare(b.name, undefined, { sensitivity: 'base' })
      )
  }, [treeData, allAlbums])

  // Re-resolve the active folder filter from its URL name. Null while the
  // tree is still loading or when the name doesn't match a top-level folder
  // (e.g. a stale/hand-edited URL) — in that case the grid just shows
  // everything rather than an empty result.
  const filterFolder = useMemo<TopLevelFolder | null>(() => {
    if (folderParam === null) return null
    return topLevelFolders.find((f) => f.name === folderParam) ?? null
  }, [folderParam, topLevelFolders])

  // Memoize grouped albums for the Albums view, with optional artist /
  // folder filter. Folder filter wins when both are set (the folder
  // restriction is the more specific one, since clicking a folder card
  // happens *after* artist selection).
  const groupedAlbums = useMemo(() => {
    if (allAlbums.length === 0) return new Map<string, Album[]>()
    let filtered = allAlbums
    if (filterFolder) {
      const allowed = new Set(filterFolder.albumIds)
      filtered = filtered.filter((a) => allowed.has(a.id))
    } else if (filterArtist !== null) {
      filtered = filtered.filter(
        (a) => (a.artist || '').trim() === filterArtist
      )
    }
    return groupAlbumsByLetter(filtered)
  }, [allAlbums, filterArtist, filterFolder])

  // Memoize artist groups for the Album-Artists view (always over the full
  // album set — filtering by artist there would just leave one card).
  const artistGroups = useMemo(() => groupAlbumsByArtist(allAlbums), [allAlbums])

  // Letter-bucket the artist groups + folder list for their letter-anchored
  // grids. (Album bucketing is already in groupedAlbums above.)
  const groupedArtists = useMemo(
    () => groupByFirstLetter(artistGroups, (g) => g.name),
    [artistGroups]
  )
  const groupedFolders = useMemo(
    () => groupByFirstLetter(topLevelFolders, (f) => f.name),
    [topLevelFolders]
  )

  // Letters available per view drives the alphabet-nav chips.
  const albumViewLetters = availableLetters
  const artistViewLetters = useMemo(
    () => Array.from(groupedArtists.keys()),
    [groupedArtists]
  )
  const folderViewLetters = useMemo(
    () => Array.from(groupedFolders.keys()),
    [groupedFolders]
  )

  // Switching the view pill replaces the current entry (a tab switch
  // shouldn't add a back-button stop) and keeps any active filter so it
  // reappears on return to the Albums view, matching prior behaviour.
  const handleViewChange = useCallback(
    (mode: ViewMode) => {
      setSearchParams(
        (prev) => {
          const next = new URLSearchParams(prev)
          next.set('view', mode)
          return next
        },
        { replace: true }
      )
    },
    [setSearchParams]
  )

  // Drilling into an artist/folder card is a real navigation step (push) so
  // browser-back returns from the filtered grid to the card view.
  const handleArtistCardClick = useCallback(
    (artist: string) => {
      setSearchParams((prev) => {
        const next = new URLSearchParams(prev)
        next.set('view', 'albums')
        next.set('artist', artist === UNKNOWN_ARTIST_LABEL ? '' : artist)
        next.delete('folder')
        return next
      })
    },
    [setSearchParams]
  )

  const handleFolderCardClick = useCallback(
    (folder: TopLevelFolder) => {
      setSearchParams((prev) => {
        const next = new URLSearchParams(prev)
        next.set('view', 'albums')
        next.set('folder', folder.name)
        next.delete('artist')
        return next
      })
    },
    [setSearchParams]
  )

  const handleClearArtistFilter = useCallback(() => {
    setSearchParams(
      (prev) => {
        const next = new URLSearchParams(prev)
        next.delete('artist')
        return next
      },
      { replace: true }
    )
  }, [setSearchParams])

  const handleClearFolderFilter = useCallback(() => {
    setSearchParams(
      (prev) => {
        const next = new URLSearchParams(prev)
        next.delete('folder')
        return next
      },
      { replace: true }
    )
  }, [setSearchParams])

  // Create callback to set anchor refs
  const createAnchorRef = useCallback((letter: string) => {
    return (element: HTMLDivElement | null) => {
      if (element) {
        anchorRefs.current.set(letter, element)
      } else {
        anchorRefs.current.delete(letter)
      }
    }
  }, [])

  // Handle letter selection - scroll to the letter anchor
  const handleLetterSelect = useCallback((letter: string) => {
    const anchor = anchorRefs.current.get(letter)
    if (anchor) {
      anchor.scrollIntoView({ behavior: 'smooth', block: 'start' })
    }
  }, [])

  // Set up Intersection Observer for current letter tracking
  useEffect(() => {
    // Clean up previous observer
    if (observerRef.current) {
      observerRef.current.disconnect()
    }

    // Create new observer
    const observer = new IntersectionObserver(
      (entries) => {
        const now = Date.now()
        // Throttle updates
        if (now - lastUpdateRef.current < THROTTLE_MS) {
          return
        }

        // Find the topmost visible letter section
        const visibleEntries = entries
          .filter((entry) => entry.isIntersecting)
          .sort((a, b) => a.boundingClientRect.top - b.boundingClientRect.top)

        if (visibleEntries.length > 0) {
          const letter = visibleEntries[0].target.getAttribute('data-letter')
          if (letter) {
            lastUpdateRef.current = now
            setCurrentLetter(letter)
          }
        }
      },
      {
        // Observe intersections at the top of the viewport
        rootMargin: '-80px 0px -80% 0px',
        threshold: 0,
      }
    )

    observerRef.current = observer

    // Observe all anchor elements
    anchorRefs.current.forEach((element) => {
      observer.observe(element)
    })

    return () => {
      observer.disconnect()
    }
    // Re-observe whenever the visible bucketing changes, including a view
    // switch — anchors mount/unmount per view, so each view needs its own
    // pass through the observer.
  }, [groupedAlbums, groupedArtists, groupedFolders, viewMode])

  // Re-observe anchors when they change
  useEffect(() => {
    if (!observerRef.current) return

    const observer = observerRef.current
    anchorRefs.current.forEach((element) => {
      observer.observe(element)
    })
  }, [groupedAlbums, groupedArtists, groupedFolders, viewMode])

  const isLoading = albumsLoading || lettersLoading

  // Loading state
  if (isLoading) {
    return <LoadingSkeleton />
  }

  // Error state
  if (albumsError) {
    return (
      <div className="text-center py-12 border rounded-lg bg-muted/20">
        <Disc3 className="h-12 w-12 mx-auto text-destructive" />
        <h3 className="mt-4 text-lg font-medium">Error Loading Albums</h3>
        <p className="mt-2 text-muted-foreground">
          {albumsError instanceof Error ? albumsError.message : 'An unknown error occurred'}
        </p>
        <Button asChild className="mt-4">
          <Link to="/libraries">Back to Libraries</Link>
        </Button>
      </div>
    )
  }

  // Empty state
  if (allAlbums.length === 0) {
    return (
      <div className="text-center py-12 border rounded-lg bg-muted/20">
        <Disc3 className="h-12 w-12 mx-auto text-muted-foreground" />
        <h3 className="mt-4 text-lg font-medium">No Albums Found</h3>
        <p className="mt-2 text-muted-foreground">
          This library doesn't have any albums yet.
        </p>
      </div>
    )
  }

  // The Albums grid keeps right padding for the desktop alphabet nav; the
  // other two views also show the nav, so they get the same padding for
  // visual consistency.
  const gridClasses =
    'grid grid-cols-2 sm:grid-cols-3 sm:pr-8 md:grid-cols-4 lg:grid-cols-5 xl:grid-cols-6 gap-4'

  // The Albums view's alphabet nav makes no sense once a single artist or
  // folder filter has collapsed the set to one or two letters.
  const albumsViewHasFilter = filterArtist !== null || filterFolder !== null

  let body: React.ReactNode
  let navLetters: string[]
  if (viewMode === 'albums') {
    body = (
      <div className={gridClasses}>
        {Array.from(groupedAlbums.entries()).map(([letter, letterAlbums]) => (
          <Fragment key={letter}>
            <LetterAnchor letter={letter} anchorRef={createAnchorRef(letter)} />
            {letterAlbums.map((album) => (
              <AlbumCard
                key={album.id}
                album={album}
                slug={library.slug}
                fromUrl={fromUrl}
              />
            ))}
          </Fragment>
        ))}
      </div>
    )
    navLetters = albumsViewHasFilter ? [] : albumViewLetters
  } else if (viewMode === 'artists') {
    body = (
      <div className={gridClasses}>
        {Array.from(groupedArtists.entries()).map(([letter, letterArtists]) => (
          <Fragment key={letter}>
            <LetterAnchor letter={letter} anchorRef={createAnchorRef(letter)} />
            {letterArtists.map((group) => (
              <ArtistCard
                key={group.sortKey}
                group={group}
                slug={library.slug}
                onClick={handleArtistCardClick}
              />
            ))}
          </Fragment>
        ))}
      </div>
    )
    navLetters = artistViewLetters
  } else {
    body = topLevelFolders.length === 0 ? (
      <div className="text-center py-12 border rounded-lg bg-muted/20">
        <FolderIcon className="h-12 w-12 mx-auto text-muted-foreground" />
        <h3 className="mt-4 text-lg font-medium">No folders</h3>
        <p className="mt-2 text-muted-foreground">
          This library has no top-level folders yet — try importing some
          albums first.
        </p>
      </div>
    ) : (
      <div className={gridClasses}>
        {Array.from(groupedFolders.entries()).map(([letter, letterFolders]) => (
          <Fragment key={letter}>
            <LetterAnchor letter={letter} anchorRef={createAnchorRef(letter)} />
            {letterFolders.map((folder) => (
              <FolderCard
                key={folder.path}
                folder={folder}
                slug={library.slug}
                onClick={handleFolderCardClick}
              />
            ))}
          </Fragment>
        ))}
      </div>
    )
    navLetters = folderViewLetters
  }

  return (
    <div className="space-y-4">
      <ViewModePills
        mode={viewMode}
        onChange={handleViewChange}
        activeArtist={viewMode === 'albums' ? filterArtist : null}
        activeFolder={
          viewMode === 'albums' && filterFolder ? filterFolder.name : null
        }
        onClearArtistFilter={handleClearArtistFilter}
        onClearFolderFilter={handleClearFolderFilter}
      />

      {body}

      {navLetters.length > 0 && (
        <AlphabetNav
          availableLetters={navLetters}
          currentLetter={currentLetter}
          onLetterSelect={handleLetterSelect}
        />
      )}
    </div>
  )
}
