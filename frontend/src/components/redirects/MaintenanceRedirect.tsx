import { Navigate } from 'react-router-dom'
import { useActiveLibrary } from '@/contexts/ActiveLibraryContext'

/**
 * Redirect component for the legacy /maintenance route.
 * Maintenance is library-scoped; send old links to the active library.
 */
export default function MaintenanceRedirect() {
  const { activeLibrary, isLoading } = useActiveLibrary()

  if (isLoading) {
    return <div className="p-6 text-sm text-muted-foreground">Loading…</div>
  }

  if (!activeLibrary) {
    return (
      <div className="p-6 text-sm text-muted-foreground">
        Select a library to run maintenance.
      </div>
    )
  }

  return <Navigate to={`/libraries/${activeLibrary.slug}/maintenance`} replace />
}
