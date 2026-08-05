import { useState, useMemo } from 'react'
import { Search, Disc3, Loader2 } from 'lucide-react'

import { Card, CardContent, CardHeader, CardTitle } from '@/components/ui/card'
import { Input } from '@/components/ui/input'
import { ScrollArea } from '@/components/ui/scroll-area'

import { useLibraryAlbumsForPicker } from '@/hooks/useLibraryItems'
import type { AlbumSummary } from '@/api/libraryItems'

// ============================================================================
// Types
// ============================================================================

interface AlbumPickerProps {
  /** Library slug */
  librarySlug: string
  /** Currently selected album title (null if none) */
  selectedAlbum: string | null
  /** Callback when an album is selected */
  onAlbumSelect: (album: AlbumSummary | null) => void
  /** Whether the picker is disabled */
  disabled?: boolean
}

// ============================================================================
// Album List Item Component
// ============================================================================

interface AlbumListItemProps {
  album: AlbumSummary
  isSelected: boolean
  onSelect: () => void
  disabled?: boolean
}

function AlbumListItem({ album, isSelected, onSelect, disabled }: AlbumListItemProps) {
  return (
    <button
      type="button"
      onClick={onSelect}
      disabled={disabled}
      className={`
        w-full text-left px-3 py-2 rounded-md transition-colors
        ${isSelected
          ? 'bg-primary text-primary-foreground'
          : 'hover:bg-muted/50'
        }
        ${disabled ? 'opacity-50 cursor-not-allowed' : 'cursor-pointer'}
      `}
    >
      <div className="flex items-center justify-between gap-2">
        <div className="min-w-0 flex-1">
          <p className="font-medium text-sm truncate" title={album.title}>
            {album.title}
          </p>
          <p className={`text-xs truncate ${isSelected ? 'text-primary-foreground/70' : 'text-muted-foreground'}`} title={album.artist}>
            {album.artist}
          </p>
        </div>
        <span className={`text-xs flex-shrink-0 ${isSelected ? 'text-primary-foreground/70' : 'text-muted-foreground'}`}>
          {album.track_count} tracks
        </span>
      </div>
    </button>
  )
}

// ============================================================================
// Main Component
// ============================================================================

export default function AlbumPicker({
  librarySlug,
  selectedAlbum,
  onAlbumSelect,
  disabled = false,
}: AlbumPickerProps) {
  const [searchQuery, setSearchQuery] = useState('')

  const { data, isLoading, error } = useLibraryAlbumsForPicker(librarySlug)

  // Filter albums by search query
  const filteredAlbums = useMemo(() => {
    if (!data?.albums) return []
    if (!searchQuery.trim()) return data.albums

    const query = searchQuery.toLowerCase()
    return data.albums.filter(
      (album) =>
        album.title.toLowerCase().includes(query) ||
        album.artist.toLowerCase().includes(query)
    )
  }, [data?.albums, searchQuery])

  // Handle album selection
  const handleAlbumSelect = (album: AlbumSummary) => {
    if (selectedAlbum === album.title) {
      // Deselect if already selected
      onAlbumSelect(null)
    } else {
      onAlbumSelect(album)
    }
  }

  // Handle clear selection
  const handleClearSelection = () => {
    onAlbumSelect(null)
  }

  return (
    <Card className="h-full flex flex-col">
      <CardHeader className="pb-3">
        <div className="flex items-center gap-2">
          <Disc3 className="h-5 w-5 text-primary" />
          <CardTitle className="text-lg">Select Album</CardTitle>
        </div>
      </CardHeader>

      <CardContent className="flex-1 flex flex-col gap-3 min-h-0">
        {/* Search Input */}
        <div className="relative">
          <Search className="absolute left-2.5 top-1/2 h-4 w-4 -translate-y-1/2 text-muted-foreground" />
          <Input
            placeholder="Search albums..."
            value={searchQuery}
            onChange={(e) => setSearchQuery(e.target.value)}
            className="pl-9"
            disabled={disabled || isLoading}
          />
        </div>

        {/* Album List */}
        <ScrollArea className="flex-1 -mx-2">
          <div className="px-2 space-y-1">
            {isLoading ? (
              <div className="flex items-center justify-center py-8">
                <Loader2 className="h-5 w-5 animate-spin text-muted-foreground" />
                <span className="ml-2 text-sm text-muted-foreground">Loading albums...</span>
              </div>
            ) : error ? (
              <div className="text-center py-8">
                <p className="text-sm text-destructive">Failed to load albums</p>
                <p className="text-xs text-muted-foreground mt-1">
                  {error instanceof Error ? error.message : 'Unknown error'}
                </p>
              </div>
            ) : filteredAlbums.length === 0 ? (
              <div className="text-center py-8">
                <p className="text-sm text-muted-foreground">
                  {searchQuery ? 'No albums match your search' : 'No albums found in this library'}
                </p>
              </div>
            ) : (
              <>
                {/* Clear selection button */}
                {selectedAlbum && (
                  <button
                    type="button"
                    onClick={handleClearSelection}
                    disabled={disabled}
                    className="w-full text-left px-3 py-2 rounded-md text-sm text-muted-foreground hover:bg-muted/50 transition-colors"
                  >
                    Clear selection
                  </button>
                )}

                {/* Album list */}
                {filteredAlbums.map((album) => (
                  <AlbumListItem
                    key={album.id}
                    album={album}
                    isSelected={selectedAlbum === album.title}
                    onSelect={() => handleAlbumSelect(album)}
                    disabled={disabled}
                  />
                ))}
              </>
            )}
          </div>
        </ScrollArea>

        {/* Footer with count */}
        {data?.total !== undefined && (
          <div className="text-xs text-muted-foreground text-center pt-2 border-t">
            {filteredAlbums.length === data.total
              ? `${data.total} albums`
              : `${filteredAlbums.length} of ${data.total} albums`}
          </div>
        )}
      </CardContent>
    </Card>
  )
}
