import { Navigate, Link } from 'react-router-dom'
import { Folder } from 'lucide-react'
import { Button } from '@/components/ui/button'
import { useActiveLibrary } from '@/contexts/ActiveLibraryContext'
import { getTabMemory } from '@/hooks/useTabMemory'

/**
 * Redirect component for /import route.
 * Redirects to /import/{active-slug}/{remembered-tab} when a library exists.
 * Shows empty state with link to create library when no libraries exist.
 */
export default function ImportRedirect() {
  const { activeLibrary, isLoading, libraries } = useActiveLibrary()

  // Show loading while context initializes
  if (isLoading) {
    return (
      <div className="flex items-center justify-center py-12">
        <div className="animate-spin rounded-full h-8 w-8 border-b-2 border-primary"></div>
      </div>
    )
  }

  // No libraries exist - show empty state
  if (libraries.length === 0) {
    return (
      <div className="text-center py-12 border rounded-lg bg-muted/20">
        <Folder className="h-12 w-12 mx-auto text-muted-foreground" />
        <h3 className="mt-4 text-lg font-medium">No libraries available</h3>
        <p className="mt-2 text-muted-foreground">
          Create a library first to import music into it.
        </p>
        <Button asChild className="mt-4">
          <Link to="/libraries/create">
            Create Library
          </Link>
        </Button>
      </div>
    )
  }

  // Redirect to active library with remembered tab
  if (activeLibrary) {
    const tab = getTabMemory('import')
    return <Navigate to={`/import/${activeLibrary.slug}/${tab}`} replace />
  }

  // Fallback - should not reach here if libraries exist
  return null
}
