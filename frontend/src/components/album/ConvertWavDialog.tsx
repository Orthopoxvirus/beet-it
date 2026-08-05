import { useEffect, useState } from 'react'
import { AlertCircle, CheckCircle2, FileAudio, Loader2 } from 'lucide-react'

import { Button } from '@/components/ui/button'
import { Checkbox } from '@/components/ui/checkbox'
import {
  Dialog,
  DialogContent,
  DialogDescription,
  DialogFooter,
  DialogHeader,
  DialogTitle,
} from '@/components/ui/dialog'

import { useConvertAlbumWav } from '@/hooks/useAlbums'
import { AlbumApiError } from '@/api/albums'
import type { AudioOpResult } from '@/types/beets-import'

export interface ConvertWavDialogProps {
  /** Library slug. */
  slug: string
  /** Beets album ID. */
  albumId: number
  /** Album title (for the confirmation copy). */
  albumTitle: string
  /** Album artist (for the confirmation copy). */
  albumArtist: string
  /** Number of WAV tracks that will be converted. */
  wavTrackCount: number
  /** Whether the dialog is currently open. */
  isOpen: boolean
  /** Close handler. */
  onClose: () => void
}

/**
 * Dialog that confirms and runs an in-place WAV→FLAC conversion for an
 * already-imported album.
 *
 * Unlike the fire-and-forget move dialog, this one stays open while the
 * conversion runs (the mutation polls the job to completion) and shows the
 * per-file outcome, since the user is usually waiting to see the album flip
 * to FLAC.
 */
export function ConvertWavDialog({
  slug,
  albumId,
  albumTitle,
  albumArtist,
  wavTrackCount,
  isOpen,
  onClose,
}: ConvertWavDialogProps) {
  const convertMutation = useConvertAlbumWav()

  const [deleteOriginals, setDeleteOriginals] = useState(true)
  const [errorMessage, setErrorMessage] = useState<string | null>(null)
  const [result, setResult] = useState<AudioOpResult | null>(null)

  // Reset state whenever the dialog opens. convertMutation must NOT be in the
  // deps — its identity changes on every render, so listing it would re-fire
  // this effect constantly and wipe the checkbox state.
  // eslint-disable-next-line react-hooks/exhaustive-deps
  useEffect(() => {
    if (isOpen) {
      setDeleteOriginals(true)
      setErrorMessage(null)
      setResult(null)
      convertMutation.reset()
    }
  }, [isOpen])

  const handleConvert = async () => {
    setErrorMessage(null)
    try {
      const opResult = await convertMutation.mutateAsync({
        slug,
        albumId,
        deleteOriginals,
      })
      setResult(opResult)
    } catch (err) {
      const message =
        err instanceof AlbumApiError
          ? err.message
          : err instanceof Error
            ? err.message
            : 'Failed to convert album.'
      setErrorMessage(message)
    }
  }

  const isConverting = convertMutation.isPending
  const failedCount = result?.failed ?? 0

  return (
    <Dialog
      open={isOpen}
      onOpenChange={(open) => {
        if (!open && !isConverting) {
          onClose()
        }
      }}
    >
      <DialogContent className="max-w-[calc(100vw-2rem)] sm:max-w-[480px]">
        <DialogHeader>
          <DialogTitle className="flex items-center gap-2">
            <FileAudio className="h-5 w-5" />
            Convert WAV to FLAC
          </DialogTitle>
          <DialogDescription>
            {wavTrackCount} WAV track{wavTrackCount !== 1 ? 's' : ''} of{' '}
            <span className="font-medium text-foreground">
              {albumArtist} — {albumTitle}
            </span>{' '}
            will be losslessly transcoded to FLAC in place. The library entry
            is updated to point at the new files — no re-import needed.
          </DialogDescription>
        </DialogHeader>

        <div className="space-y-3 py-2">
          {!result && (
            <label className="flex items-center gap-2 text-sm cursor-pointer">
              <Checkbox
                checked={deleteOriginals}
                onCheckedChange={(checked) => setDeleteOriginals(checked === true)}
                disabled={isConverting}
                data-testid="delete-originals-checkbox"
              />
              Delete original WAV files after conversion
            </label>
          )}

          {isConverting && (
            <div className="flex items-center gap-2 text-sm text-muted-foreground">
              <Loader2 className="h-4 w-4 animate-spin" />
              Converting… this can take a while for long tracks.
            </div>
          )}

          {result && (
            <div
              role="status"
              className={`flex items-start gap-2 rounded-md border p-3 text-sm ${
                failedCount > 0
                  ? 'border-destructive/50 bg-destructive/10 text-destructive'
                  : 'border-green-600/50 bg-green-600/10 text-green-700 dark:text-green-400'
              }`}
            >
              {failedCount > 0 ? (
                <AlertCircle className="mt-0.5 h-4 w-4 shrink-0" />
              ) : (
                <CheckCircle2 className="mt-0.5 h-4 w-4 shrink-0" />
              )}
              <span>
                {result.converted ?? 0} track
                {(result.converted ?? 0) !== 1 ? 's' : ''} converted
                {(result.skipped ?? 0) > 0 && `, ${result.skipped} skipped`}
                {(result.deleted ?? 0) > 0 && `, ${result.deleted} WAVs deleted`}
                {failedCount > 0 && `, ${failedCount} failed`}.
              </span>
            </div>
          )}

          {errorMessage && (
            <div
              role="alert"
              className="flex items-start gap-2 rounded-md border border-destructive/50 bg-destructive/10 p-3 text-sm text-destructive"
            >
              <AlertCircle className="mt-0.5 h-4 w-4 shrink-0" />
              <span>{errorMessage}</span>
            </div>
          )}

          {!result && (
            <p className="text-xs text-muted-foreground">
              A WAV whose FLAC twin already exists is skipped, and each WAV is
              only removed after its FLAC has been verified.
            </p>
          )}
        </div>

        <DialogFooter>
          {result ? (
            <Button onClick={onClose} data-testid="convert-dialog-close">
              Close
            </Button>
          ) : (
            <>
              <Button variant="outline" onClick={onClose} disabled={isConverting}>
                Cancel
              </Button>
              <Button onClick={handleConvert} disabled={isConverting}>
                {isConverting && <Loader2 className="mr-2 h-4 w-4 animate-spin" />}
                Convert to FLAC
              </Button>
            </>
          )}
        </DialogFooter>
      </DialogContent>
    </Dialog>
  )
}
