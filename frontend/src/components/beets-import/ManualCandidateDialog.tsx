import { useState, useCallback, useEffect, useRef } from 'react'
import { Loader2, AlertCircle, Link2, ExternalLink, Search, Check } from 'lucide-react'
import {
  Dialog,
  DialogContent,
  DialogDescription,
  DialogFooter,
  DialogHeader,
  DialogTitle,
} from '@/components/ui/dialog'
import { Button } from '@/components/ui/button'
import { Input } from '@/components/ui/input'
import { Label } from '@/components/ui/label'
import { Badge } from '@/components/ui/badge'
import { Tabs, TabsList, TabsTrigger, TabsContent } from '@/components/ui/tabs'
import {
  Tooltip,
  TooltipContent,
  TooltipProvider,
  TooltipTrigger,
} from '@/components/ui/tooltip'
import { searchCandidates } from '@/api/beets-import'
import { detectProvider, isValidLink } from '@/types/beets-import'
import type {
  ManualCandidateProvider,
  SearchProviderGroup,
} from '@/types/beets-import'

// ============================================================================
// Types
// ============================================================================

interface ManualCandidateDialogProps {
  /** Whether the dialog is open */
  open: boolean
  /** Callback when dialog should close */
  onOpenChange: (open: boolean) => void
  /** Library slug — required to run multi-provider search */
  librarySlug: string
  /**
   * Identity of the album being matched (e.g. its path). Search results are
   * kept across close/reopen for the same album and dropped when it changes.
   */
  albumKey?: string | null
  /**
   * Seeds the search field when the dialog first mounts and whenever the album
   * changes (e.g. `"Artist - Album"` from the candidate details). The user's
   * own edits survive close/reopen for the same album — only an album switch
   * re-seeds.
   */
  initialQuery?: string
  /**
   * Structured artist/album for the seeded search. When present, the first
   * (unedited) search sends them as field queries so each provider matches on
   * the right fields instead of a loose free-text blob (issue #69). Cleared the
   * moment the user edits the search box — a hand-typed term is treated as free
   * text.
   */
  initialArtist?: string | null
  initialAlbum?: string | null
  /**
   * Track count of the local folder being matched. Forwarded to the search so
   * hits with the same track count rank first, and used to flag matching rows
   * (issue #112).
   */
  expectedTracks?: number | null
  /** Callback when a link is submitted for resolution (paste or search pick) */
  onSubmit: (link: string) => void
  /** Whether resolution is in progress */
  isLoading?: boolean
  /** Error message from resolution failure */
  error?: string | null
}

// ============================================================================
// Provider Info
// ============================================================================

const PROVIDER_INFO: Record<ManualCandidateProvider, { name: string; example: string }> = {
  deezer: {
    name: 'Deezer',
    example: 'https://www.deezer.com/album/12345',
  },
  spotify: {
    name: 'Spotify',
    example: 'https://open.spotify.com/album/...',
  },
  discogs: {
    name: 'Discogs',
    example: 'https://www.discogs.com/release/12345',
  },
  musicbrainz: {
    name: 'MusicBrainz',
    example: 'UUID or https://musicbrainz.org/release/...',
  },
}

/** Results requested per provider per page. */
const PER_PAGE = 5

/** Source filter: a single provider, or all of them. */
type SourceFilter = 'all' | ManualCandidateProvider

/**
 * Search state owned by the dialog component (not the tab): Radix unmounts
 * the dialog content on close, so anything kept inside SearchTab would be
 * lost between close and reopen (issue #53).
 */
interface SearchState {
  /** Live input value */
  query: string
  /** The term that produced `groups` — load-more paginates this, not the live input */
  submittedQuery: string
  /**
   * Live structured terms seeded from the album. Sent as field queries on the
   * next search; nulled the instant the user edits the input (free-text mode).
   */
  artist: string | null
  album: string | null
  /**
   * Structured terms that produced `groups`. load-more must reuse these (not the
   * live ones) so paginating a seeded search keeps the same field query.
   */
  submittedArtist: string | null
  submittedAlbum: string | null
  groups: SearchProviderGroup[] | null
  /** Last fetched page per provider (pagination is per provider) */
  pages: Record<string, number>
  sourceFilter: SourceFilter
}

const INITIAL_SEARCH_STATE: SearchState = {
  query: '',
  submittedQuery: '',
  artist: null,
  album: null,
  submittedArtist: null,
  submittedAlbum: null,
  groups: null,
  pages: {},
  sourceFilter: 'all',
}

// ============================================================================
// Search result merging (pagination append + dedup)
// ============================================================================

/**
 * Merge a freshly-fetched page into the accumulated groups: append new results
 * per provider, deduping by sourceId, and adopt the latest availability/hasMore.
 * `next` may be partial (per-provider load-more fetches a single provider);
 * groups absent from it pass through unchanged.
 */
function mergeGroups(
  prev: SearchProviderGroup[],
  next: SearchProviderGroup[]
): SearchProviderGroup[] {
  return prev.map((pg) => {
    const ng = next.find((n) => n.provider === pg.provider)
    if (!ng) return pg
    const seen = new Set(pg.results.map((r) => r.sourceId))
    return {
      ...ng,
      results: [...pg.results, ...ng.results.filter((r) => !seen.has(r.sourceId))],
    }
  })
}

// ============================================================================
// Search result row
// ============================================================================

interface SearchResultRowProps {
  provider: ManualCandidateProvider
  title: string
  artist: string
  year: number | null
  trackCount: number | null
  /** True when this hit's track count equals the local folder's (issue #112) */
  trackCountMatches: boolean
  externalUrl: string
  coverUrl: string | null
  disabled: boolean
  isResolving: boolean
  onUse: () => void
}

function SearchResultRow({
  provider,
  title,
  artist,
  year,
  trackCount,
  trackCountMatches,
  externalUrl,
  coverUrl,
  disabled,
  isResolving,
  onUse,
}: SearchResultRowProps) {
  const meta = [artist, year ? String(year) : null, trackCount ? `${trackCount} tracks` : null]
    .filter(Boolean)
    .join(' · ')

  return (
    <div className="flex items-center gap-3 rounded-md border p-2">
      {coverUrl ? (
        <img
          src={coverUrl}
          alt=""
          className="h-10 w-10 flex-shrink-0 rounded object-cover"
          loading="lazy"
        />
      ) : (
        <div className="h-10 w-10 flex-shrink-0 rounded bg-muted" />
      )}

      <div className="min-w-0 flex-1">
        <div className="flex items-center gap-1.5">
          <p className="truncate text-sm font-medium">{title || 'Untitled'}</p>
          {trackCountMatches && (
            <Badge
              variant="secondary"
              className="flex-shrink-0 gap-0.5 px-1.5 py-0 text-[10px]"
              title="Track count matches the local folder"
            >
              <Check className="h-3 w-3" />
              tracks
            </Badge>
          )}
        </div>
        {meta && <p className="truncate text-xs text-muted-foreground">{meta}</p>}
      </div>

      <a
        href={externalUrl}
        target="_blank"
        rel="noopener noreferrer"
        className="flex-shrink-0 rounded p-1.5 text-muted-foreground hover:bg-muted hover:text-foreground"
        aria-label={`Open ${PROVIDER_INFO[provider].name} page in a new tab`}
        title="Open in new tab"
      >
        <ExternalLink className="h-4 w-4" />
      </a>

      <Button
        type="button"
        size="sm"
        variant="secondary"
        onClick={onUse}
        disabled={disabled}
        className="flex-shrink-0"
      >
        {isResolving ? <Loader2 className="h-4 w-4 animate-spin" /> : 'Use'}
      </Button>
    </div>
  )
}

// ============================================================================
// Search tab
// ============================================================================

interface SearchTabProps {
  librarySlug: string
  /** Local folder's track count; matching hits rank first and get flagged (issue #112) */
  expectedTracks?: number | null
  /** Search state lifted to the dialog so it survives close/reopen (issue #53) */
  state: SearchState
  onStateChange: React.Dispatch<React.SetStateAction<SearchState>>
  onUse: (externalUrl: string) => void
  /** External URL currently being resolved (null = none) */
  resolvingUrl: string | null
  /** Whether a resolution is in progress (disables all Use buttons) */
  isResolving: boolean
  /** Resolution error bubbled up from the parent */
  resolveError: string | null
}

function SearchTab({
  librarySlug,
  expectedTracks,
  state,
  onStateChange,
  onUse,
  resolvingUrl,
  isResolving,
  resolveError,
}: SearchTabProps) {
  const { query, submittedQuery, artist, album, submittedArtist, submittedAlbum, groups, pages, sourceFilter } = state
  // Transient request state stays local: a spinner or error from a fetch that
  // was abandoned by closing the dialog should not reappear on reopen.
  const [isSearching, setIsSearching] = useState(false)
  const [loadingProvider, setLoadingProvider] = useState<ManualCandidateProvider | null>(null)
  const [searchError, setSearchError] = useState<string | null>(null)

  const runSearch = useCallback(
    async (term: string) => {
      if (!term) return

      setIsSearching(true)
      setSearchError(null)
      // Snapshot the structured terms that are about to be submitted so
      // load-more paginates the same field query, even if the user edits the
      // box afterwards.
      const structured = { artist, album }
      onStateChange((prev) => ({
        ...prev,
        submittedQuery: term,
        submittedArtist: prev.artist,
        submittedAlbum: prev.album,
      }))
      try {
        const resp = await searchCandidates(
          librarySlug,
          term,
          1,
          PER_PAGE,
          undefined,
          structured,
          expectedTracks
        )
        onStateChange((prev) => ({
          ...prev,
          groups: resp.providers,
          pages: Object.fromEntries(resp.providers.map((g) => [g.provider, 1])),
          // The filtered source can disappear between searches (config change);
          // fall back to All rather than showing nothing.
          sourceFilter:
            prev.sourceFilter !== 'all' &&
            !resp.providers.some((g) => g.provider === prev.sourceFilter && g.available)
              ? 'all'
              : prev.sourceFilter,
        }))
      } catch (e) {
        setSearchError(e instanceof Error ? e.message : 'Search failed')
      } finally {
        setIsSearching(false)
      }
    },
    [librarySlug, onStateChange, artist, album, expectedTracks]
  )

  const loadMore = useCallback(
    async (provider: ManualCandidateProvider) => {
      const nextPage = (pages[provider] ?? 1) + 1
      setLoadingProvider(provider)
      setSearchError(null)
      try {
        const resp = await searchCandidates(
          librarySlug,
          submittedQuery,
          nextPage,
          PER_PAGE,
          [provider],
          { artist: submittedArtist, album: submittedAlbum },
          expectedTracks
        )
        onStateChange((prev) => ({
          ...prev,
          pages: { ...prev.pages, [provider]: nextPage },
          groups: prev.groups ? mergeGroups(prev.groups, resp.providers) : resp.providers,
        }))
      } catch (e) {
        setSearchError(e instanceof Error ? e.message : 'Search failed')
      } finally {
        setLoadingProvider(null)
      }
    },
    [librarySlug, submittedQuery, submittedArtist, submittedAlbum, pages, onStateChange, expectedTracks]
  )

  const handleSubmit = useCallback(
    (e: React.FormEvent) => {
      e.preventDefault()
      void runSearch(query.trim())
    },
    [runSearch, query]
  )

  const available = groups?.filter((g) => g.available) ?? []
  const unavailable = groups?.filter((g) => !g.available) ?? []
  const visible = sourceFilter === 'all' ? available : available.filter((g) => g.provider === sourceFilter)
  const totalResults = visible.reduce((n, g) => n + g.results.length, 0)
  const hasSearched = groups !== null
  const isBusy = isSearching || loadingProvider !== null

  return (
    // flex-1, not h-full: a percentage height doesn't resolve against the
    // flexed TabsContent, so h-full collapsed to content height and the rows
    // spilled out of the max-h'd dialog (issue #53).
    <div className="flex min-h-0 flex-1 flex-col gap-4">
      <form onSubmit={handleSubmit} className="flex flex-shrink-0 gap-2">
        <Input
          type="text"
          placeholder="Search albums, artists…"
          value={query}
          onChange={(e) => {
            const value = e.target.value
            // A hand-typed term is free text: drop the seeded structured fields
            // so the next search isn't scoped to the old artist/album.
            onStateChange((prev) => ({ ...prev, query: value, artist: null, album: null }))
          }}
          aria-label="Search term"
          autoComplete="off"
          autoFocus
        />
        <Button type="submit" disabled={isBusy || !query.trim()}>
          {isSearching ? (
            <Loader2 className="h-4 w-4 animate-spin" />
          ) : (
            <Search className="h-4 w-4" />
          )}
          <span className="ml-2">Search</span>
        </Button>
      </form>

      {/* Source filter — pick which provider's results to show */}
      {hasSearched && available.length > 0 && (
        <div
          className="flex flex-shrink-0 flex-wrap gap-1.5"
          role="group"
          aria-label="Filter by source"
        >
          <Button
            type="button"
            size="sm"
            variant={sourceFilter === 'all' ? 'default' : 'outline'}
            onClick={() => onStateChange((prev) => ({ ...prev, sourceFilter: 'all' }))}
          >
            All
          </Button>
          {available.map((g) => (
            <Button
              key={g.provider}
              type="button"
              size="sm"
              variant={sourceFilter === g.provider ? 'default' : 'outline'}
              onClick={() => onStateChange((prev) => ({ ...prev, sourceFilter: g.provider }))}
            >
              {PROVIDER_INFO[g.provider].name}
              {g.results.length > 0 ? ` (${g.results.length})` : ''}
            </Button>
          ))}
        </div>
      )}

      {/* Unavailable providers — greyed badges explaining why on hover */}
      {unavailable.length > 0 && (
        <TooltipProvider>
          <div className="flex flex-shrink-0 flex-wrap gap-2">
            {unavailable.map((g) => (
              <Tooltip key={g.provider}>
                <TooltipTrigger asChild>
                  {/* span wrapper: TooltipTrigger asChild injects a ref, and Badge is not a forwardRef component */}
                  <span className="inline-flex cursor-help">
                    <Badge variant="outline" className="opacity-50">
                      {PROVIDER_INFO[g.provider].name}
                    </Badge>
                  </span>
                </TooltipTrigger>
                <TooltipContent>
                  <p className="max-w-[260px] text-xs">{g.reason}</p>
                </TooltipContent>
              </Tooltip>
            ))}
          </div>
        </TooltipProvider>
      )}

      {/* Resolution error (from picking a result) */}
      {resolveError && (
        <div className="flex-shrink-0 rounded-md border border-destructive/20 bg-destructive/10 p-3">
          <p className="flex items-start gap-2 text-sm text-destructive">
            <AlertCircle className="mt-0.5 h-4 w-4 flex-shrink-0" />
            {resolveError}
          </p>
        </div>
      )}

      {/* Search error */}
      {searchError && (
        <p className="flex flex-shrink-0 items-center gap-1 text-sm text-destructive">
          <AlertCircle className="h-3 w-3 flex-shrink-0" />
          {searchError}
        </p>
      )}

      {/* Scrollable results region — caps the dialog height (issue #51) */}
      <div className="min-h-0 flex-1 space-y-4 overflow-y-auto pr-1">
        {/* Results grouped by provider */}
        {visible.map((group) => {
          if (group.results.length === 0 && !group.reason) return null
          return (
            <div key={group.provider} className="space-y-2">
              <div className="flex items-center gap-2">
                <h4 className="text-sm font-medium">{PROVIDER_INFO[group.provider].name}</h4>
                {group.results.length > 0 && (
                  <Badge variant="secondary">{group.results.length}</Badge>
                )}
              </div>
              {group.reason && (
                <p className="text-xs text-muted-foreground">{group.reason}</p>
              )}
              {group.results.map((item) => (
                <SearchResultRow
                  key={`${item.provider}-${item.sourceId}`}
                  provider={item.provider}
                  title={item.title}
                  artist={item.artist}
                  year={item.year}
                  trackCount={item.trackCount}
                  trackCountMatches={
                    expectedTracks != null && item.trackCount === expectedTracks
                  }
                  externalUrl={item.externalUrl}
                  coverUrl={item.coverUrl}
                  disabled={isResolving}
                  isResolving={isResolving && resolvingUrl === item.externalUrl}
                  onUse={() => onUse(item.externalUrl)}
                />
              ))}
              {/* Per-provider pagination — fetches only this provider's next page */}
              {group.hasMore && (
                <Button
                  type="button"
                  variant="outline"
                  size="sm"
                  className="w-full"
                  onClick={() => void loadMore(group.provider)}
                  disabled={isBusy}
                >
                  {loadingProvider === group.provider ? (
                    <>
                      <Loader2 className="mr-2 h-4 w-4 animate-spin" />
                      Loading…
                    </>
                  ) : (
                    `Load more from ${PROVIDER_INFO[group.provider].name}`
                  )}
                </Button>
              )}
            </div>
          )
        })}

        {/* Empty state — suppressed when a provider reported an error of its own */}
        {hasSearched &&
          !isSearching &&
          totalResults === 0 &&
          !searchError &&
          !visible.some((g) => g.reason) && (
            <p className="py-4 text-center text-sm text-muted-foreground">
              No results found. Try a different search term.
            </p>
          )}
      </div>
    </div>
  )
}

// ============================================================================
// Link tab (paste a URL / MusicBrainz ID)
// ============================================================================

interface LinkTabProps {
  onSubmit: (link: string) => void
  isLoading: boolean
  error: string | null
}

function LinkTab({ onSubmit, isLoading, error }: LinkTabProps) {
  const [link, setLink] = useState('')
  const [validationError, setValidationError] = useState<string | null>(null)
  const [detectedProvider, setDetectedProvider] = useState<ManualCandidateProvider | null>(null)

  const handleLinkChange = useCallback((value: string) => {
    setLink(value)
    setValidationError(null)
    if (!value.trim()) {
      setDetectedProvider(null)
      return
    }
    setDetectedProvider(detectProvider(value))
  }, [])

  const handleSubmit = useCallback(
    (e: React.FormEvent) => {
      e.preventDefault()
      const trimmedLink = link.trim()
      if (!trimmedLink) {
        setValidationError('Please enter a link or MusicBrainz ID')
        return
      }
      if (!isValidLink(trimmedLink)) {
        setValidationError(
          'Link format not recognized. Please use a valid URL from Deezer, Spotify, Discogs, MusicBrainz, or a MusicBrainz release UUID.'
        )
        return
      }
      onSubmit(trimmedLink)
    },
    [link, onSubmit]
  )

  const isValid = link.trim() && isValidLink(link)

  return (
    <form onSubmit={handleSubmit} className="space-y-4">
      <div className="space-y-2">
        <Label htmlFor="link">Link or MusicBrainz ID</Label>
        <Input
          id="link"
          type="text"
          placeholder="Paste link or MusicBrainz release UUID..."
          value={link}
          onChange={(e) => handleLinkChange(e.target.value)}
          disabled={isLoading}
          autoComplete="off"
          autoFocus
        />

        {detectedProvider && !validationError && (
          <p className="text-sm text-green-600 dark:text-green-400 flex items-center gap-1">
            <ExternalLink className="h-3 w-3" />
            Detected: {PROVIDER_INFO[detectedProvider].name}
          </p>
        )}

        {validationError && (
          <p className="text-sm text-destructive flex items-center gap-1">
            <AlertCircle className="h-3 w-3 flex-shrink-0" />
            {validationError}
          </p>
        )}

        {error && (
          <div className="p-3 rounded-md bg-destructive/10 border border-destructive/20">
            <p className="text-sm text-destructive flex items-start gap-2">
              <AlertCircle className="h-4 w-4 flex-shrink-0 mt-0.5" />
              {error}
            </p>
          </div>
        )}
      </div>

      <div className="rounded-md bg-muted/50 p-3 text-sm">
        <p className="font-medium mb-2">Supported providers:</p>
        <ul className="space-y-1 text-muted-foreground">
          {Object.entries(PROVIDER_INFO).map(([key, info]) => (
            <li key={key} className="flex items-start gap-2 min-w-0">
              <span className="font-medium text-foreground shrink-0 min-w-[90px]">
                {info.name}:
              </span>
              <span className="text-xs font-mono break-all min-w-0">{info.example}</span>
            </li>
          ))}
        </ul>
      </div>

      <DialogFooter>
        <Button type="submit" disabled={isLoading || !isValid}>
          {isLoading ? (
            <>
              <Loader2 className="mr-2 h-4 w-4 animate-spin" />
              Resolving...
            </>
          ) : (
            'Add Candidate'
          )}
        </Button>
      </DialogFooter>
    </form>
  )
}

// ============================================================================
// Component
// ============================================================================

/**
 * Dialog for adding a manual candidate match for an album.
 *
 * Two modes:
 *  - **Search** (default): query MusicBrainz, Spotify, Deezer, and Discogs at
 *    once and pick a result, or open one in a new tab to inspect.
 *  - **Paste link**: paste an external URL or MusicBrainz ID directly.
 *
 * Both modes funnel through the same `onSubmit(link)` resolution path.
 */
export default function ManualCandidateDialog({
  open,
  onOpenChange,
  librarySlug,
  albumKey = null,
  initialQuery = '',
  initialArtist = null,
  initialAlbum = null,
  expectedTracks = null,
  onSubmit,
  isLoading = false,
  error = null,
}: ManualCandidateDialogProps) {
  const [mode, setMode] = useState<'search' | 'link'>('search')
  const [resolvingUrl, setResolvingUrl] = useState<string | null>(null)
  // Lives here, not in SearchTab: the dialog content unmounts on close, this
  // component doesn't — so results survive close/reopen for the same album.
  const [searchState, setSearchState] = useState<SearchState>(() => ({
    ...INITIAL_SEARCH_STATE,
    query: initialQuery,
    artist: initialArtist,
    album: initialAlbum,
  }))

  // Cached results belong to one album in one library — drop them when either changes.
  const cacheKey = `${librarySlug} ${albumKey ?? ''}`
  const cacheKeyRef = useRef(cacheKey)
  // Read inside the album-change effect so re-seeding picks up the latest query
  // without making it an effect dependency: keying the reset on the album (not
  // the query) lets the user's own edits survive close/reopen for the same album.
  const initialQueryRef = useRef(initialQuery)
  initialQueryRef.current = initialQuery
  const initialArtistRef = useRef(initialArtist)
  initialArtistRef.current = initialArtist
  const initialAlbumRef = useRef(initialAlbum)
  initialAlbumRef.current = initialAlbum
  useEffect(() => {
    cacheKeyRef.current = cacheKey
    setSearchState({
      ...INITIAL_SEARCH_STATE,
      query: initialQueryRef.current,
      artist: initialArtistRef.current,
      album: initialAlbumRef.current,
    })
  }, [cacheKey])

  // A search response can arrive after the dialog was closed and the album
  // switched; without this guard it would populate the new album's cache
  // with the old album's results.
  const updateSearchState = useCallback<React.Dispatch<React.SetStateAction<SearchState>>>(
    (action) => {
      if (cacheKeyRef.current !== cacheKey) return
      setSearchState(action)
    },
    [cacheKey]
  )

  // Reset transient state when the dialog closes (after the closing animation).
  useEffect(() => {
    if (!open) {
      const timeout = setTimeout(() => {
        setMode('search')
        setResolvingUrl(null)
      }, 150)
      return () => clearTimeout(timeout)
    }
  }, [open])

  // Clear the per-row spinner once a resolution attempt finishes.
  useEffect(() => {
    if (!isLoading) setResolvingUrl(null)
  }, [isLoading])

  const handleUseSearchResult = useCallback(
    (externalUrl: string) => {
      setResolvingUrl(externalUrl)
      onSubmit(externalUrl)
    },
    [onSubmit]
  )

  return (
    <Dialog open={open} onOpenChange={onOpenChange}>
      {/* flex column + max-h so long result lists scroll inside the dialog
          instead of growing it past the viewport (issue #51) */}
      <DialogContent className="flex max-h-[85vh] max-w-[calc(100vw-2rem)] flex-col sm:max-w-[560px]">
        <DialogHeader className="flex-shrink-0">
          <DialogTitle className="flex items-center gap-2">
            <Link2 className="h-5 w-5" />
            Add Manual Candidate
          </DialogTitle>
          <DialogDescription>
            Search the metadata providers enabled for this library, or paste a
            link from Deezer, Spotify, Discogs, or MusicBrainz.
          </DialogDescription>
        </DialogHeader>

        <Tabs
          value={mode}
          onValueChange={(v) => setMode(v as 'search' | 'link')}
          className="flex min-h-0 flex-1 flex-col"
        >
          <TabsList className="grid w-full flex-shrink-0 grid-cols-2">
            <TabsTrigger value="search">
              <Search className="mr-2 h-4 w-4" />
              Search
            </TabsTrigger>
            <TabsTrigger value="link">
              <Link2 className="mr-2 h-4 w-4" />
              Paste link
            </TabsTrigger>
          </TabsList>

          {/* flex column so SearchTab can size via flex-1 — TabsContent's
              flexed height is not definite, so a child h-full wouldn't resolve */}
          <TabsContent value="search" className="flex min-h-0 flex-1 flex-col">
            <SearchTab
              librarySlug={librarySlug}
              expectedTracks={expectedTracks}
              state={searchState}
              onStateChange={updateSearchState}
              onUse={handleUseSearchResult}
              resolvingUrl={resolvingUrl}
              isResolving={isLoading}
              resolveError={error}
            />
          </TabsContent>

          <TabsContent value="link" className="min-h-0 flex-1 overflow-y-auto">
            <LinkTab onSubmit={onSubmit} isLoading={isLoading} error={error} />
          </TabsContent>
        </Tabs>
      </DialogContent>
    </Dialog>
  )
}
