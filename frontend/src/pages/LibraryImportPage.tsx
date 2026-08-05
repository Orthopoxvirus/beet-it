import { useParams, Link } from 'react-router-dom'
import { ArrowLeft, AlertCircle, Library as LibraryIcon } from 'lucide-react'

import { Button } from '@/components/ui/button'
import { Card, CardContent, CardHeader, CardTitle } from '@/components/ui/card'
import { ImportFolderTree } from '@/components/import'
import { useLibrary } from '@/hooks/useLibraries'

// ============================================================================
// Loading Skeleton Component
// ============================================================================

function LoadingSkeleton() {
  return (
    <div className="space-y-6">
      <div className="flex items-center gap-4">
        <Button variant="ghost" size="icon" disabled>
          <ArrowLeft className="h-4 w-4" />
        </Button>
        <div className="h-8 w-48 bg-muted animate-pulse rounded" />
      </div>
      <div className="grid grid-cols-1 lg:grid-cols-3 gap-6">
        <div className="lg:col-span-1">
          <div className="border rounded-md h-[500px] bg-muted/20 animate-pulse" />
        </div>
        <div className="lg:col-span-2">
          <div className="border rounded-md h-[300px] bg-muted/20 animate-pulse" />
        </div>
      </div>
    </div>
  )
}

// ============================================================================
// Main Page Component
// ============================================================================

export default function LibraryImportPage() {
  const { slug } = useParams<{ slug: string }>()

  const {
    data: library,
    isLoading,
    error,
  } = useLibrary(slug || '')

  // Invalid library slug
  if (!slug) {
    return (
      <div className="space-y-6">
        <div className="flex items-center gap-4">
          <Button variant="ghost" size="icon" asChild>
            <Link to="/import">
              <ArrowLeft className="h-4 w-4" />
            </Link>
          </Button>
          <h1 className="text-2xl font-bold">Import</h1>
        </div>
        <div className="text-center py-12 border rounded-lg bg-muted/20">
          <AlertCircle className="h-12 w-12 mx-auto text-destructive" />
          <h3 className="mt-4 text-lg font-medium">Invalid Library</h3>
          <p className="mt-2 text-muted-foreground">
            The library slug is not valid.
          </p>
          <Button asChild className="mt-4">
            <Link to="/import">Back to Import</Link>
          </Button>
        </div>
      </div>
    )
  }

  // Loading state
  if (isLoading) {
    return <LoadingSkeleton />
  }

  // Error state
  if (error) {
    const isNotFound =
      error instanceof Error &&
      'status' in error &&
      (error as { status: number }).status === 404

    return (
      <div className="space-y-6">
        <div className="flex items-center gap-4">
          <Button variant="ghost" size="icon" asChild>
            <Link to="/import">
              <ArrowLeft className="h-4 w-4" />
            </Link>
          </Button>
          <h1 className="text-2xl font-bold">Import</h1>
        </div>
        <div className="text-center py-12 border rounded-lg bg-muted/20">
          <AlertCircle className="h-12 w-12 mx-auto text-destructive" />
          <h3 className="mt-4 text-lg font-medium">
            {isNotFound ? 'Library Not Found' : 'Error Loading Library'}
          </h3>
          <p className="mt-2 text-muted-foreground">
            {error instanceof Error ? error.message : 'An unknown error occurred'}
          </p>
          <Button asChild className="mt-4">
            <Link to="/import">Back to Import</Link>
          </Button>
        </div>
      </div>
    )
  }

  // Library not found (no error but no data)
  if (!library) {
    return (
      <div className="space-y-6">
        <div className="flex items-center gap-4">
          <Button variant="ghost" size="icon" asChild>
            <Link to="/import">
              <ArrowLeft className="h-4 w-4" />
            </Link>
          </Button>
          <h1 className="text-2xl font-bold">Import</h1>
        </div>
        <div className="text-center py-12 border rounded-lg bg-muted/20">
          <LibraryIcon className="h-12 w-12 mx-auto text-muted-foreground" />
          <h3 className="mt-4 text-lg font-medium">Library Not Found</h3>
          <p className="mt-2 text-muted-foreground">
            The library "{slug}" could not be found.
          </p>
          <Button asChild className="mt-4">
            <Link to="/import">Back to Import</Link>
          </Button>
        </div>
      </div>
    )
  }

  return (
    <div className="space-y-6">
      {/* Header with back navigation */}
      <div className="flex items-center gap-4">
        <Button variant="ghost" size="icon" asChild>
          <Link to="/import">
            <ArrowLeft className="h-4 w-4" />
          </Link>
        </Button>
        <div>
          <h1 className="text-2xl font-bold">{library.name}</h1>
          <p className="text-sm text-muted-foreground">Import folder browser</p>
        </div>
      </div>

      {/* Main content with folder tree on left */}
      <div className="grid grid-cols-1 lg:grid-cols-3 gap-6">
        {/* Left side - Import Folder Tree */}
        <div className="lg:col-span-1">
          <ImportFolderTree librarySlug={slug} />
        </div>

        {/* Right side - Library info and future import actions */}
        <div className="lg:col-span-2 space-y-6">
          {/* Library Info Card */}
          <Card>
            <CardHeader>
              <CardTitle className="text-lg">Library Details</CardTitle>
            </CardHeader>
            <CardContent>
              <div className="grid grid-cols-1 md:grid-cols-2 gap-4 text-sm">
                <div>
                  <span className="text-muted-foreground">Import Path:</span>
                  <p className="font-mono mt-1 truncate" title={library.import_path}>
                    {library.import_path || 'Not configured'}
                  </p>
                </div>
                <div>
                  <span className="text-muted-foreground">Library Path:</span>
                  <p className="font-mono mt-1 truncate" title={library.library_path}>
                    {library.library_path}
                  </p>
                </div>
              </div>
            </CardContent>
          </Card>

          {/* Placeholder for future import actions */}
          <Card>
            <CardHeader>
              <CardTitle className="text-lg">Import Actions</CardTitle>
            </CardHeader>
            <CardContent>
              <p className="text-sm text-muted-foreground">
                Select folders from the tree on the left to begin importing music into your library.
              </p>
              <p className="text-sm text-muted-foreground mt-2">
                Album selection and import functionality will be available in a future update.
              </p>
            </CardContent>
          </Card>
        </div>
      </div>
    </div>
  )
}
