import { useEffect, useMemo, useState } from 'react'
import { ArrowRightLeft, AlertCircle, Loader2 } from 'lucide-react'

import { Button } from '@/components/ui/button'
import {
  Dialog,
  DialogContent,
  DialogDescription,
  DialogFooter,
  DialogHeader,
  DialogTitle,
} from '@/components/ui/dialog'
import {
  Select,
  SelectContent,
  SelectItem,
  SelectTrigger,
  SelectValue,
} from '@/components/ui/select'

import { useLibraries } from '@/hooks/useLibraries'
import { useMoveAlbumToLibrary } from '@/hooks/useAlbums'
import { AlbumApiError } from '@/api/albums'

export interface MoveAlbumDialogProps {
  /** Source library slug. */
  sourceSlug: string
  /** Beets album ID in the source library. */
  albumId: number
  /** Album title (for the confirmation copy). */
  albumTitle: string
  /** Album artist (for the confirmation copy). */
  albumArtist: string
  /** Whether the dialog is currently open. */
  isOpen: boolean
  /** Close handler. */
  onClose: () => void
  /**
   * Called after the move has been successfully queued (and after `onClose`).
   * Lets the caller decide where to go next: an overview can stay put (the
   * album list query is invalidated, so the row refreshes in place), while a
   * detail page — whose album is about to disappear — can navigate back to the
   * grid the user came from. Omit to do nothing.
   */
  onMoved?: () => void
}

/**
 * Dialog that picks a target library and queues a cross-library move.
 *
 * The move runs asynchronously: the source album_id disappears once the worker
 * runs and the target's new album_id isn't known until then. The dialog itself
 * doesn't navigate — it closes, then hands control to the optional `onMoved`
 * callback so the caller can decide the right destination for its context.
 */
export function MoveAlbumDialog({
  sourceSlug,
  albumId,
  albumTitle,
  albumArtist,
  isOpen,
  onClose,
  onMoved,
}: MoveAlbumDialogProps) {
  const { data: libraryListData, isLoading: isLoadingLibraries } = useLibraries()
  const moveMutation = useMoveAlbumToLibrary()

  const [targetSlug, setTargetSlug] = useState<string>('')
  const [errorMessage, setErrorMessage] = useState<string | null>(null)

  // Eligible targets = every library except the source.
  const targetLibraries = useMemo(() => {
    const items = libraryListData?.items ?? []
    return items.filter((lib) => lib.slug !== sourceSlug)
  }, [libraryListData, sourceSlug])

  // Reset state whenever the dialog opens. moveMutation must NOT be in the
  // deps — its identity changes on every render, so listing it would cause
  // this effect to re-fire after every keystroke / select-change and wipe
  // the user's selection back to "" within milliseconds.
  // eslint-disable-next-line react-hooks/exhaustive-deps
  useEffect(() => {
    if (isOpen) {
      setTargetSlug('')
      setErrorMessage(null)
      moveMutation.reset()
    }
  }, [isOpen])

  const handleSubmit = async () => {
    setErrorMessage(null)
    if (!targetSlug) {
      setErrorMessage('Pick a target library first.')
      return
    }
    try {
      await moveMutation.mutateAsync({
        slug: sourceSlug,
        albumId,
        targetLibrarySlug: targetSlug,
      })
      onClose()
      // The album row will vanish from the source DB once the worker runs.
      // Where to go next depends on the caller's context, so defer to it.
      onMoved?.()
    } catch (err) {
      const message =
        err instanceof AlbumApiError
          ? err.message
          : err instanceof Error
            ? err.message
            : 'Failed to queue album move.'
      setErrorMessage(message)
    }
  }

  const isSubmitting = moveMutation.isPending

  return (
    <Dialog
      open={isOpen}
      onOpenChange={(open) => {
        if (!open && !isSubmitting) {
          onClose()
        }
      }}
    >
      <DialogContent className="max-w-[calc(100vw-2rem)] sm:max-w-[480px]">
        <DialogHeader>
          <DialogTitle className="flex items-center gap-2">
            <ArrowRightLeft className="h-5 w-5" />
            Move Album
          </DialogTitle>
          <DialogDescription>
            Move{' '}
            <span className="font-medium text-foreground">
              {albumArtist} — {albumTitle}
            </span>{' '}
            to a different library. Files and the beets database entry are
            relocated; the source library will no longer have this album.
          </DialogDescription>
        </DialogHeader>

        <div className="space-y-3 py-2">
          <label className="text-sm font-medium" htmlFor="move-album-target">
            Target library
          </label>
          <Select
            value={targetSlug}
            onValueChange={setTargetSlug}
            disabled={isSubmitting || isLoadingLibraries}
          >
            <SelectTrigger id="move-album-target">
              <SelectValue
                placeholder={
                  isLoadingLibraries
                    ? 'Loading libraries…'
                    : targetLibraries.length === 0
                      ? 'No other libraries available'
                      : 'Pick a target library'
                }
              />
            </SelectTrigger>
            <SelectContent>
              {targetLibraries.map((lib) => (
                <SelectItem key={lib.slug} value={lib.slug}>
                  {lib.name}{' '}
                  <span className="text-muted-foreground">({lib.slug})</span>
                </SelectItem>
              ))}
            </SelectContent>
          </Select>

          {errorMessage && (
            <div
              role="alert"
              className="flex items-start gap-2 rounded-md border border-destructive/50 bg-destructive/10 p-3 text-sm text-destructive"
            >
              <AlertCircle className="mt-0.5 h-4 w-4 shrink-0" />
              <span>{errorMessage}</span>
            </div>
          )}

          <p className="text-xs text-muted-foreground">
            The actual move runs in the background — track its progress in the
            activity panel. Cover art, .nfo files, and any other extras in the
            album folder are moved along with the audio files.
          </p>
        </div>

        <DialogFooter>
          <Button
            variant="outline"
            onClick={onClose}
            disabled={isSubmitting}
          >
            Cancel
          </Button>
          <Button
            onClick={handleSubmit}
            disabled={
              isSubmitting || !targetSlug || targetLibraries.length === 0
            }
          >
            {isSubmitting && <Loader2 className="mr-2 h-4 w-4 animate-spin" />}
            Queue move
          </Button>
        </DialogFooter>
      </DialogContent>
    </Dialog>
  )
}
