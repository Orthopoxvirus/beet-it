import { useMemo } from 'react'
import { CheckCircle2, AlertTriangle, ArrowRight } from 'lucide-react'

import { Card, CardContent, CardHeader, CardTitle } from '@/components/ui/card'
import { Badge } from '@/components/ui/badge'
import { cn } from '@/lib/utils'

import type { LibraryItem } from '@/api/libraryItems'

export type DistinctField = 'artist' | 'album_artist' | 'genre'

export type DistinctFilters = Record<DistinctField, string | null>

export const EMPTY_DISTINCT_FILTERS: DistinctFilters = {
  artist: null,
  album_artist: null,
  genre: null,
}

export const DISTINCT_FILTER_LABELS: Record<DistinctField, string> = {
  artist: 'Artist',
  album_artist: 'Album Artist',
  genre: 'Genre',
}

export const EMPTY_LABEL = '(empty)'

const FIELDS: Array<{ key: DistinctField; label: string }> = [
  { key: 'artist', label: DISTINCT_FILTER_LABELS.artist },
  { key: 'album_artist', label: DISTINCT_FILTER_LABELS.album_artist },
  { key: 'genre', label: DISTINCT_FILTER_LABELS.genre },
]

/**
 * Normalise a LibraryItem field for distinct-counting and filter-matching.
 * Trim whitespace, then map empty/null to EMPTY_LABEL so missing tags show
 * up in the panel and can be filtered explicitly.
 */
export function normaliseDistinctValue(value: string | null | undefined): string {
  if (typeof value !== 'string') return EMPTY_LABEL
  const trimmed = value.trim()
  return trimmed === '' ? EMPTY_LABEL : trimmed
}

export function itemMatchesFilters(
  item: LibraryItem,
  filters: DistinctFilters,
): boolean {
  for (const { key } of FIELDS) {
    const wanted = filters[key]
    if (wanted == null) continue
    if (normaliseDistinctValue(item[key]) !== wanted) return false
  }
  return true
}

export interface DistinctValuesPanelProps {
  items: LibraryItem[]
  /** Currently-active filters; the matching chip in each column is highlighted. */
  activeFilters?: DistinctFilters
  /** Callback fired when the user clicks a value chip. */
  onValueClick?: (field: DistinctField, value: string) => void
  /**
   * Callback fired when the user clicks a value's "use as template" arrow —
   * seeds that value into the batch tag editor as a fixed value for the field.
   */
  onUseAsFixed?: (field: DistinctField, value: string) => void
  className?: string
}

interface DistinctEntry {
  value: string
  count: number
  isEmpty: boolean
}

/**
 * Counts distinct values per field across the loaded items so the user can
 * spot inconsistencies before doing a batch edit. A column with one
 * uniform value gets a green check; anything with two or more variants
 * gets a yellow warning, with each value listed alongside the number of
 * tracks holding it.
 */
export function DistinctValuesPanel({
  items,
  activeFilters,
  onValueClick,
  onUseAsFixed,
  className,
}: DistinctValuesPanelProps) {
  const distinctByField = useMemo(() => {
    const result: Record<DistinctField, Map<string, number>> = {
      artist: new Map(),
      album_artist: new Map(),
      genre: new Map(),
    }
    for (const item of items) {
      for (const { key } of FIELDS) {
        const value = normaliseDistinctValue(item[key])
        result[key].set(value, (result[key].get(value) ?? 0) + 1)
      }
    }
    return result
  }, [items])

  if (items.length === 0) {
    return null
  }

  const interactive = typeof onValueClick === 'function'

  return (
    <Card className={className}>
      <CardHeader className="pb-3">
        <CardTitle className="text-base">Distinct values</CardTitle>
        <p className="text-xs text-muted-foreground">
          Values across the {items.length} loaded track
          {items.length !== 1 ? 's' : ''} — multiple variants in one column
          usually mean a typo or inconsistent tag worth fixing.
          {interactive
            ? ' Click a value to filter the table to just those tracks.'
            : ''}
        </p>
      </CardHeader>
      <CardContent>
        <div className="grid grid-cols-1 md:grid-cols-3 gap-4">
          {FIELDS.map(({ key, label }) => {
            const entries: DistinctEntry[] = Array.from(
              distinctByField[key].entries()
            )
              .map(([value, count]) => ({
                value,
                count,
                isEmpty: value === EMPTY_LABEL,
              }))
              .sort((a, b) => b.count - a.count)
            const isUniform = entries.length === 1
            return (
              <DistinctColumn
                key={key}
                label={label}
                entries={entries}
                isUniform={isUniform}
                activeValue={activeFilters?.[key] ?? null}
                onValueClick={
                  onValueClick
                    ? (value) => onValueClick(key, value)
                    : undefined
                }
                onUseAsFixed={
                  onUseAsFixed
                    ? (value) => onUseAsFixed(key, value)
                    : undefined
                }
              />
            )
          })}
        </div>
      </CardContent>
    </Card>
  )
}

interface DistinctColumnProps {
  label: string
  entries: DistinctEntry[]
  isUniform: boolean
  activeValue: string | null
  onValueClick?: (value: string) => void
  onUseAsFixed?: (value: string) => void
}

function DistinctColumn({
  label,
  entries,
  isUniform,
  activeValue,
  onValueClick,
  onUseAsFixed,
}: DistinctColumnProps) {
  return (
    <div className="space-y-2 min-w-0">
      <div className="flex items-center gap-2">
        {isUniform ? (
          <CheckCircle2 className="h-4 w-4 shrink-0 text-emerald-500" />
        ) : (
          <AlertTriangle className="h-4 w-4 shrink-0 text-amber-500" />
        )}
        <span className="text-sm font-medium">{label}</span>
        <span className="text-xs text-muted-foreground">
          ({entries.length}{' '}
          {entries.length === 1 ? 'value' : 'values'})
        </span>
      </div>
      <ul className="space-y-1">
        {entries.map((entry) => {
          const isActive = activeValue === entry.value
          const clickable = typeof onValueClick === 'function'
          const Element: 'button' | 'div' = clickable ? 'button' : 'div'
          return (
            <li key={entry.value} className="flex items-center gap-1">
              <Element
                {...(clickable
                  ? {
                      type: 'button',
                      onClick: () => onValueClick?.(entry.value),
                    }
                  : {})}
                className={cn(
                  'flex items-start gap-2 min-w-0 flex-1 text-left text-sm rounded px-1.5 py-0.5 -ml-1.5',
                  clickable &&
                    'hover:bg-accent transition-colors cursor-pointer',
                  isActive && 'bg-accent ring-1 ring-primary/40'
                )}
                aria-pressed={clickable ? isActive : undefined}
                title={entry.value}
              >
                <span
                  className={cn(
                    'truncate flex-1',
                    entry.isEmpty && 'italic text-muted-foreground'
                  )}
                >
                  {entry.value}
                </span>
                <Badge variant="secondary" className="shrink-0 text-xs">
                  {entry.count}
                </Badge>
              </Element>
              {onUseAsFixed && (
                <button
                  type="button"
                  onClick={() => onUseAsFixed(entry.value)}
                  className="shrink-0 rounded p-1 text-muted-foreground hover:bg-accent hover:text-foreground transition-colors"
                  title={`Use "${entry.value}" as the fixed ${label} value in the batch editor`}
                  aria-label={`Use "${entry.value}" as the fixed ${label} value`}
                >
                  <ArrowRight className="h-3.5 w-3.5" />
                </button>
              )}
            </li>
          )
        })}
      </ul>
    </div>
  )
}
