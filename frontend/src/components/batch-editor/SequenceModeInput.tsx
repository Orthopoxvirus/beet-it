import { Input } from '@/components/ui/input'
import { Label } from '@/components/ui/label'
import { Checkbox } from '@/components/ui/checkbox'

// ============================================================================
// Types
// ============================================================================

interface SequenceModeInputProps {
  /** Starting value for the sequence */
  start: number
  /** Whether to restart numbering per directory */
  perDirectory: boolean
  /** Callback when start value changes */
  onStartChange: (start: number) => void
  /** Callback when perDirectory changes */
  onPerDirectoryChange: (perDirectory: boolean) => void
  /** Whether the inputs are disabled */
  disabled?: boolean
}

// ============================================================================
// Component
// ============================================================================

/**
 * Input component for Sequence mode - allows configuring sequential
 * track numbering with optional per-directory restart.
 */
export function SequenceModeInput({
  start,
  perDirectory,
  onStartChange,
  onPerDirectoryChange,
  disabled = false,
}: SequenceModeInputProps) {
  const startId = 'sequence-start'
  const perDirectoryId = 'sequence-per-directory'

  return (
    <div className="space-y-3">
      {/* Start Value Input */}
      <div className="space-y-1.5">
        <Label htmlFor={startId} className="text-xs text-muted-foreground">
          Starting Number
        </Label>
        <Input
          id={startId}
          type="number"
          min={1}
          max={9999}
          value={start}
          onChange={(e) => onStartChange(Math.max(1, parseInt(e.target.value, 10) || 1))}
          disabled={disabled}
          className="h-8 w-24"
        />
        <p className="text-xs text-muted-foreground">
          Track numbers will start from this value.
        </p>
      </div>

      {/* Per Directory Checkbox */}
      <div className="flex items-start space-x-2">
        <Checkbox
          id={perDirectoryId}
          checked={perDirectory}
          onCheckedChange={(checked) => onPerDirectoryChange(checked === true)}
          disabled={disabled}
        />
        <div className="grid gap-1.5 leading-none">
          <Label
            htmlFor={perDirectoryId}
            className="text-sm font-medium leading-none cursor-pointer"
          >
            Restart per directory
          </Label>
          <p className="text-xs text-muted-foreground">
            When enabled, numbering restarts at the starting value for each folder.
          </p>
        </div>
      </div>

      {/* Behavior explanation */}
      <div className="rounded-md bg-muted/50 p-2 text-xs">
        <p className="font-medium mb-1">Numbering Behavior:</p>
        {perDirectory ? (
          <p className="text-muted-foreground">
            Each folder will have tracks numbered starting from {start}.
            For example, if you have 3 tracks in /album1 and 4 tracks in /album2,
            they will be numbered {start}-{start + 2} and {start}-{start + 3} respectively.
          </p>
        ) : (
          <p className="text-muted-foreground">
            All tracks will be numbered sequentially starting from {start},
            regardless of which folder they are in.
          </p>
        )}
      </div>
    </div>
  )
}

export default SequenceModeInput
