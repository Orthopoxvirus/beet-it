import { useNavigate } from 'react-router-dom'
import { Folder } from 'lucide-react'

import { Card } from '@/components/ui/card'
import { LibraryScanProgress } from '@/components/scan/LibraryScanProgress'

import { useLibraries } from '@/hooks/useLibraries'
import { type Library } from '@/api/libraries'

export default function ImportPage() {
  const { data, isLoading, error } = useLibraries()
  const navigate = useNavigate()

  if (isLoading) {
    return (
      <div className="flex items-center justify-center py-12">
        <div className="animate-spin rounded-full h-8 w-8 border-b-2 border-primary"></div>
      </div>
    )
  }

  if (error) {
    return (
      <div className="text-center py-12">
        <p className="text-destructive">Failed to load libraries</p>
        <p className="text-muted-foreground text-sm mt-2">
          {error instanceof Error ? error.message : 'Unknown error'}
        </p>
      </div>
    )
  }

  const libraries = data?.items || []

  return (
    <div className="space-y-6">
      <div className="flex items-center justify-between">
        <h1 className="text-2xl font-bold">Import Music</h1>
      </div>

      {libraries.length > 0 ? (
        <div className="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-3 gap-4">
          {libraries.map((library: Library) => (
            <Card
              key={library.id}
              className="p-4 cursor-pointer hover:shadow-md transition-shadow"
              onClick={() => navigate(`/import/${library.slug}/files`)}
            >
              <span className="text-lg font-semibold truncate" title={library.name}>
                {library.name}
              </span>
              {/* Show scan progress bar at the bottom of the card */}
              <LibraryScanProgress slug={library.slug} />
            </Card>
          ))}
        </div>
      ) : (
        <div className="text-center py-12 border rounded-lg bg-muted/20">
          <Folder className="h-12 w-12 mx-auto text-muted-foreground" />
          <h3 className="mt-4 text-lg font-medium">No libraries available</h3>
          <p className="mt-2 text-muted-foreground">
            Create a library first to import music into it.
          </p>
        </div>
      )}
    </div>
  )
}
