import { useState, useCallback, useMemo, useEffect } from 'react'
import { Wand2, Loader2, AlertCircle, CheckCircle } from 'lucide-react'

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

import { TagFieldConfig } from '@/components/batch-editor'
import { useLibraryItemsPreview, useLibraryBatchTagUpdate } from '@/hooks/useLibraryItems'
import { useDebouncedValue } from '@/hooks/useTagPreview'

import type {
  TagName,
  TagFieldState,
  BatchTagFormState,
  TransformationRule,
  FixedRule,
  RegexRule,
  SequenceRule,
  ItemPreview,
} from '@/types/batch-tag-editor'
import { EDITABLE_TAGS } from '@/types/batch-tag-editor'

// ============================================================================
// Types
// ============================================================================

interface LibraryBatchTagEditorFormProps {
  /** Library slug */
  librarySlug: string
  /** Item IDs to transform */
  itemIds: number[]
  /** Callback when preview data changes */
  onPreviewChange?: (previewMap: Map<number, ItemPreview>) => void
  /** Callback when batch update completes with job ID for status polling */
  onBatchUpdateComplete?: (jobId: string, albumsToSync: string[]) => void
  /** Whether the form is disabled */
  disabled?: boolean
  /**
   * Extra rules contributed by another surface (the reorder feature's explicit
   * track-number / title rules). Merged with the form's own rules for preview
   * and commit so a single "Apply Changes" covers both.
   */
  extraRules?: TransformationRule[]
  /** How many tracks the extra rules change — for the preview summary line. */
  extraChangedItemCount?: number
  /**
   * A "use as template" seed from the Distinct values card. When `token`
   * changes, the named field is switched to Fixed-Value mode with `value`,
   * overwriting any existing config for that tag (last action wins).
   */
  seedFixedValue?: { tag: TagName; value: string; token: number } | null
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

function buildRulesFromState(formState: BatchTagFormState): TransformationRule[] {
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
    }
  }

  return rules
}

// ============================================================================
// Component
// ============================================================================

export default function LibraryBatchTagEditorForm({
  librarySlug,
  itemIds,
  onPreviewChange,
  onBatchUpdateComplete,
  disabled: externalDisabled = false,
  extraRules = [],
  extraChangedItemCount = 0,
  seedFixedValue,
}: LibraryBatchTagEditorFormProps) {
  // Form state
  const [formState, setFormState] = useState<BatchTagFormState>(createInitialFormState())

  // Confirmation dialog
  const [showConfirmDialog, setShowConfirmDialog] = useState(false)

  // Build rules from form state
  const rules = useMemo(() => buildRulesFromState(formState), [formState])

  // Rules actually committed: the form's own rules plus any externally supplied
  // ones (the reorder feature's explicit rules). The form's *preview* still
  // runs on its own rules only — the reorder preview is merged in upstream and
  // is computed client-side, so there's no need to round-trip the explicit
  // rules through the preview endpoint on every drag.
  const allRules = useMemo(() => [...rules, ...extraRules], [rules, extraRules])

  // Debounce rules for preview (300ms)
  const debouncedRules = useDebouncedValue(rules, 300)

  // Preview hook - uses library items API
  const {
    isFetching: isPreviewFetching,
    error: previewError,
    previewMap,
    hasChanges,
  } = useLibraryItemsPreview(librarySlug, itemIds, debouncedRules, {
    enabled: itemIds.length > 0 && debouncedRules.length > 0,
  })

  // Batch update hook - uses library items API
  const {
    state: updateState,
    execute: executeUpdate,
    reset: resetUpdate,
  } = useLibraryBatchTagUpdate({
    onCompleted: (data) => {
      // Close dialog but preserve form configuration
      setShowConfirmDialog(false)
      // Notify parent with job ID for status polling
      if (data.jobId) {
        onBatchUpdateComplete?.(data.jobId, data.albumsToSync || [])
      }
    },
    onError: () => {
      setShowConfirmDialog(false)
    },
  })

  // Notify parent of preview changes
  useEffect(() => {
    onPreviewChange?.(previewMap)
  }, [previewMap, onPreviewChange])

  // Seed a field into Fixed-Value mode from the Distinct values card's
  // "use as template" arrow. Keyed on the seed token so repeated clicks of
  // the same value re-apply; overwrites any existing config for that tag
  // (last action wins). Mirrors handleFieldChange's completion-reset so a
  // freshly-seeded change can be applied right after a finished run.
  const seedToken = seedFixedValue?.token
  useEffect(() => {
    if (!seedFixedValue) return
    const { tag, value } = seedFixedValue
    setFormState((prev) => ({
      ...prev,
      [tag]: { ...prev[tag], enabled: true, mode: 'fixed', fixedValue: value },
    }))
    if (updateState.isComplete) {
      resetUpdate()
    }
    // Fire only on a new seed token, not on unrelated state churn.
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [seedToken])

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
    if (allRules.length > 0 && itemIds.length > 0) {
      executeUpdate(librarySlug, itemIds, allRules)
    }
  }, [executeUpdate, librarySlug, itemIds, allRules])

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
  // Apply is enabled when the form has previewed changes, OR when a reorder has
  // contributed explicit rules (those only exist when something actually moved).
  const canApply =
    itemIds.length > 0 &&
    !updateState.isUpdating &&
    ((hasChanges && rules.length > 0) || extraRules.length > 0)

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
            {updateState.albumsToSync.length > 0 && (
              <p className="text-xs text-muted-foreground">
                Syncing changes to beets database for {updateState.albumsToSync.length} album{updateState.albumsToSync.length !== 1 ? 's' : ''}...
              </p>
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
        {/* Header */}
        <CardHeader>
          <div className="flex items-center gap-2">
            <Wand2 className="h-5 w-5 text-primary" />
            <CardTitle className="text-lg">Batch Tag Editor</CardTitle>
          </div>
        </CardHeader>

        {/* Content */}
        <CardContent className="space-y-4">
          {/* Empty state message */}
          {itemIds.length === 0 && (
            <div className="text-center py-4 text-muted-foreground">
              Select an album to enable batch editing.
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
                <div className="text-sm text-muted-foreground space-x-2">
                  {hasChanges && previewMap.size > 0 && (
                    <span>
                      Preview: {previewMap.size} track{previewMap.size !== 1 ? 's' : ''} will be modified
                    </span>
                  )}
                  {extraChangedItemCount > 0 && (
                    <span>
                      Reorder: {extraChangedItemCount} track{extraChangedItemCount !== 1 ? 's' : ''} renumbered
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
      </Card>

      {/* Confirmation Dialog */}
      <Dialog open={showConfirmDialog} onOpenChange={setShowConfirmDialog}>
        <DialogContent>
          <DialogHeader>
            <DialogTitle>Apply Tag Changes?</DialogTitle>
            <DialogDescription>
              This will apply the configured transformations to {itemIds.length} track{itemIds.length !== 1 ? 's' : ''}.
              The changes will be written to the audio files and synced to the beets database.
            </DialogDescription>
          </DialogHeader>

          <div className="py-4">
            <p className="text-sm font-medium mb-2">Changes to apply:</p>
            <ul className="text-sm text-muted-foreground space-y-1">
              {allRules.map((rule, index) => (
                <li key={index}>
                  <span className="font-medium">{rule.tag}</span>:{' '}
                  {rule.mode === 'explicit' ? 'reorder' : `${rule.mode} mode`}
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
