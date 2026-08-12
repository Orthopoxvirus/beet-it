import { useState, useCallback, useMemo, useEffect } from 'react'
import { Wand2, Loader2, AlertCircle, CheckCircle, ChevronDown, ChevronRight } from 'lucide-react'

import { Button } from '@/components/ui/button'
import { Card, CardContent, CardHeader, CardTitle } from '@/components/ui/card'
import { Progress } from '@/components/ui/progress'
import {
  Dialog,
  DialogContent,
  DialogDescription,
  DialogFooter,
  DialogHeader,
  DialogTitle,
} from '@/components/ui/dialog'

import { TagFieldConfig } from './TagFieldConfig'
import { useTagPreview, useDebouncedValue } from '@/hooks/useTagPreview'
import { useBatchTagUpdate } from '@/hooks/useBatchTagUpdate'

import type {
  TagName,
  TagFieldState,
  BatchTagFormState,
  TransformationRule,
  FixedRule,
  RegexRule,
  SequenceRule,
  ExplicitRule,
  ItemPreview,
} from '@/types/batch-tag-editor'
import { EDITABLE_TAGS } from '@/types/batch-tag-editor'

// ============================================================================
// Types
// ============================================================================

interface BatchTagEditorFormProps {
  /** Library slug */
  librarySlug: string
  /** Item IDs to transform */
  itemIds: number[]
  /** Callback when preview data changes */
  onPreviewChange?: (previewMap: Map<number, ItemPreview>) => void
  /** Whether the form is disabled */
  disabled?: boolean
  /** Make the card header a collapse toggle (chevron in the header). */
  collapsible?: boolean
  /** Initial collapsed state when {@link collapsible} is set. */
  defaultCollapsed?: boolean
  /**
   * Item-id → track-number map from the Local Album table's Manual mode
   * (typed numbers / drag reorder). Feeds the explicit rule while the
   * Track Number field is set to Manual.
   */
  manualTrackNumbers?: Record<number, string>
  /**
   * Notifies the parent when Track Number enters/leaves Manual mode, so the
   * track table can show/hide its number inputs and drag handles.
   */
  onTrackNumberManualChange?: (manual: boolean) => void
}

// ============================================================================
// Initial State
// ============================================================================

function createInitialFieldState(): TagFieldState {
  return {
    enabled: false,
    mode: null,
    fixedValue: '',
    sourceField: 'filename',
    pattern: '',
    replacement: '',
    sequenceStart: 1,
    perDirectory: false,
  }
}

function createInitialFormState(): BatchTagFormState {
  const state: Partial<BatchTagFormState> = {}
  for (const tag of EDITABLE_TAGS) {
    state[tag] = createInitialFieldState()
  }
  return state as BatchTagFormState
}

// ============================================================================
// Rule Building
// ============================================================================

function buildRulesFromState(
  formState: BatchTagFormState,
  manualTrackNumbers?: Record<number, string>
): TransformationRule[] {
  const rules: TransformationRule[] = []

  for (const tag of EDITABLE_TAGS) {
    const fieldState = formState[tag]
    if (!fieldState.enabled || !fieldState.mode) {
      continue
    }

    switch (fieldState.mode) {
      case 'fixed':
        rules.push({
          tag,
          mode: 'fixed',
          value: fieldState.fixedValue || '',
        } as FixedRule)
        break

      case 'regex':
        if (fieldState.pattern && fieldState.sourceField) {
          rules.push({
            tag,
            mode: 'regex',
            source_field: fieldState.sourceField,
            pattern: fieldState.pattern,
            replacement: fieldState.replacement || '',
          } as RegexRule)
        }
        break

      case 'sequence':
        if (tag === 'track_number') {
          rules.push({
            tag: 'track_number',
            mode: 'sequence',
            start: fieldState.sequenceStart ?? 1,
            per_directory: fieldState.perDirectory ?? false,
          } as SequenceRule)
        }
        break

      case 'explicit':
        // Manual mode: the values come from the Local Album table (typed
        // numbers / drag reorder), not from this form. No edits yet → no rule.
        if (
          tag === 'track_number' &&
          manualTrackNumbers &&
          Object.keys(manualTrackNumbers).length > 0
        ) {
          rules.push({
            tag: 'track_number',
            mode: 'explicit',
            values: manualTrackNumbers,
          } as ExplicitRule)
        }
        break
    }
  }

  return rules
}

// ============================================================================
// Component
// ============================================================================

export function BatchTagEditorForm({
  librarySlug,
  itemIds,
  onPreviewChange,
  disabled: externalDisabled = false,
  collapsible = false,
  defaultCollapsed = false,
  manualTrackNumbers,
  onTrackNumberManualChange,
}: BatchTagEditorFormProps) {
  // Collapse state (only meaningful when `collapsible`)
  const [isCollapsed, setIsCollapsed] = useState(collapsible && defaultCollapsed)

  // Form state
  const [formState, setFormState] = useState<BatchTagFormState>(createInitialFormState())

  // Confirmation dialog
  const [showConfirmDialog, setShowConfirmDialog] = useState(false)

  // Build rules from form state
  const rules = useMemo(
    () => buildRulesFromState(formState, manualTrackNumbers),
    [formState, manualTrackNumbers]
  )

  // Tell the parent when Track Number enters/leaves Manual mode, so the track
  // table can switch its number inputs and drag handles on/off.
  const isTrackNumberManual =
    formState.track_number.enabled && formState.track_number.mode === 'explicit'
  useEffect(() => {
    onTrackNumberManualChange?.(isTrackNumberManual)
  }, [isTrackNumberManual, onTrackNumberManualChange])

  // Debounce rules for preview (300ms)
  const debouncedRules = useDebouncedValue(rules, 300)

  // Preview hook
  const {
    isFetching: isPreviewFetching,
    error: previewError,
    previewMap,
    hasChanges,
  } = useTagPreview(librarySlug, itemIds, debouncedRules, {
    enabled: itemIds.length > 0 && debouncedRules.length > 0,
  })

  // Batch update hook
  const {
    state: updateState,
    execute: executeUpdate,
    reset: resetUpdate,
  } = useBatchTagUpdate({
    onCompleted: () => {
      // Close dialog but preserve form configuration
      setShowConfirmDialog(false)
    },
    onError: () => {
      setShowConfirmDialog(false)
    },
  })

  // Notify parent of preview changes
  useEffect(() => {
    onPreviewChange?.(previewMap)
  }, [previewMap, onPreviewChange])

  // Handle field state change
  const handleFieldChange = useCallback((tag: TagName, state: TagFieldState) => {
    // Clear completion status when user makes new changes (to allow re-applying)
    if (updateState.isComplete) {
      resetUpdate()
    }
    setFormState((prev) => ({
      ...prev,
      [tag]: state,
    }))
  }, [updateState.isComplete, resetUpdate])

  // Handle apply click
  const handleApplyClick = useCallback(() => {
    setShowConfirmDialog(true)
  }, [])

  // Handle confirm apply
  const handleConfirmApply = useCallback(() => {
    if (rules.length > 0 && itemIds.length > 0) {
      executeUpdate(librarySlug, itemIds, rules)
    }
  }, [executeUpdate, librarySlug, itemIds, rules])

  // Handle reset
  const handleReset = useCallback(() => {
    setFormState(createInitialFormState())
    resetUpdate()
  }, [resetUpdate])

  // Count enabled fields
  const enabledFieldCount = useMemo(
    () => Object.values(formState).filter((f) => f.enabled).length,
    [formState]
  )

  // Derived states
  const isDisabled = externalDisabled || updateState.isUpdating
  const canApply = hasChanges && rules.length > 0 && itemIds.length > 0 && !updateState.isUpdating

  // Render update progress
  const renderUpdateProgress = () => {
    if (!updateState.isUpdating && !updateState.isComplete) {
      return null
    }

    return (
      <div className="space-y-2 p-4 rounded-md bg-muted/50">
        {updateState.isUpdating ? (
          <>
            <div className="flex items-center gap-2 text-sm">
              <Loader2 className="h-4 w-4 animate-spin" />
              <span>
                Applying changes... {updateState.itemsProcessed} / {updateState.itemsTotal}
              </span>
            </div>
            <Progress value={updateState.progress} />
          </>
        ) : updateState.isComplete ? (
          <div className="space-y-2">
            <div className="flex items-center gap-2 text-sm">
              {updateState.itemsFailed === 0 ? (
                <>
                  <CheckCircle className="h-4 w-4 text-green-500" />
                  <span className="text-green-700 dark:text-green-400">
                    Successfully updated {updateState.itemsSucceeded} track{updateState.itemsSucceeded !== 1 ? 's' : ''}
                  </span>
                </>
              ) : (
                <>
                  <AlertCircle className="h-4 w-4 text-amber-500" />
                  <span className="text-amber-700 dark:text-amber-400">
                    {updateState.itemsSucceeded} succeeded, {updateState.itemsFailed} failed
                  </span>
                </>
              )}
            </div>
            {updateState.itemsFailed > 0 && (
              <div className="text-xs text-muted-foreground max-h-24 overflow-y-auto">
                {updateState.results
                  .filter((r) => r.status === 'failed')
                  .map((r) => (
                    <div key={r.itemId}>
                      Item {r.itemId}: {r.error?.message || 'Unknown error'}
                    </div>
                  ))}
              </div>
            )}
            <p className="text-xs text-muted-foreground">
              Configuration preserved. Modify settings or use Reset to clear.
            </p>
          </div>
        ) : null}
      </div>
    )
  }

  return (
    <>
      <Card>
        {/* Header — a collapse toggle when `collapsible`, otherwise static */}
        <CardHeader>
          {collapsible ? (
            <button
              type="button"
              onClick={() => setIsCollapsed((v) => !v)}
              className="flex items-center gap-2 hover:text-foreground transition-colors"
              aria-expanded={!isCollapsed}
            >
              {isCollapsed ? (
                <ChevronRight className="h-4 w-4 text-muted-foreground" />
              ) : (
                <ChevronDown className="h-4 w-4 text-muted-foreground" />
              )}
              <Wand2 className="h-5 w-5 text-primary" />
              <CardTitle className="text-lg">Batch Tag Editor</CardTitle>
            </button>
          ) : (
            <div className="flex items-center gap-2">
              <Wand2 className="h-5 w-5 text-primary" />
              <CardTitle className="text-lg">Batch Tag Editor</CardTitle>
            </div>
          )}
        </CardHeader>

        {/* Content */}
        {!isCollapsed && (
        <CardContent className="space-y-4">
          {/* Empty state message */}
          {itemIds.length === 0 && (
            <div className="text-center py-4 text-muted-foreground">
              Select a folder with tracks to enable batch editing.
            </div>
          )}

          {/* Update progress */}
          {renderUpdateProgress()}

          {/* Tag field configurations */}
          {itemIds.length > 0 && (
            <>
              <div className="grid grid-cols-1 md:grid-cols-2 gap-3">
                {EDITABLE_TAGS.map((tag) => (
                  <TagFieldConfig
                    key={tag}
                    tag={tag}
                    state={formState[tag]}
                    onChange={(state) => handleFieldChange(tag, state)}
                    disabled={isDisabled}
                    allowManualTrackNumbers={!!onTrackNumberManualChange}
                  />
                ))}
              </div>

              {/* Preview loading indicator */}
              {isPreviewFetching && (
                <div className="flex items-center gap-2 text-sm text-muted-foreground">
                  <Loader2 className="h-3 w-3 animate-spin" />
                  <span>Loading preview...</span>
                </div>
              )}

              {/* Preview error */}
              {previewError && (
                <div className="flex items-center gap-2 text-sm text-destructive">
                  <AlertCircle className="h-4 w-4" />
                  <span>Preview error: {previewError.message}</span>
                </div>
              )}

              {/* Actions */}
              <div className="flex items-center justify-between pt-2 border-t">
                <div className="text-sm text-muted-foreground">
                  {hasChanges && previewMap.size > 0 && (
                    <span>
                      Preview: {previewMap.size} track{previewMap.size !== 1 ? 's' : ''} will be modified
                    </span>
                  )}
                </div>
                <div className="flex gap-2">
                  <Button
                    variant="outline"
                    size="sm"
                    onClick={handleReset}
                    disabled={isDisabled || enabledFieldCount === 0}
                  >
                    Reset
                  </Button>
                  <Button
                    size="sm"
                    onClick={handleApplyClick}
                    disabled={!canApply}
                  >
                    Apply Changes
                  </Button>
                </div>
              </div>
            </>
          )}
        </CardContent>
        )}
      </Card>

      {/* Confirmation Dialog */}
      <Dialog open={showConfirmDialog} onOpenChange={setShowConfirmDialog}>
        <DialogContent>
          <DialogHeader>
            <DialogTitle>Apply Tag Changes?</DialogTitle>
            <DialogDescription>
              This will apply the configured transformations to {itemIds.length} track{itemIds.length !== 1 ? 's' : ''}.
              The changes will be written to both the database and the audio files.
            </DialogDescription>
          </DialogHeader>

          <div className="py-4">
            <p className="text-sm font-medium mb-2">Changes to apply:</p>
            <ul className="text-sm text-muted-foreground space-y-1">
              {rules.map((rule, index) => (
                <li key={index}>
                  <span className="font-medium">{rule.tag}</span>:{' '}
                  {rule.mode === 'explicit' ? 'manual' : rule.mode} mode
                </li>
              ))}
            </ul>
          </div>

          <DialogFooter>
            <Button
              variant="outline"
              onClick={() => setShowConfirmDialog(false)}
              disabled={updateState.isUpdating}
            >
              Cancel
            </Button>
            <Button
              onClick={handleConfirmApply}
              disabled={updateState.isUpdating}
            >
              {updateState.isUpdating ? (
                <>
                  <Loader2 className="h-4 w-4 mr-2 animate-spin" />
                  Applying...
                </>
              ) : (
                'Apply Changes'
              )}
            </Button>
          </DialogFooter>
        </DialogContent>
      </Dialog>
    </>
  )
}

export default BatchTagEditorForm
