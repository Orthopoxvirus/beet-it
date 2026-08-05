import { useScanProgress } from '@/hooks/useScanProgress'
import { ScanProgressBar } from './ScanProgressBar'

export interface LibraryScanProgressProps {
  /**
   * The library slug to monitor
   */
  slug: string
  /**
   * Additional CSS classes
   */
  className?: string
}

/**
 * A wrapper component that connects to SSE and displays the scan progress bar
 *
 * Use this in library cards on the Import page to show real-time scan progress.
 */
export function LibraryScanProgress({ slug, className }: LibraryScanProgressProps) {
  const state = useScanProgress(slug)

  return <ScanProgressBar state={state} className={className} compact />
}

export default LibraryScanProgress
