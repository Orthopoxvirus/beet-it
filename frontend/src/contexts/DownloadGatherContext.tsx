import {
  createContext,
  useContext,
  useState,
  useEffect,
  useCallback,
  useMemo,
  type ReactNode,
} from 'react'

const GATHER_STORAGE_KEY = 'download-gather'

export type GatherKind = 'album' | 'track'

export interface GatheredAlbum {
  id: number
  title: string
  artist: string
  /** Total on-disk size in bytes, or null while unknown. */
  sizeBytes: number | null
}

export interface GatheredTrack {
  id: number
  title: string
  artist: string
}

interface GatherEntry extends GatheredAlbum {
  /** Missing on entries persisted before tracks existed — treated as 'album'. */
  kind?: GatherKind
}

interface GatherState {
  /** The library these items belong to. A gather is single-library so it can
   *  pack into one zip and POST to that library's download endpoint. */
  slug: string | null
  items: GatherEntry[]
}

interface DownloadGatherContextValue {
  slug: string | null
  items: GatherEntry[]
  count: number
  albumCount: number
  trackCount: number
  /** Sum of known album sizes (albums with unknown size contribute 0). */
  totalSize: number
  /** The most recently added item, or null. */
  lastAdded: GatherEntry | null
  isGathered: (albumId: number) => boolean
  isTrackGathered: (trackId: number) => boolean
  /** Add an album for `slug`. Adding from a different library starts fresh. */
  addAlbum: (slug: string, album: GatheredAlbum) => void
  /** Add one or many titles for `slug` (select-all uses the bulk form). */
  addTracks: (slug: string, tracks: GatheredTrack[]) => void
  removeAlbum: (albumId: number) => void
  removeTrack: (trackId: number) => void
  clear: () => void
}

const DownloadGatherContext = createContext<DownloadGatherContextValue | undefined>(undefined)

function kindOf(entry: GatherEntry): GatherKind {
  return entry.kind ?? 'album'
}

function loadInitial(): GatherState {
  try {
    const raw = localStorage.getItem(GATHER_STORAGE_KEY)
    if (raw) {
      const parsed = JSON.parse(raw) as GatherState
      if (parsed && Array.isArray(parsed.items)) {
        return { slug: parsed.slug ?? null, items: parsed.items }
      }
    }
  } catch {
    // Corrupt/legacy value — start clean.
  }
  return { slug: null, items: [] }
}

export function DownloadGatherProvider({ children }: { children: ReactNode }) {
  const [state, setState] = useState<GatherState>(loadInitial)

  useEffect(() => {
    localStorage.setItem(GATHER_STORAGE_KEY, JSON.stringify(state))
  }, [state])

  const addAlbum = useCallback((slug: string, album: GatheredAlbum) => {
    setState((prev) => {
      // Switching libraries replaces the gather — a zip is single-library.
      const base = prev.slug && prev.slug !== slug ? [] : prev.items
      const idx = base.findIndex((a) => kindOf(a) === 'album' && a.id === album.id)
      if (idx >= 0) {
        // Upsert in place — lets a later size lookup fill in an album added
        // optimistically with an unknown size, without changing its position.
        const items = base.slice()
        items[idx] = { ...items[idx], ...album }
        return { slug, items }
      }
      return { slug, items: [...base, { ...album, kind: 'album' as const }] }
    })
  }, [])

  const addTracks = useCallback((slug: string, tracks: GatheredTrack[]) => {
    if (tracks.length === 0) return
    setState((prev) => {
      const base = prev.slug && prev.slug !== slug ? [] : prev.items
      const known = new Set(
        base.filter((e) => kindOf(e) === 'track').map((e) => e.id)
      )
      const fresh = tracks
        .filter((t) => !known.has(t.id))
        .map((t) => ({ ...t, sizeBytes: null, kind: 'track' as const }))
      if (fresh.length === 0 && base === prev.items) return prev
      return { slug, items: [...base, ...fresh] }
    })
  }, [])

  const removeEntry = useCallback((kind: GatherKind, id: number) => {
    setState((prev) => {
      const items = prev.items.filter((e) => !(kindOf(e) === kind && e.id === id))
      return { slug: items.length ? prev.slug : null, items }
    })
  }, [])

  const removeAlbum = useCallback(
    (albumId: number) => removeEntry('album', albumId),
    [removeEntry]
  )
  const removeTrack = useCallback(
    (trackId: number) => removeEntry('track', trackId),
    [removeEntry]
  )

  const clear = useCallback(() => setState({ slug: null, items: [] }), [])

  const value = useMemo<DownloadGatherContextValue>(() => {
    const items = state.items
    const albums = items.filter((e) => kindOf(e) === 'album')
    const tracks = items.filter((e) => kindOf(e) === 'track')
    return {
      slug: state.slug,
      items,
      count: items.length,
      albumCount: albums.length,
      trackCount: tracks.length,
      totalSize: items.reduce((sum, a) => sum + (a.sizeBytes ?? 0), 0),
      lastAdded: items.length ? items[items.length - 1] : null,
      isGathered: (albumId: number) => albums.some((a) => a.id === albumId),
      isTrackGathered: (trackId: number) => tracks.some((t) => t.id === trackId),
      addAlbum,
      addTracks,
      removeAlbum,
      removeTrack,
      clear,
    }
  }, [state, addAlbum, addTracks, removeAlbum, removeTrack, clear])

  return (
    <DownloadGatherContext.Provider value={value}>
      {children}
    </DownloadGatherContext.Provider>
  )
}

export function useDownloadGather() {
  const context = useContext(DownloadGatherContext)
  if (context === undefined) {
    throw new Error('useDownloadGather must be used within a DownloadGatherProvider')
  }
  return context
}

export { kindOf as gatherEntryKind }
