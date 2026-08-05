import { Loader2, Clock, AlertCircle, CheckCircle2 } from 'lucide-react'

import { Progress } from '@/components/ui/progress'
import { cn } from '@/lib/utils'
import type { ScanProgressState } from '@/types/scan'

// ============================================================================
// Status Text Helpers
// ============================================================================

function getStatusText(state: ScanProgressState): string {
  if (state.error) {
    return 'Scan failed'
  }

  if (state.isBlocked && state.blockingOperations.length > 0) {
    return `Blocked by: ${state.blockingOperations.join(', ')}`
  }

  if (state.isQueued) {
    if (state.queuePosition && state.queuePosition > 1) {
      return `Queued (position ${state.queuePosition})`
    }
    return 'Scan queued'
  }

  if (!state.isScanning || !state.progress) {
    return ''
  }

  const { status } = state.progress

  switch (status) {
    case 'scanning':
      return 'Scanning...'
    case 'extracting_metadata':
      return 'Extracting metadata...'
    case 'queued':
      return 'Scan queued'
    case 'completed':
      return 'Scan completed'
    case 'failed':
      return 'Scan failed'
    default:
      return 'Processing...'
  }
}

// ============================================================================
// Component Props
// ============================================================================

export interface ScanProgressBarProps {
  /**
   * The scan progress state from useScanProgress hook
   */
  state: ScanProgressState
  /**
   * Additional CSS classes
   */
  className?: string
  /**
   * Whether to show the compact version (for library cards)
   */
  compact?: boolean
  /**
   * Whether to show percentage text
   */
  showPercentage?: boolean
}

// ============================================================================
// ScanProgressBar Component
// ============================================================================

/**
 * Displays a progress bar for scan operations
 *
 * Use this component at the bottom of library cards on the Import page
 * to show real-time scan progress.
 */
export function ScanProgressBar({
  state,
  className,
  compact = true,
  showPercentage = true,
}: ScanProgressBarProps) {
  // Don't render if not connected or no scan activity
  const shouldRender = state.isScanning || state.isQueued || state.isBlocked || state.error

  if (!shouldRender) {
    return null
  }

  const statusText = getStatusText(state)
  const percentage = state.progress?.percentage ?? 0

  // Determine icon based on state
  let StatusIcon = Loader2
  let iconClassName = 'animate-spin text-primary'

  if (state.error) {
    StatusIcon = AlertCircle
    iconClassName = 'text-destructive'
  } else if (state.isQueued && !state.isScanning) {
    StatusIcon = Clock
    iconClassName = 'text-muted-foreground'
  } else if (state.progress?.status === 'completed') {
    StatusIcon = CheckCircle2
    iconClassName = 'text-green-500'
  }

  return (
    <div
      className={cn(
        'w-full',
        compact ? 'pt-3 mt-3 border-t' : 'p-4 rounded-lg bg-muted/50',
        className
      )}
    >
      {/* Status Row */}
      <div className="flex items-center justify-between gap-2 mb-1.5">
        <div className="flex items-center gap-1.5 min-w-0">
          <StatusIcon className={cn('h-3.5 w-3.5 flex-shrink-0', iconClassName)} />
          <span
            className={cn(
              'text-xs truncate',
              state.error ? 'text-destructive' : 'text-muted-foreground'
            )}
            title={statusText}
          >
            {statusText}
          </span>
        </div>

        {showPercentage && state.isScanning && state.progress && (
          <span className="text-xs font-medium text-muted-foreground flex-shrink-0">
            {Math.round(percentage)}%
          </span>
        )}
      </div>

      {/* Progress Bar */}
      {state.isScanning && state.progress ? (
        <Progress
          value={percentage}
          className="h-1.5"
        />
      ) : state.isQueued || state.isBlocked ? (
        <Progress
          indeterminate
          className="h-1.5"
        />
      ) : null}

      {/* Item Count (optional, for non-compact mode) */}
      {!compact && state.isScanning && state.progress && state.progress.itemsTotal > 0 && (
        <div className="mt-1.5 text-xs text-muted-foreground">
          {state.progress.itemsProcessed} / {state.progress.itemsTotal} items
        </div>
      )}
    </div>
  )
}

export default ScanProgressBar
