import {
  Loader2,
  Clock,
  AlertCircle,
  CheckCircle2,
  FileAudio,
  Timer,
  ListOrdered,
  AlertTriangle,
  Play,
} from 'lucide-react'

import { Progress } from '@/components/ui/progress'
import { Button } from '@/components/ui/button'
import { Card, CardContent, CardHeader, CardTitle } from '@/components/ui/card'
import { Badge } from '@/components/ui/badge'
import { cn } from '@/lib/utils'
import type { ScanProgressState, ScanStatus } from '@/types/scan'

// ============================================================================
// Helpers
// ============================================================================

function formatElapsedTime(seconds: number | null): string {
  if (seconds === null || seconds < 0) return '--:--'

  const hours = Math.floor(seconds / 3600)
  const minutes = Math.floor((seconds % 3600) / 60)
  const secs = Math.floor(seconds % 60)

  if (hours > 0) {
    return `${hours}:${minutes.toString().padStart(2, '0')}:${secs.toString().padStart(2, '0')}`
  }
  return `${minutes}:${secs.toString().padStart(2, '0')}`
}

function getStatusLabel(status: string): string {
  switch (status) {
    case 'scanning':
      return 'Scanning files'
    case 'extracting_metadata':
      return 'Extracting metadata'
    case 'queued':
      return 'Queued'
    case 'completed':
      return 'Completed'
    case 'failed':
      return 'Failed'
    default:
      return 'Processing'
  }
}

function truncatePath(path: string | null, maxLength = 60): string {
  if (!path) return ''
  if (path.length <= maxLength) return path

  // Try to show the filename and part of the directory
  const parts = path.split('/')
  const filename = parts.pop() || ''
  const dir = parts.join('/')

  if (filename.length >= maxLength - 3) {
    return '...' + filename.slice(-(maxLength - 3))
  }

  const remainingLength = maxLength - filename.length - 4 // account for ".../"
  if (remainingLength > 0 && dir.length > remainingLength) {
    return '...' + dir.slice(-remainingLength) + '/' + filename
  }

  return '.../' + filename
}

// ============================================================================
// Component Props
// ============================================================================

export interface ScanProgressSectionProps {
  /**
   * Real-time progress state from useScanProgress hook
   */
  progressState: ScanProgressState
  /**
   * Initial status data from useScanStatus hook (optional)
   */
  statusData?: ScanStatus | null
  /**
   * Library name for display
   */
  libraryName?: string
  /**
   * Callback when manual scan is triggered
   */
  onTriggerScan?: () => void
  /**
   * Whether the trigger scan mutation is pending
   */
  isTriggeringScan?: boolean
  /**
   * Additional CSS classes
   */
  className?: string
}

// ============================================================================
// ScanProgressSection Component
// ============================================================================

/**
 * A prominent section displaying detailed scan progress information
 *
 * Use this at the top of the import detail page (/import/<slug>) to show:
 * - Progress bar with percentage
 * - Items processed / total
 * - Current file being scanned
 * - Elapsed time
 * - Queued scans count
 * - Blocking operations indicator
 */
export function ScanProgressSection({
  progressState,
  statusData,
  libraryName,
  onTriggerScan,
  isTriggeringScan = false,
  className,
}: ScanProgressSectionProps) {
  const { isScanning, isQueued, isBlocked, progress, error, queuePosition, blockingOperations } =
    progressState

  // Determine if we should show the section
  const hasActivity = isScanning || isQueued || isBlocked || error
  const watcherActive = statusData?.watcherActive ?? false
  const queuedCount = statusData?.queuedScans ?? (isQueued ? (queuePosition ?? 1) : 0)

  // Compute display values
  const percentage = progress?.percentage ?? 0
  const itemsProcessed = progress?.itemsProcessed ?? 0
  const itemsTotal = progress?.itemsTotal ?? 0
  const currentFile = progress?.currentFile ?? null
  const elapsedSeconds = progress?.elapsedSeconds ?? null
  const status = progress?.status ?? (isQueued ? 'queued' : null)

  // Determine the primary status icon and color
  // Default to non-spinning FileAudio icon for idle state
  let StatusIcon = FileAudio
  let statusIconClass = 'text-muted-foreground'
  let statusBadgeVariant: 'default' | 'secondary' | 'destructive' | 'outline' = 'default'

  if (error) {
    StatusIcon = AlertCircle
    statusIconClass = 'text-destructive'
    statusBadgeVariant = 'destructive'
  } else if (status === 'completed') {
    StatusIcon = CheckCircle2
    statusIconClass = 'text-green-500'
    statusBadgeVariant = 'outline'
  } else if (isScanning) {
    // Only show spinning loader when actively scanning
    StatusIcon = Loader2
    statusIconClass = 'animate-spin text-primary'
  } else if (isQueued && !isScanning) {
    StatusIcon = Clock
    statusIconClass = 'text-amber-500'
    statusBadgeVariant = 'secondary'
  } else if (isBlocked) {
    StatusIcon = AlertTriangle
    statusIconClass = 'text-amber-500'
    statusBadgeVariant = 'secondary'
  }

  return (
    <Card className={cn('w-full', className)}>
      <CardHeader className="pb-2">
        {/* On narrow viewports, let the watcher chip + Scan Now button wrap to
            their own row so the "Scanner" heading doesn't get crushed
            onto two lines. */}
        <div className="flex flex-col gap-2 sm:flex-row sm:items-center sm:justify-between">
          <CardTitle className="text-lg flex items-center gap-2 min-w-0">
            <StatusIcon className={cn('h-5 w-5 flex-shrink-0', statusIconClass)} />
            {hasActivity ? (
              <span>Scan Progress</span>
            ) : (
              <span>Scanner</span>
            )}
          </CardTitle>

          <div className="flex items-center gap-2 flex-wrap">
            {/* Watcher status */}
            {watcherActive && (
              <Badge variant="outline" className="text-xs">
                <span className="mr-1.5 h-2 w-2 rounded-full bg-green-500 inline-block" />
                Watcher active
              </Badge>
            )}

            {/* Status badge */}
            {status && (
              <Badge variant={statusBadgeVariant} className="text-xs">
                {getStatusLabel(status)}
              </Badge>
            )}

            {/* Manual scan button */}
            {onTriggerScan && !isScanning && !isQueued && (
              <Button
                size="sm"
                variant="outline"
                onClick={onTriggerScan}
                disabled={isTriggeringScan}
              >
                {isTriggeringScan ? (
                  <>
                    <Loader2 className="mr-2 h-4 w-4 animate-spin" />
                    Starting...
                  </>
                ) : (
                  <>
                    <Play className="mr-2 h-4 w-4" />
                    Scan Now
                  </>
                )}
              </Button>
            )}
          </div>
        </div>
      </CardHeader>

      <CardContent className="space-y-4">
        {/* Error message */}
        {error && (
          <div className="rounded-lg bg-destructive/10 border border-destructive/20 p-3">
            <p className="text-sm text-destructive">{error}</p>
          </div>
        )}

        {/* Blocking operations warning */}
        {isBlocked && blockingOperations.length > 0 && (
          <div className="rounded-lg bg-amber-500/10 border border-amber-500/20 p-3">
            <div className="flex items-start gap-2">
              <AlertTriangle className="h-4 w-4 text-amber-500 mt-0.5 flex-shrink-0" />
              <div>
                <p className="text-sm font-medium text-amber-700 dark:text-amber-400">
                  Scan blocked by running operations
                </p>
                <p className="text-xs text-muted-foreground mt-1">
                  Waiting for: {blockingOperations.join(', ')}
                </p>
              </div>
            </div>
          </div>
        )}

        {/* Progress section (when scanning) */}
        {isScanning && progress && (
          <>
            {/* Progress bar */}
            <div className="space-y-2">
              <div className="flex items-center justify-between text-sm">
                <span className="text-muted-foreground">Progress</span>
                <span className="font-medium">{Math.round(percentage)}%</span>
              </div>
              <Progress value={percentage} className="h-2" />
            </div>

            {/* Stats grid */}
            <div className="grid grid-cols-2 sm:grid-cols-4 gap-4">
              {/* Items processed */}
              <div className="flex items-center gap-2">
                <FileAudio className="h-4 w-4 text-muted-foreground" />
                <div>
                  <p className="text-sm font-medium">
                    {itemsProcessed.toLocaleString()} / {itemsTotal.toLocaleString()}
                  </p>
                  <p className="text-xs text-muted-foreground">Items</p>
                </div>
              </div>

              {/* Elapsed time */}
              <div className="flex items-center gap-2">
                <Timer className="h-4 w-4 text-muted-foreground" />
                <div>
                  <p className="text-sm font-medium">{formatElapsedTime(elapsedSeconds)}</p>
                  <p className="text-xs text-muted-foreground">Elapsed</p>
                </div>
              </div>

              {/* Queue count */}
              {queuedCount > 0 && (
                <div className="flex items-center gap-2">
                  <ListOrdered className="h-4 w-4 text-muted-foreground" />
                  <div>
                    <p className="text-sm font-medium">{queuedCount}</p>
                    <p className="text-xs text-muted-foreground">Queued</p>
                  </div>
                </div>
              )}
            </div>

            {/* Current file */}
            {currentFile && (
              <div className="rounded-lg bg-muted/50 p-3">
                <p className="text-xs text-muted-foreground mb-1">Currently processing:</p>
                <p
                  className="text-sm font-mono truncate"
                  title={currentFile}
                >
                  {truncatePath(currentFile)}
                </p>
              </div>
            )}
          </>
        )}

        {/* Queued state (when not scanning) */}
        {isQueued && !isScanning && (
          <div className="flex items-center gap-3 p-4 rounded-lg bg-muted/50">
            <Clock className="h-8 w-8 text-amber-500" />
            <div>
              <p className="font-medium">Scan Queued</p>
              <p className="text-sm text-muted-foreground">
                {queuePosition && queuePosition > 1
                  ? `Position ${queuePosition} in queue`
                  : 'Waiting to start...'}
              </p>
            </div>
          </div>
        )}

        {/* Idle state (no scan activity) */}
        {!hasActivity && (
          <div className="text-center py-6">
            <FileAudio className="h-12 w-12 mx-auto text-muted-foreground/50" />
            <p className="mt-3 text-muted-foreground">
              No scan is currently running.
            </p>
            {libraryName && (
              <p className="text-sm text-muted-foreground mt-1">
                Click "Scan Now" to scan the import folder for {libraryName}.
              </p>
            )}
          </div>
        )}

        {/* Last completed scan info */}
        {!hasActivity && statusData?.lastCompletedScan && (
          <div className="pt-4 border-t">
            <p className="text-xs text-muted-foreground">
              Last scan completed:{' '}
              <span className="font-medium">
                {new Date(statusData.lastCompletedScan.completedAt!).toLocaleString()}
              </span>
              {' - '}
              {statusData.lastCompletedScan.itemsProcessed.toLocaleString()} items processed
            </p>
          </div>
        )}
      </CardContent>
    </Card>
  )
}

export default ScanProgressSection
