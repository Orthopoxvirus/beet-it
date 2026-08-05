import { Disc, Loader2, ListOrdered } from 'lucide-react'
import { cn } from '@/lib/utils'
import type { AlbumStage } from '@/types/beets-import'

// ============================================================================
// Types
// ============================================================================

interface StageIndicatorProps {
  /** Current stage of the album import process */
  stage: AlbumStage
  /** Whether analysis is currently in progress */
  isAnalyzing?: boolean
  /** Whether this album is queued for analysis */
  isQueued?: boolean
  /** Queue position (1-indexed, only when isQueued is true) */
  queuePosition?: number
  /** Callback when the disc is clicked (trigger analysis) */
  onAnalyzeClick?: () => void
  /** Optional additional CSS class */
  className?: string
}

// ============================================================================
// Component
// ============================================================================

/**
 * Single-disc indicator showing album import progress.
 *
 * The disc is clickable to trigger (re-)analysis. Its color reflects the
 * current stage:
 * - none: muted (gray)
 * - analyzed: green (candidates retrieved)
 * - chosen: blue (import in progress)
 * - imported: purple (import complete)
 *
 * While queued, a position badge replaces the disc; while analyzing, a
 * spinner replaces it.
 */
export default function StageIndicator({
  stage,
  isAnalyzing = false,
  isQueued = false,
  queuePosition,
  onAnalyzeClick,
  className,
}: StageIndicatorProps) {
  const isAnalyzed = stage === 'analyzed' || stage === 'chosen' || stage === 'imported'

  const handleDiscClick = (e: React.MouseEvent) => {
    e.stopPropagation()
    if (onAnalyzeClick && !isAnalyzing && !isQueued) {
      onAnalyzeClick()
    }
  }

  return (
    <div className={cn('flex items-center gap-0.5 flex-shrink-0', className)}>
      {/* Disc: clickable to trigger/re-trigger analysis */}
      {isAnalyzing ? (
        <Loader2
          className="h-4 w-4 text-primary animate-spin"
          aria-label="Analyzing..."
        />
      ) : isQueued ? (
        <div
          className="flex items-center gap-1 px-1.5 py-0.5 rounded bg-amber-500/10 border border-amber-500/30"
          aria-label={`Queued at position ${queuePosition ?? '?'}`}
          data-testid="queue-badge"
        >
          <ListOrdered className="h-3 w-3 text-amber-500" />
          <span className="text-xs font-medium text-amber-600 dark:text-amber-400">
            #{queuePosition ?? '?'}
          </span>
        </div>
      ) : (
        <button
          type="button"
          onClick={handleDiscClick}
          disabled={isAnalyzing}
          className={cn(
            'p-0.5 rounded transition-colors',
            onAnalyzeClick && !isAnalyzing && 'hover:bg-muted cursor-pointer',
            !onAnalyzeClick && 'cursor-default'
          )}
          aria-label={isAnalyzed ? 'Re-analyze album' : 'Analyze album'}
          title={isAnalyzed ? 'Click to re-analyze' : 'Click to analyze'}
        >
          <Disc
            className={cn(
              'h-3.5 w-3.5 transition-colors',
              stage === 'imported'
                ? 'text-purple-500'
                : stage === 'chosen'
                ? 'text-blue-500'
                : stage === 'analyzed'
                ? 'text-green-500'
                : 'text-muted-foreground/40'
            )}
          />
        </button>
      )}
    </div>
  )
}
