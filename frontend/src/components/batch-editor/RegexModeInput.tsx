import { Input } from '@/components/ui/input'
import { Label } from '@/components/ui/label'
import {
  Select,
  SelectContent,
  SelectItem,
  SelectTrigger,
  SelectValue,
} from '@/components/ui/select'
import type { TagName, SourceField } from '@/types/batch-tag-editor'
import { SOURCE_FIELDS, SOURCE_FIELD_LABELS } from '@/types/batch-tag-editor'

// ============================================================================
// Types
// ============================================================================

interface RegexModeInputProps {
  /** Tag name being configured */
  tag: TagName
  /** Selected source field */
  sourceField: SourceField
  /** Regex pattern */
  pattern: string
  /** Replacement template */
  replacement: string
  /** Callback when source field changes */
  onSourceFieldChange: (field: SourceField) => void
  /** Callback when pattern changes */
  onPatternChange: (pattern: string) => void
  /** Callback when replacement changes */
  onReplacementChange: (replacement: string) => void
  /** Whether the inputs are disabled */
  disabled?: boolean
  /** Pattern validation error */
  patternError?: string
}

// ============================================================================
// Component
// ============================================================================

/**
 * Input component for Regex mode - allows configuring a regex transformation
 * with source field, pattern, and replacement template.
 */
export function RegexModeInput({
  tag,
  sourceField,
  pattern,
  replacement,
  onSourceFieldChange,
  onPatternChange,
  onReplacementChange,
  disabled = false,
  patternError,
}: RegexModeInputProps) {
  const sourceFieldId = `regex-source-${tag}`
  const patternId = `regex-pattern-${tag}`
  const replacementId = `regex-replacement-${tag}`

  return (
    <div className="space-y-3">
      {/* Source Field Selector */}
      <div className="space-y-1.5">
        <Label htmlFor={sourceFieldId} className="text-xs text-muted-foreground">
          Source Field
        </Label>
        <Select
          value={sourceField}
          onValueChange={(value) => onSourceFieldChange(value as SourceField)}
          disabled={disabled}
        >
          <SelectTrigger id={sourceFieldId} className="h-8">
            <SelectValue placeholder="Select source field" />
          </SelectTrigger>
          <SelectContent>
            {SOURCE_FIELDS.map((field) => (
              <SelectItem key={field} value={field}>
                {SOURCE_FIELD_LABELS[field]}
              </SelectItem>
            ))}
          </SelectContent>
        </Select>
        <p className="text-xs text-muted-foreground">
          The field to apply the regex pattern to.
        </p>
      </div>

      {/* Pattern Input */}
      <div className="space-y-1.5">
        <Label htmlFor={patternId} className="text-xs text-muted-foreground">
          Regex Pattern
        </Label>
        <Input
          id={patternId}
          type="text"
          value={pattern}
          onChange={(e) => onPatternChange(e.target.value)}
          placeholder="e.g., ^(\d+)\s*[-_]\s*(.+)\.mp3$"
          disabled={disabled}
          className={`h-8 font-mono text-sm ${patternError ? 'border-destructive' : ''}`}
        />
        {patternError ? (
          <p className="text-xs text-destructive">{patternError}</p>
        ) : (
          <p className="text-xs text-muted-foreground">
            Python-compatible regex. Use capture groups () for extraction.
          </p>
        )}
      </div>

      {/* Replacement Template Input */}
      <div className="space-y-1.5">
        <Label htmlFor={replacementId} className="text-xs text-muted-foreground">
          Replacement Template
        </Label>
        <Input
          id={replacementId}
          type="text"
          value={replacement}
          onChange={(e) => onReplacementChange(e.target.value)}
          placeholder="e.g., $2"
          disabled={disabled}
          className="h-8 font-mono text-sm"
        />
        <p className="text-xs text-muted-foreground">
          Use $1, $2, etc. for captured groups. $0 = entire match.
        </p>
      </div>

      {/* Example */}
      <div className="rounded-md bg-muted/50 p-2 text-xs">
        <p className="font-medium mb-1">Example:</p>
        <p className="text-muted-foreground">
          Pattern: <code className="bg-muted px-1 rounded">^(\d+)\s*[-_]\s*(.+)\.mp3$</code>
        </p>
        <p className="text-muted-foreground">
          Input: <code className="bg-muted px-1 rounded">01 - My Song.mp3</code>
        </p>
        <p className="text-muted-foreground">
          Replacement <code className="bg-muted px-1 rounded">$2</code> = <code className="bg-muted px-1 rounded">My Song</code>
        </p>
      </div>
    </div>
  )
}

export default RegexModeInput
