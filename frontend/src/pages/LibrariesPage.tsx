import { useState } from 'react'
import { Link, useNavigate } from 'react-router-dom'
import { Plus, Info, Folder } from 'lucide-react'

import { Button } from '@/components/ui/button'
import { Card, CardFooter } from '@/components/ui/card'
import { LibraryInfoModal } from '@/components/LibraryInfoModal'

import { useLibraries } from '@/hooks/useLibraries'
import { type Library } from '@/api/libraries'

export default function LibrariesPage() {
  const { data, isLoading, error } = useLibraries()
  const navigate = useNavigate()
  const [selectedLibrary, setSelectedLibrary] = useState<Library | null>(null)
  const [modalOpen, setModalOpen] = useState(false)

  const handleInfoClick = (library: Library) => {
    setSelectedLibrary(library)
    setModalOpen(true)
  }

  const handleModalClose = (open: boolean) => {
    setModalOpen(open)
    if (!open) {
      setSelectedLibrary(null)
    }
  }

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
        <h1 className="text-2xl font-bold">Libraries</h1>
        <Button asChild>
          <Link to="/libraries/create">
            <Plus className="h-4 w-4 mr-2" />
            Create Library
          </Link>
        </Button>
      </div>

      {libraries.length > 0 ? (
        <div className="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-3 gap-4">
          {libraries.map((library: Library) => (
            <Card
              key={library.id}
              className="group relative flex flex-col cursor-pointer hover:shadow-md transition-shadow"
              onClick={() => navigate(`/libraries/${library.slug}/albums`)}
            >
              {/* Hover action buttons */}
              <div className="absolute top-2 right-2 flex flex-col gap-1 opacity-0 group-hover:opacity-100 transition-opacity z-10">
                <Button
                  variant="ghost"
                  size="icon"
                  className="h-8 w-8"
                  onClick={(e) => {
                    e.stopPropagation()
                    handleInfoClick(library)
                  }}
                  title="View library info"
                >
                  <Info className="h-4 w-4" />
                </Button>
              </div>
              {/* Card body - minimal, just for spacing */}
              <div className="flex-1 min-h-[60px]"></div>
              {/* Title in footer area */}
              <CardFooter className="pt-3 border-t">
                <span className="text-lg font-semibold truncate" title={library.name}>
                  {library.name}
                </span>
              </CardFooter>
            </Card>
          ))}
        </div>
      ) : (
        <div className="text-center py-12 border rounded-lg bg-muted/20">
          <Folder className="h-12 w-12 mx-auto text-muted-foreground" />
          <h3 className="mt-4 text-lg font-medium">No libraries yet</h3>
          <p className="mt-2 text-muted-foreground">
            Create your first library to start organizing your music.
          </p>
          <Button asChild className="mt-4">
            <Link to="/libraries/create">
              <Plus className="h-4 w-4 mr-2" />
              Create Library
            </Link>
          </Button>
        </div>
      )}

      <LibraryInfoModal
        library={selectedLibrary}
        open={modalOpen}
        onOpenChange={handleModalClose}
      />
    </div>
  )
}
