import { Input } from '@/components/ui/input'
import { Label } from '@/components/ui/label'
import type { TagName } from '@/types/batch-tag-editor'

// ============================================================================
// Types
// ============================================================================

interface FixedModeInputProps {
  /** Tag name being configured */
  tag: TagName
  /** Current fixed value */
  value: string
  /** Callback when value changes */
  onChange: (value: string) => void
  /** Whether the input is disabled */
  disabled?: boolean
}

// ============================================================================
// Component
// ============================================================================

/**
 * Input component for Fixed mode - allows entering a constant value
 * that will replace the tag for all selected items.
 */
export function FixedModeInput({
  tag,
  value,
  onChange,
  disabled = false,
}: FixedModeInputProps) {
  const inputId = `fixed-value-${tag}`
  const placeholder =
    tag === 'track_number'
      ? 'Enter track number...'
      : 'Enter fixed value...'

  return (
    <div className="space-y-2">
      <Label htmlFor={inputId} className="text-xs text-muted-foreground">
        Fixed Value
      </Label>
      <Input
        id={inputId}
        type={tag === 'track_number' ? 'number' : 'text'}
        value={value}
        onChange={(e) => onChange(e.target.value)}
        placeholder={placeholder}
        disabled={disabled}
        className="h-8"
        min={tag === 'track_number' ? 1 : undefined}
      />
      <p className="text-xs text-muted-foreground">
        All selected tracks will have this value set.
        {tag !== 'track_number' && ' Leave empty to clear the tag.'}
      </p>
    </div>
  )
}

export default FixedModeInput
