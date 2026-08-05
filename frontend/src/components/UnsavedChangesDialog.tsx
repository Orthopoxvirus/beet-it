import { AlertTriangle } from 'lucide-react'

import {
  AlertDialog,
  AlertDialogAction,
  AlertDialogCancel,
  AlertDialogContent,
  AlertDialogDescription,
  AlertDialogFooter,
  AlertDialogHeader,
  AlertDialogTitle,
} from '@/components/ui/alert-dialog'
import { buttonVariants } from '@/components/ui/button'
import { cn } from '@/lib/utils'

export interface UnsavedChangesDialogProps {
  /**
   * Whether the dialog is open
   */
  open: boolean
  /**
   * Callback when user chooses to stay on the page
   */
  onStay: () => void
  /**
   * Callback when user chooses to leave and discard changes
   */
  onLeave: () => void
}

/**
 * A confirmation dialog shown when attempting to navigate away with unsaved changes.
 *
 * Uses AlertDialog from shadcn/ui which is semantically correct for confirmation dialogs.
 * Provides "Stay" and "Leave" options for the user.
 *
 * @example
 * ```tsx
 * <UnsavedChangesDialog
 *   open={isBlocked}
 *   onStay={() => blocker.reset?.()}
 *   onLeave={() => blocker.proceed?.()}
 * />
 * ```
 */
export function UnsavedChangesDialog({
  open,
  onStay,
  onLeave,
}: UnsavedChangesDialogProps) {
  return (
    <AlertDialog open={open}>
      <AlertDialogContent>
        <AlertDialogHeader>
          <AlertDialogTitle className="flex items-center gap-2">
            <AlertTriangle className="h-5 w-5 text-amber-500" />
            Unsaved Changes
          </AlertDialogTitle>
          <AlertDialogDescription>
            You have unsaved changes. Are you sure you want to leave? Your changes will be lost.
          </AlertDialogDescription>
        </AlertDialogHeader>
        <AlertDialogFooter>
          <AlertDialogCancel onClick={onStay}>Stay</AlertDialogCancel>
          <AlertDialogAction
            onClick={onLeave}
            className={cn(buttonVariants({ variant: 'destructive' }))}
          >
            Leave
          </AlertDialogAction>
        </AlertDialogFooter>
      </AlertDialogContent>
    </AlertDialog>
  )
}
