import {
  Select,
  SelectContent,
  SelectItem,
  SelectTrigger,
  SelectValue,
} from '@/components/ui/select'
import { Label } from '@/components/ui/label'
import { FixedModeInput } from './FixedModeInput'
import { RegexModeInput } from './RegexModeInput'
import { SequenceModeInput } from './SequenceModeInput'
import type {
  TagName,
  TransformationMode,
  SourceField,
  TagFieldState,
} from '@/types/batch-tag-editor'
import { TAG_LABELS } from '@/types/batch-tag-editor'

// ============================================================================
// Types
// ============================================================================

interface TagFieldConfigProps {
  /** Tag being configured */
  tag: TagName
  /** Current field state */
  state: TagFieldState
  /** Callback to update state */
  onChange: (state: TagFieldState) => void
  /** Whether the field is disabled */
  disabled?: boolean
  /** Pattern validation error (for regex mode) */
  patternError?: string
}

// ============================================================================
// Mode Options
// ============================================================================

type ModeOption = {
  value: TransformationMode | 'none'
  label: string
}

const STANDARD_MODE_OPTIONS: ModeOption[] = [
  { value: 'none', label: 'None' },
  { value: 'fixed', label: 'Fixed Value' },
  { value: 'regex', label: 'Regex' },
]

const TRACK_NUMBER_MODE_OPTIONS: ModeOption[] = [
  { value: 'none', label: 'None' },
  { value: 'fixed', label: 'Fixed Value' },
  { value: 'regex', label: 'Regex' },
  { value: 'sequence', label: 'Sequence' },
]

// ============================================================================
// Component
// ============================================================================

/**
 * Configuration component for a single tag field.
 * Allows selecting a transformation mode and configuring its parameters.
 */
export function TagFieldConfig({
  tag,
  state,
  onChange,
  disabled = false,
  patternError,
}: TagFieldConfigProps) {
  const modeOptions = tag === 'track_number' ? TRACK_NUMBER_MODE_OPTIONS : STANDARD_MODE_OPTIONS
  const modeId = `tag-mode-${tag}`
  const currentMode = state.enabled ? (state.mode || 'none') : 'none'

  // Handle mode change
  const handleModeChange = (value: string) => {
    if (value === 'none') {
      onChange({
        ...state,
        enabled: false,
        mode: null,
      })
    } else {
      const newMode = value as TransformationMode
      onChange({
        ...state,
        enabled: true,
        mode: newMode,
        // Set defaults for new mode
        ...(newMode === 'fixed' && { fixedValue: state.fixedValue || '' }),
        ...(newMode === 'regex' && {
          sourceField: state.sourceField || 'filename',
          pattern: state.pattern || '',
          replacement: state.replacement || '',
        }),
        ...(newMode === 'sequence' && {
          sequenceStart: state.sequenceStart ?? 1,
          perDirectory: state.perDirectory ?? false,
        }),
      })
    }
  }

  // Render mode-specific input
  const renderModeInput = () => {
    if (!state.enabled || !state.mode) {
      return null
    }

    switch (state.mode) {
      case 'fixed':
        return (
          <FixedModeInput
            tag={tag}
            value={state.fixedValue || ''}
            onChange={(value) => onChange({ ...state, fixedValue: value })}
            disabled={disabled}
          />
        )

      case 'regex':
        return (
          <RegexModeInput
            tag={tag}
            sourceField={state.sourceField || 'filename'}
            pattern={state.pattern || ''}
            replacement={state.replacement || ''}
            onSourceFieldChange={(field: SourceField) =>
              onChange({ ...state, sourceField: field })
            }
            onPatternChange={(pattern) => onChange({ ...state, pattern })}
            onReplacementChange={(replacement) => onChange({ ...state, replacement })}
            disabled={disabled}
            patternError={patternError}
          />
        )

      case 'sequence':
        return (
          <SequenceModeInput
            start={state.sequenceStart ?? 1}
            perDirectory={state.perDirectory ?? false}
            onStartChange={(start) => onChange({ ...state, sequenceStart: start })}
            onPerDirectoryChange={(perDirectory) =>
              onChange({ ...state, perDirectory })
            }
            disabled={disabled}
          />
        )

      default:
        return null
    }
  }

  return (
    <div className="rounded-md border p-3 space-y-3">
      {/* Tag Header with Mode Selector */}
      <div className="flex items-center justify-between gap-4">
        <Label htmlFor={modeId} className="font-medium">
          {TAG_LABELS[tag]}
        </Label>
        <Select
          value={currentMode}
          onValueChange={handleModeChange}
          disabled={disabled}
        >
          <SelectTrigger id={modeId} className="w-[150px] h-8">
            <SelectValue placeholder="Select mode" />
          </SelectTrigger>
          <SelectContent>
            {modeOptions.map((option) => (
              <SelectItem key={option.value} value={option.value}>
                {option.label}
              </SelectItem>
            ))}
          </SelectContent>
        </Select>
      </div>

      {/* Mode-Specific Configuration */}
      {renderModeInput()}
    </div>
  )
}

export default TagFieldConfig
