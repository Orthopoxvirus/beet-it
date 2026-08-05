import { Navigate, useOutletContext, useParams } from 'react-router-dom'

import MaintenanceTabs, { isMaintenanceTab } from '@/components/maintenance/MaintenanceTabs'
import type { Library } from '@/api/libraries'

interface LibraryDetailContext {
  library: Library
}

/** Per-library maintenance page (route: libraries/:slug/maintenance/:tab). */
export default function LibraryMaintenancePage() {
  const { library } = useOutletContext<LibraryDetailContext>()
  const { tab } = useParams<{ tab: string }>()

  if (!tab || !isMaintenanceTab(tab)) {
    return <Navigate to={`/libraries/${library.slug}/maintenance/cover-art`} replace />
  }

  return (
    <div className="space-y-4">
      <div>
        <h1 className="text-2xl font-semibold">Maintenance</h1>
        <p className="text-sm text-muted-foreground">Library: {library.name}</p>
      </div>
      <MaintenanceTabs slug={library.slug} tab={tab} />
    </div>
  )
}
