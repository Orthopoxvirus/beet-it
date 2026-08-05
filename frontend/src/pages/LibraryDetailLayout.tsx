import { useEffect } from 'react'
import { useParams, useSearchParams, useNavigate, Outlet } from 'react-router-dom'
import { AlertCircle } from 'lucide-react'

import { useLibrary } from '@/hooks/useLibraries'
import { useLibraryAlbums } from '@/hooks/useAlbums'
import { useSyncActiveLibraryFromUrl } from '@/contexts/ActiveLibraryContext'

// ============================================================================
// Loading Skeleton Component
// ============================================================================

function LoadingSkeleton() {
  return (
    <div className="space-y-6">
      <div className="flex items-center gap-4">
        <div className="h-9 w-24 bg-muted animate-pulse rounded" />
        <div className="h-8 w-48 bg-muted animate-pulse rounded" />
      </div>
      <div className="h-10 w-64 bg-muted animate-pulse rounded" />
      <div className="grid grid-cols-2 sm:grid-cols-3 md:grid-cols-4 lg:grid-cols-5 xl:grid-cols-6 gap-4">
        {Array.from({ length: 12 }).map((_, i) => (
          <div key={i} className="space-y-2">
            <div className="aspect-square bg-muted animate-pulse rounded" />
            <div className="h-4 bg-muted animate-pulse rounded w-3/4" />
            <div className="h-3 bg-muted animate-pulse rounded w-1/2" />
          </div>
        ))}
      </div>
    </div>
  )
}

// ============================================================================
// Main Layout Component
// ============================================================================

export default function LibraryDetailLayout() {
  const { slug } = useParams<{ slug: string }>()
  const [searchParams] = useSearchParams()
  const navigate = useNavigate()

  // Sync active library context with URL slug
  useSyncActiveLibraryFromUrl(slug)

  // Legacy tab URL redirect
  const tab = searchParams.get('tab')
  useEffect(() => {
    if (tab) {
      // Map legacy tab values to new routes
      const tabMap: Record<string, string> = {
        albums: 'albums',
        'batch-edit': 'batch-edit',
        settings: 'settings',
      }
      const newPath = tabMap[tab] || 'albums'
      navigate(newPath, { replace: true })
    }
  }, [tab, navigate])

  // Fetch library details
  const {
    data: library,
    isLoading: libraryLoading,
    error: libraryError,
  } = useLibrary(slug || '')

  // Fetch albums for count display (only need total) — don't block layout on this
  const { data: albumsData } = useLibraryAlbums(slug || '')

  const isLoading = libraryLoading
  const albumCount = albumsData?.total ?? 0

  // Update document title when library loads
  useEffect(() => {
    if (library) {
      document.title = `beet it - Library: ${library.name}`
    }
    return () => {
      document.title = 'beet it'
    }
  }, [library])

  // Invalid library slug
  if (!slug) {
    return (
      <div className="text-center py-12 border rounded-lg bg-muted/20">
        <AlertCircle className="h-12 w-12 mx-auto text-destructive" />
        <h3 className="mt-4 text-lg font-medium">Invalid Library</h3>
        <p className="mt-2 text-muted-foreground">
          The library slug is not valid.
        </p>
      </div>
    )
  }

  // Loading state
  if (isLoading) {
    return <LoadingSkeleton />
  }

  // Error state
  if (libraryError) {
    const isNotFound =
      libraryError instanceof Error &&
      'status' in libraryError &&
      (libraryError as { status: number }).status === 404

    return (
      <div className="text-center py-12 border rounded-lg bg-muted/20">
        <AlertCircle className="h-12 w-12 mx-auto text-destructive" />
        <h3 className="mt-4 text-lg font-medium">
          {isNotFound ? 'Library Not Found' : 'Error Loading Library'}
        </h3>
        <p className="mt-2 text-muted-foreground">
          {libraryError instanceof Error
            ? libraryError.message
            : 'An unknown error occurred'}
        </p>
      </div>
    )
  }

  // No library found
  if (!library) {
    return (
      <div className="text-center py-12 border rounded-lg bg-muted/20">
        <AlertCircle className="h-12 w-12 mx-auto text-muted-foreground" />
        <h3 className="mt-4 text-lg font-medium">Library Not Found</h3>
        <p className="mt-2 text-muted-foreground">
          The library you're looking for doesn't exist.
        </p>
      </div>
    )
  }

  return (
    <div className="space-y-6">
      {/* Nested route outlet - renders sub-pages */}
      <Outlet context={{ library, albumCount }} />
    </div>
  )
}

// Export context type for child pages
import type { Library } from '@/api/libraries'

export interface LibraryDetailContext {
  library: Library
  albumCount: number
}
