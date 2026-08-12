// ============================================================================
// Manual Mode (track_number) — explanation panel
// ============================================================================
//
// Manual mode has no inputs of its own: the per-track number inputs and the
// drag handles live in the Local Album table below, and their values feed the
// explicit rule this editor sends. This panel just tells the user where to go.

/**
 * Explanation shown when Track Number is set to Manual mode. The actual
 * editing happens on the Local Album track rows.
 */
export function ManualModeInput() {
  return (
    <div className="rounded-md bg-muted/50 p-2 text-xs space-y-1">
      <p className="font-medium">Manual Numbering:</p>
      <p className="text-muted-foreground">
        Edit the track numbers directly in the Local Album table below, or drag
        table rows to reorder. Typing a number moves the track to that position
        and shifts the others; the table re-sorts as you go. Apply Changes
        writes the numbers shown in the inputs.
      </p>
    </div>
  )
}

export default ManualModeInput
