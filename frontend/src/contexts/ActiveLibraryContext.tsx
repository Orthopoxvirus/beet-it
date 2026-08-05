import {
  createContext,
  useContext,
  useState,
  useEffect,
  useCallback,
  useMemo,
  type ReactNode,
} from 'react'
import { useLibraries } from '@/hooks/useLibraries'
import { type Library } from '@/api/libraries'

const ACTIVE_LIBRARY_SLUG_KEY = 'active-library-slug'

interface ActiveLibraryContextValue {
  /** The currently active library, or null if none selected or loading */
  activeLibrary: Library | null
  /** Set the active library and persist to localStorage */
  setActiveLibrary: (library: Library) => void
  /** All available libraries */
  libraries: Library[]
  /** Whether libraries are still loading */
  isLoading: boolean
  /** Error from loading libraries */
  error: Error | null
}

const ActiveLibraryContext = createContext<ActiveLibraryContextValue | undefined>(undefined)

interface ActiveLibraryProviderProps {
  children: ReactNode
}

export function ActiveLibraryProvider({ children }: ActiveLibraryProviderProps) {
  const { data, isLoading, error } = useLibraries()
  const [activeLibrarySlug, setActiveLibrarySlug] = useState<string | null>(() => {
    return localStorage.getItem(ACTIVE_LIBRARY_SLUG_KEY)
  })

  const libraries = useMemo(() => data?.items || [], [data])

  // Find the active library from the slug
  const activeLibrary = useMemo(() => {
    if (!libraries.length) return null

    // Try to find library matching stored slug
    if (activeLibrarySlug) {
      const found = libraries.find((lib) => lib.slug === activeLibrarySlug)
      if (found) return found
    }

    // Fallback to first library if stored slug doesn't exist
    return libraries[0]
  }, [libraries, activeLibrarySlug])

  // Sync the fallback selection to localStorage
  useEffect(() => {
    if (activeLibrary && activeLibrary.slug !== activeLibrarySlug) {
      localStorage.setItem(ACTIVE_LIBRARY_SLUG_KEY, activeLibrary.slug)
      setActiveLibrarySlug(activeLibrary.slug)
    }
  }, [activeLibrary, activeLibrarySlug])

  const setActiveLibrary = useCallback((library: Library) => {
    localStorage.setItem(ACTIVE_LIBRARY_SLUG_KEY, library.slug)
    setActiveLibrarySlug(library.slug)
  }, [])

  const value = useMemo(
    () => ({
      activeLibrary,
      setActiveLibrary,
      libraries,
      isLoading,
      error: error as Error | null,
    }),
    [activeLibrary, setActiveLibrary, libraries, isLoading, error]
  )

  return (
    <ActiveLibraryContext.Provider value={value}>
      {children}
    </ActiveLibraryContext.Provider>
  )
}

export function useActiveLibrary() {
  const context = useContext(ActiveLibraryContext)
  if (context === undefined) {
    throw new Error('useActiveLibrary must be used within an ActiveLibraryProvider')
  }
  return context
}

/**
 * Sync the active library with a URL slug.
 * Call this in route components to update the context when the URL changes.
 */
export function useSyncActiveLibraryFromUrl(slug: string | undefined) {
  const { libraries, setActiveLibrary, activeLibrary } = useActiveLibrary()

  useEffect(() => {
    if (!slug || !libraries.length) return

    // If URL slug differs from active library, update context
    if (activeLibrary?.slug !== slug) {
      const library = libraries.find((lib) => lib.slug === slug)
      if (library) {
        setActiveLibrary(library)
      }
    }
  }, [slug, libraries, activeLibrary?.slug, setActiveLibrary])
}
