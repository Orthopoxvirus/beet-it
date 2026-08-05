import { useState, useMemo, useCallback } from 'react'
import { Link } from 'react-router-dom'
import {
  FileSearch,
  Disc,
  Tags,
  Download,
  Check,
  X,
  Loader2,
  ChevronLeft,
  ChevronRight,
  Clock,
  Trash2,
  ArrowRightLeft,
  AlertCircle,
  AudioLines,
  Sparkles,
} from 'lucide-react'
import {
  Card,
  CardContent,
  CardDescription,
  CardHeader,
  CardTitle,
} from '@/components/ui/card'
import {
  Select,
  SelectContent,
  SelectItem,
  SelectTrigger,
  SelectValue,
} from '@/components/ui/select'
import { Button } from '@/components/ui/button'
import { Badge } from '@/components/ui/badge'
import { Alert, AlertDescription } from '@/components/ui/alert'
import { cn } from '@/lib/utils'
import { useActivityHistory, useClearActivityHistory } from '@/hooks/useActivity'
import { useLibraries } from '@/hooks/useLibraries'
import type {
  TaskType,
  TaskStatus,
  TaskEventHistoryItem,
  ActivityHistoryParams,
} from '@/types/activity'
import { TASK_TYPE_LABELS, TASK_STATUS_LABELS } from '@/types/activity'
import type { ClearHistoryParams } from '@/api/activity'

// ============================================================================
// Constants
// ============================================================================

const PAGE_SIZE = 20

const TASK_TYPES: { value: TaskType | 'all'; label: string }[] = [
  { value: 'all', label: 'All Types' },
  { value: 'scan', label: 'Scan' },
  { value: 'analysis', label: 'Analysis' },
  { value: 'tag_write', label: 'Tag Write' },
  { value: 'import', label: 'Import' },
  { value: 'move', label: 'Move' },
  { value: 'batch_edit_sync', label: 'Batch Sync' },
  { value: 'emby_refresh', label: 'Emby Refresh' },
]

const STATUS_OPTIONS: { value: TaskStatus | 'all'; label: string }[] = [
  { value: 'all', label: 'All Statuses' },
  { value: 'running', label: 'Running' },
  { value: 'completed', label: 'Completed' },
  { value: 'failed', label: 'Failed' },
]

// ============================================================================
// Utility Functions
// ============================================================================

/**
 * Format duration in seconds to a human-readable string.
 */
function formatDuration(seconds: number | null): string {
  if (seconds === null) return '-'
  if (seconds < 60) {
    return `${seconds}s`
  }
  const minutes = Math.floor(seconds / 60)
  const remainingSeconds = seconds % 60
  if (minutes < 60) {
    return remainingSeconds > 0 ? `${minutes}m ${remainingSeconds}s` : `${minutes}m`
  }
  const hours = Math.floor(minutes / 60)
  const remainingMinutes = minutes % 60
  return remainingMinutes > 0 ? `${hours}h ${remainingMinutes}m` : `${hours}h`
}

/**
 * Format a date string to a readable format.
 */
function formatDateTime(dateString: string): string {
  const date = new Date(dateString)
  return date.toLocaleString(undefined, {
    month: 'short',
    day: 'numeric',
    hour: '2-digit',
    minute: '2-digit',
  })
}

/**
 * Get the icon component for a task type.
 */
function getTaskIcon(taskType: TaskType) {
  switch (taskType) {
    case 'scan':
      return FileSearch
    case 'analysis':
      return Disc
    case 'tag_write':
      return Tags
    case 'import':
      return Download
    case 'move':
      return ArrowRightLeft
    case 'batch_edit_sync':
      return Tags
    case 'emby_refresh':
      return AlertCircle
    case 'convert_wav':
      return AudioLines
    case 'dedupe_wav':
      return Trash2
    case 'cleanup':
      return Sparkles
    default:
      return FileSearch
  }
}

/**
 * Get status badge variant and icon.
 */
function getStatusInfo(status: TaskStatus): {
  variant: 'default' | 'destructive' | 'secondary'
  icon: typeof Check
  className: string
} {
  switch (status) {
    case 'completed':
      return { variant: 'default', icon: Check, className: 'bg-green-500 hover:bg-green-500/80' }
    case 'failed':
      return { variant: 'destructive', icon: X, className: '' }
    case 'running':
      return { variant: 'secondary', icon: Loader2, className: 'animate-pulse' }
    default:
      return { variant: 'secondary', icon: Clock, className: '' }
  }
}

// ============================================================================
// Task Row Component
// ============================================================================

interface TaskRowProps {
  task: TaskEventHistoryItem
}

function TaskRow({ task }: TaskRowProps) {
  const Icon = getTaskIcon(task.taskType)
  const statusInfo = getStatusInfo(task.status)
  const StatusIcon = statusInfo.icon

  const canNavigate = task.libraryId !== null

  return (
    <div className="flex items-center gap-4 py-3 border-b last:border-b-0">
      {/* Status */}
      <div className="w-24 shrink-0">
        <Badge
          variant={statusInfo.variant}
          className={cn('flex items-center gap-1 w-fit', statusInfo.className)}
        >
          <StatusIcon className={cn('h-3 w-3', task.status === 'running' && 'animate-spin')} />
          {TASK_STATUS_LABELS[task.status]}
        </Badge>
      </div>

      {/* Type */}
      <div className="w-20 shrink-0 flex items-center gap-2">
        <Icon className="h-4 w-4 text-muted-foreground" />
        <span className="text-sm">{TASK_TYPE_LABELS[task.taskType]}</span>
      </div>

      {/* Library */}
      <div className="w-32 shrink-0">
        {canNavigate ? (
          <Link
            to={`/import/${task.librarySlug}/beets`}
            className="text-sm text-primary hover:underline truncate block"
          >
            {task.librarySlug}
          </Link>
        ) : (
          <span className="text-sm text-muted-foreground truncate block" title="Library deleted">
            {task.librarySlug}
          </span>
        )}
      </div>

      {/* Description */}
      <div className="flex-1 min-w-0">
        <p className="text-sm truncate" title={task.description}>
          {task.description}
        </p>
        {task.status === 'failed' &&
          typeof task.metadata?.error_message === 'string' && (
            <p
              className="mt-0.5 flex items-start gap-1 text-xs text-destructive"
              title={task.metadata.error_message as string}
            >
              <AlertCircle className="h-3 w-3 mt-0.5 shrink-0" />
              <span className="truncate">
                {task.metadata.error_message as string}
              </span>
            </p>
          )}
      </div>

      {/* Duration */}
      <div className="w-20 shrink-0 text-right">
        <span className="text-sm text-muted-foreground">
          {formatDuration(task.durationSeconds)}
        </span>
      </div>

      {/* Timestamp */}
      <div className="w-32 shrink-0 text-right">
        <span className="text-sm text-muted-foreground">
          {formatDateTime(task.startedAt)}
        </span>
      </div>
    </div>
  )
}

// ============================================================================
// Main Component
// ============================================================================

export default function ActivityPage() {
  // Filter state
  const [selectedLibrary, setSelectedLibrary] = useState<string>('all')
  const [selectedTaskType, setSelectedTaskType] = useState<string>('all')
  const [selectedStatus, setSelectedStatus] = useState<string>('all')
  const [currentPage, setCurrentPage] = useState(1)

  // Clear feedback state
  const [clearError, setClearError] = useState<string | null>(null)
  const [successMessage, setSuccessMessage] = useState<string | null>(null)

  // Fetch libraries for filter dropdown
  const { data: librariesData } = useLibraries()

  // Build query params
  const queryParams: ActivityHistoryParams = useMemo(() => {
    const params: ActivityHistoryParams = {
      skip: (currentPage - 1) * PAGE_SIZE,
      limit: PAGE_SIZE,
    }

    if (selectedLibrary !== 'all') {
      params.libraryId = parseInt(selectedLibrary, 10)
    }
    if (selectedTaskType !== 'all') {
      params.taskType = selectedTaskType as TaskType
    }
    if (selectedStatus !== 'all') {
      params.status = selectedStatus as TaskStatus
    }

    return params
  }, [currentPage, selectedLibrary, selectedTaskType, selectedStatus])

  // Fetch activity history
  const { data, isLoading, error } = useActivityHistory(queryParams)

  // Clear history mutation
  const clearMutation = useClearActivityHistory({
    onSuccess: (response) => {
      setClearError(null)
      setSuccessMessage(
        `Successfully cleared ${response.deletedCount} ${response.deletedCount === 1 ? 'record' : 'records'}.`
      )
      // Auto-dismiss success message after 5 seconds
      setTimeout(() => setSuccessMessage(null), 5000)
      // Reset to first page after clearing
      setCurrentPage(1)
    },
    onError: (err) => {
      setClearError(err.message || 'Failed to clear history. Please try again.')
    },
  })

  // Determine if filters are active (excluding status filter from clear operation)
  const hasFilters = selectedLibrary !== 'all' || selectedTaskType !== 'all'

  // Check if there's history to clear
  const hasHistory = (data?.total ?? 0) > 0

  // Clear history immediately — no confirmation step.
  const handleClear = useCallback(() => {
    setClearError(null)

    const params: ClearHistoryParams = {}

    if (selectedLibrary !== 'all') {
      params.libraryId = parseInt(selectedLibrary, 10)
    }
    if (selectedTaskType !== 'all') {
      params.taskType = selectedTaskType as TaskType
    }

    clearMutation.mutate(params)
  }, [selectedLibrary, selectedTaskType, clearMutation])

  // Calculate pagination
  const totalPages = data ? Math.ceil(data.total / PAGE_SIZE) : 0
  const showingFrom = data && data.total > 0 ? data.skip + 1 : 0
  const showingTo = data ? Math.min(data.skip + data.items.length, data.total) : 0

  // Reset to page 1 when filters change
  const handleFilterChange = (setter: (value: string) => void) => (value: string) => {
    setter(value)
    setCurrentPage(1)
  }

  return (
    <div className="space-y-6">
      <div className="flex items-start justify-between">
        <div>
          <h1 className="text-2xl font-bold">Activity History</h1>
          <p className="text-muted-foreground">
            View the complete history of background tasks across all libraries
          </p>
        </div>
        {hasHistory && (
          <Button
            variant="outline"
            size="sm"
            onClick={handleClear}
            disabled={clearMutation.isPending}
            className="text-destructive hover:text-destructive hover:bg-destructive/10"
          >
            {clearMutation.isPending ? (
              <Loader2 className="h-4 w-4 mr-2 animate-spin" />
            ) : (
              <Trash2 className="h-4 w-4 mr-2" />
            )}
            {hasFilters ? 'Clear Filtered' : 'Clear All'}
          </Button>
        )}
      </div>

      {/* Success message */}
      {successMessage && (
        <Alert className="border-green-500/50 bg-green-50 dark:bg-green-950 text-green-700 dark:text-green-400">
          <Check className="h-4 w-4" />
          <AlertDescription>{successMessage}</AlertDescription>
        </Alert>
      )}

      {/* Clear error message */}
      {clearError && (
        <Alert variant="destructive">
          <AlertCircle className="h-4 w-4" />
          <AlertDescription>{clearError}</AlertDescription>
        </Alert>
      )}

      <Card>
        <CardHeader>
          <CardTitle>Task History</CardTitle>
          <CardDescription>
            Filter and browse task execution history
          </CardDescription>
        </CardHeader>
        <CardContent>
          {/* Filters */}
          <div className="flex flex-wrap gap-4 mb-6">
            {/* Library Filter */}
            <div className="w-48">
              <Select
                value={selectedLibrary}
                onValueChange={handleFilterChange(setSelectedLibrary)}
              >
                <SelectTrigger>
                  <SelectValue placeholder="All Libraries" />
                </SelectTrigger>
                <SelectContent>
                  <SelectItem value="all">All Libraries</SelectItem>
                  {librariesData?.items.map((library) => (
                    <SelectItem key={library.id} value={library.id.toString()}>
                      {library.name}
                    </SelectItem>
                  ))}
                </SelectContent>
              </Select>
            </div>

            {/* Task Type Filter */}
            <div className="w-36">
              <Select
                value={selectedTaskType}
                onValueChange={handleFilterChange(setSelectedTaskType)}
              >
                <SelectTrigger>
                  <SelectValue placeholder="All Types" />
                </SelectTrigger>
                <SelectContent>
                  {TASK_TYPES.map((type) => (
                    <SelectItem key={type.value} value={type.value}>
                      {type.label}
                    </SelectItem>
                  ))}
                </SelectContent>
              </Select>
            </div>

            {/* Status Filter */}
            <div className="w-36">
              <Select
                value={selectedStatus}
                onValueChange={handleFilterChange(setSelectedStatus)}
              >
                <SelectTrigger>
                  <SelectValue placeholder="All Statuses" />
                </SelectTrigger>
                <SelectContent>
                  {STATUS_OPTIONS.map((status) => (
                    <SelectItem key={status.value} value={status.value}>
                      {status.label}
                    </SelectItem>
                  ))}
                </SelectContent>
              </Select>
            </div>
          </div>

          {/* Loading state */}
          {isLoading && (
            <div className="flex items-center justify-center py-12">
              <Loader2 className="h-8 w-8 animate-spin text-muted-foreground" />
            </div>
          )}

          {/* Error state */}
          {error && (
            <div className="rounded-lg border border-destructive/50 bg-destructive/10 p-4">
              <p className="text-sm text-destructive">
                Failed to load activity history. Please try again.
              </p>
            </div>
          )}

          {/* Table Header + rows — wrapped in an x-scroll container so the
              six-column row keeps its min-width without forcing the whole
              page to scroll sideways on narrow viewports. */}
          {!isLoading && !error && data && (
            <>
              <div className="overflow-x-auto">
                <div className="min-w-[720px]">
                  <div className="flex items-center gap-4 py-2 border-b text-sm font-medium text-muted-foreground">
                    <div className="w-24 shrink-0">Status</div>
                    <div className="w-20 shrink-0">Type</div>
                    <div className="w-32 shrink-0">Library</div>
                    <div className="flex-1">Description</div>
                    <div className="w-20 shrink-0 text-right">Duration</div>
                    <div className="w-32 shrink-0 text-right">Started</div>
                  </div>

                  {/* Table Content */}
                  {data.items.length === 0 ? (
                    <div className="flex flex-col items-center justify-center py-12 text-center">
                      <Clock className="h-12 w-12 text-muted-foreground/50 mb-4" />
                      <p className="text-sm text-muted-foreground">No tasks found</p>
                      <p className="text-xs text-muted-foreground mt-1">
                        Try adjusting your filters
                      </p>
                    </div>
                  ) : (
                    <div>
                      {data.items.map((task) => (
                        <TaskRow key={task.id} task={task} />
                      ))}
                    </div>
                  )}
                </div>
              </div>

              {/* Pagination */}
              {data.total > 0 && (
                <div className="flex items-center justify-between mt-6 pt-4 border-t">
                  <div className="text-sm text-muted-foreground">
                    Showing {showingFrom} to {showingTo} of {data.total} tasks
                  </div>
                  <div className="flex items-center gap-2">
                    <Button
                      variant="outline"
                      size="sm"
                      onClick={() => setCurrentPage((p) => Math.max(1, p - 1))}
                      disabled={currentPage === 1}
                    >
                      <ChevronLeft className="h-4 w-4" />
                      Previous
                    </Button>
                    <div className="text-sm text-muted-foreground px-2">
                      Page {currentPage} of {totalPages}
                    </div>
                    <Button
                      variant="outline"
                      size="sm"
                      onClick={() => setCurrentPage((p) => Math.min(totalPages, p + 1))}
                      disabled={currentPage >= totalPages}
                    >
                      Next
                      <ChevronRight className="h-4 w-4" />
                    </Button>
                  </div>
                </div>
              )}
            </>
          )}
        </CardContent>
      </Card>
    </div>
  )
}
