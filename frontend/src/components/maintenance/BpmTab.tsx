import { Activity, Ban, CheckCircle2, Loader2, Play } from 'lucide-react'

import { Button } from '@/components/ui/button'
import { Card, CardContent, CardHeader, CardTitle } from '@/components/ui/card'
import { Progress } from '@/components/ui/progress'
import {
  useBpmInfo,
  useBpmBackfillStatus,
  useStartBpmBackfill,
  useCancelBpmBackfill,
} from '@/hooks/useMaintenance'

interface BpmTabProps {
  slug: string
}

/** "2 h 05 min", "12 min", "< 1 min" */
export function formatDuration(seconds: number): string {
  if (seconds < 60) return '< 1 min'
  const totalMinutes = Math.round(seconds / 60)
  const hours = Math.floor(totalMinutes / 60)
  const minutes = totalMinutes % 60
  if (hours === 0) return `${minutes} min`
  return `${hours} h ${String(minutes).padStart(2, '0')} min`
}

/**
 * "Analyze missing BPM" maintenance action: shows how many tracks lack a bpm
 * tag, starts the chunked autobpm backfill, tracks progress and allows
 * cancellation (the task stops at the next chunk boundary).
 */
export default function BpmTab({ slug }: BpmTabProps) {
  const info = useBpmInfo(slug)
  const status = useBpmBackfillStatus(slug)
  const start = useStartBpmBackfill(slug)
  const cancel = useCancelBpmBackfill(slug)

  const job = status.data
  const isActive = job?.status === 'queued' || job?.status === 'running'
  const done = (job?.processed ?? 0) + (job?.failed ?? 0)
  const percent = job && job.total > 0 ? (done / job.total) * 100 : 0
  const missing = info.data?.missing_count

  return (
    <Card>
      <CardHeader className="pb-3">
        <CardTitle className="text-lg flex items-center gap-2">
          <Activity className="h-5 w-5 text-muted-foreground" />
          Analyze missing BPM
        </CardTitle>
        <p className="text-sm text-muted-foreground">
          Computes the tempo of tracks without a <code>bpm</code> tag using the
          beets autobpm plugin (librosa). Existing tags are never overwritten.
          Analysis is CPU-heavy and runs in restart-safe slices on multiple
          cores — a long job survives restarts and resumes on its own.
        </p>
      </CardHeader>
      <CardContent className="space-y-4">
        {/* Missing count */}
        {info.isLoading ? (
          <div className="flex items-center gap-2 text-sm text-muted-foreground">
            <Loader2 className="h-4 w-4 animate-spin" /> Counting tracks without BPM…
          </div>
        ) : info.error ? (
          <p className="text-sm text-destructive">Failed to load BPM info</p>
        ) : (
          <p className="text-sm">
            <span className="font-medium">{missing?.toLocaleString()}</span>{' '}
            track{missing === 1 ? '' : 's'} without a BPM tag.
            {!isActive && (missing ?? 0) > 0 && (info.data?.estimated_seconds ?? 0) > 0 && (
              <span className="text-muted-foreground">
                {' '}Estimated duration: ≈ {formatDuration(info.data!.estimated_seconds)} on{' '}
                {info.data!.workers} parallel worker{info.data!.workers === 1 ? '' : 's'}.
              </span>
            )}
          </p>
        )}

        {/* Active job progress */}
        {isActive && job && (
          <div className="space-y-2">
            <div className="flex items-center justify-between text-sm">
              <span className="text-muted-foreground">
                {job.status === 'queued' ? 'Queued…' : 'Analyzing…'}
              </span>
              <span className="font-medium">
                {done.toLocaleString()} / {job.total.toLocaleString()}
                {job.failed > 0 && (
                  <span className="text-destructive"> ({job.failed} failed)</span>
                )}
                {(job.eta_seconds ?? 0) > 0 && (
                  <span className="text-muted-foreground">
                    {' '}· ≈ {formatDuration(job.eta_seconds!)} left
                  </span>
                )}
              </span>
            </div>
            <Progress value={percent} className="h-2" />
          </div>
        )}

        {/* Terminal states */}
        {!isActive && job && job.status !== 'idle' && job.status !== 'unknown' && (
          <div className="flex items-center gap-2 text-sm">
            {job.status === 'completed' && (
              <>
                <CheckCircle2 className="h-4 w-4 text-green-500" />
                <span>
                  Last run analyzed {job.processed.toLocaleString()} track
                  {job.processed === 1 ? '' : 's'}.
                </span>
              </>
            )}
            {job.status === 'completed_with_errors' && (
              <>
                <CheckCircle2 className="h-4 w-4 text-amber-500" />
                <span>
                  Last run: {job.processed.toLocaleString()} analyzed,{' '}
                  {job.failed.toLocaleString()} failed.
                  {job.error ? ` Last error: ${job.error}` : ''}
                </span>
              </>
            )}
            {job.status === 'cancelled' && (
              <>
                <Ban className="h-4 w-4 text-amber-500" />
                <span>
                  Last run cancelled after {job.processed.toLocaleString()} track
                  {job.processed === 1 ? '' : 's'}.
                </span>
              </>
            )}
            {job.status === 'failed' && (
              <span className="text-destructive">
                Last run failed{job.error ? `: ${job.error}` : ''}
              </span>
            )}
          </div>
        )}

        {/* Actions */}
        <div className="flex items-center gap-2">
          {isActive ? (
            <Button
              variant="outline"
              size="sm"
              onClick={() => cancel.mutate()}
              disabled={cancel.isPending}
            >
              {cancel.isPending ? (
                <Loader2 className="mr-2 h-4 w-4 animate-spin" />
              ) : (
                <Ban className="mr-2 h-4 w-4" />
              )}
              Cancel
            </Button>
          ) : (
            <Button
              size="sm"
              onClick={() => start.mutate()}
              disabled={start.isPending || info.isLoading || missing === 0}
            >
              {start.isPending ? (
                <Loader2 className="mr-2 h-4 w-4 animate-spin" />
              ) : (
                <Play className="mr-2 h-4 w-4" />
              )}
              {missing === 0 ? 'Nothing to analyze' : 'Analyze missing BPM'}
            </Button>
          )}
          {start.error && (
            <span className="text-sm text-destructive">
              {start.error instanceof Error ? start.error.message : 'Failed to start'}
            </span>
          )}
        </div>
      </CardContent>
    </Card>
  )
}
