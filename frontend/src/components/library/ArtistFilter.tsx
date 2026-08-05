import { useMemo, useState } from 'react'
import { Check, ChevronsUpDown, Search, Users } from 'lucide-react'

import { Button } from '@/components/ui/button'
import { Input } from '@/components/ui/input'
import { ScrollArea } from '@/components/ui/scroll-area'
import { Popover, PopoverContent, PopoverTrigger } from '@/components/ui/popover'
import { cn } from '@/lib/utils'

interface ArtistFilterProps {
  /** Album artists present in the current search + BPM result (alphabetical). */
  inResult: string[]
  /** Remaining library album artists, not in the current result (alphabetical). */
  others: string[]
  /** Currently selected album artists. */
  selected: string[]
  onChange: (next: string[]) => void
  isLoading?: boolean
}

/**
 * Multi-select album-artist filter for the Titles page.
 *
 * Ordering, top to bottom: checked artists first, then artists present in the
 * current search/BPM result, then the rest. A search box filters the visible
 * list; toggling an artist keeps the popover open.
 */
export function ArtistFilter({
  inResult,
  others,
  selected,
  onChange,
  isLoading = false,
}: ArtistFilterProps) {
  const [open, setOpen] = useState(false)
  const [query, setQuery] = useState('')

  const selectedSet = useMemo(() => new Set(selected), [selected])

  // Checked → in-result (unchecked) → others (unchecked). The backend already
  // returns each group alphabetical; selected is sorted here for a stable order.
  const ordered = useMemo(() => {
    const selectedSorted = [...selected].sort((a, b) => a.localeCompare(b))
    const inResultRest = inResult.filter((a) => !selectedSet.has(a))
    const othersRest = others.filter((a) => !selectedSet.has(a))
    return { selectedSorted, inResultRest, othersRest }
  }, [selected, selectedSet, inResult, others])

  const q = query.trim().toLowerCase()
  const matches = (a: string) => !q || a.toLowerCase().includes(q)

  const visibleSelected = ordered.selectedSorted.filter(matches)
  const visibleInResult = ordered.inResultRest.filter(matches)
  const visibleOthers = ordered.othersRest.filter(matches)
  const visibleCount = visibleSelected.length + visibleInResult.length + visibleOthers.length
  const totalCount = inResult.length + others.length

  const toggle = (artist: string) => {
    onChange(
      selectedSet.has(artist)
        ? selected.filter((a) => a !== artist)
        : [...selected, artist]
    )
  }

  const triggerLabel =
    selected.length === 0
      ? 'Album artists'
      : `${selected.length} album artist${selected.length === 1 ? '' : 's'}`

  const renderOption = (artist: string) => {
    const isSelected = selectedSet.has(artist)
    return (
      <button
        key={artist}
        type="button"
        role="option"
        aria-selected={isSelected}
        onClick={() => toggle(artist)}
        className="flex w-full items-center gap-2 rounded-sm px-2 py-1.5 text-left text-sm outline-none hover:bg-accent focus-visible:bg-accent"
      >
        <span
          className={cn(
            'flex h-4 w-4 shrink-0 items-center justify-center rounded-sm border border-primary',
            isSelected && 'bg-primary text-primary-foreground'
          )}
          aria-hidden="true"
        >
          {isSelected && <Check className="h-3 w-3" />}
        </span>
        <span className="truncate" title={artist}>
          {artist}
        </span>
      </button>
    )
  }

  return (
    <Popover open={open} onOpenChange={setOpen}>
      <PopoverTrigger asChild>
        <Button
          variant="outline"
          size="sm"
          role="combobox"
          aria-expanded={open}
          aria-label="Filter by album artist"
          className="h-9 justify-between gap-2"
        >
          <span className="flex items-center gap-1.5">
            <Users className="h-4 w-4" />
            {triggerLabel}
          </span>
          <ChevronsUpDown className="h-4 w-4 opacity-50" />
        </Button>
      </PopoverTrigger>
      <PopoverContent className="w-64 p-0" align="start">
        <div className="relative border-b p-2">
          <Search className="absolute left-4 top-1/2 h-4 w-4 -translate-y-1/2 text-muted-foreground" />
          <Input
            value={query}
            onChange={(e) => setQuery(e.target.value)}
            placeholder="Filter artists…"
            className="h-8 pl-8"
            aria-label="Filter album artists"
          />
        </div>
        <ScrollArea className="max-h-64 p-1">
          {isLoading && totalCount === 0 ? (
            <p className="px-2 py-6 text-center text-sm text-muted-foreground">Loading…</p>
          ) : totalCount === 0 ? (
            <p className="px-2 py-6 text-center text-sm text-muted-foreground">No artists</p>
          ) : visibleCount === 0 ? (
            <p className="px-2 py-6 text-center text-sm text-muted-foreground">
              No artists match “{query}”
            </p>
          ) : (
            <>
              {visibleSelected.map(renderOption)}
              {visibleInResult.map(renderOption)}
              {visibleOthers.length > 0 && (
                <>
                  {(visibleSelected.length > 0 || visibleInResult.length > 0) && (
                    <p className="px-2 pb-1 pt-2 text-xs text-muted-foreground">
                      Not in current results
                    </p>
                  )}
                  {visibleOthers.map(renderOption)}
                </>
              )}
            </>
          )}
        </ScrollArea>
        {selected.length > 0 && (
          <div className="border-t p-1">
            <Button
              variant="ghost"
              size="sm"
              className="w-full justify-center text-xs"
              onClick={() => onChange([])}
            >
              Clear {selected.length} selected
            </Button>
          </div>
        )}
      </PopoverContent>
    </Popover>
  )
}
