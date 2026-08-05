import { useState } from 'react'
import { Loader2, AlertTriangle } from 'lucide-react'

import { Button } from '@/components/ui/button'
import { Checkbox } from '@/components/ui/checkbox'
import { Label } from '@/components/ui/label'
import {
  Dialog,
  DialogContent,
  DialogHeader,
  DialogTitle,
  DialogDescription,
  DialogFooter,
} from '@/components/ui/dialog'

import { type Library, type DeleteOptions, LibraryApiError } from '@/api/libraries'
import { useDeleteLibrary } from '@/hooks/useLibraries'

interface DeleteLibraryDialogProps {
  library: Library
  open: boolean
  onOpenChange: (open: boolean) => void
  onSuccess?: () => void
}

export default function DeleteLibraryDialog({
  library,
  open,
  onOpenChange,
  onSuccess,
}: DeleteLibraryDialogProps) {
  // Checkboxes default to CHECKED (keeping resources)
  const [keepConfig, setKeepConfig] = useState(true)
  const [keepDatabase, setKeepDatabase] = useState(true)
  const [keepFolders, setKeepFolders] = useState(true)
  const [error, setError] = useState<string | null>(null)

  const deleteMutation = useDeleteLibrary()

  // Check if any resources will be deleted
  const willDeleteResources = !keepConfig || !keepDatabase || !keepFolders

  const handleDelete = async () => {
    setError(null)
    const options: DeleteOptions = {
      keep_config: keepConfig,
      keep_database: keepDatabase,
      keep_folders: keepFolders,
    }

    try {
      await deleteMutation.mutateAsync({ slug: library.slug, options })
      // Reset state, call success callback, and close dialog
      resetState()
      onSuccess?.()
      onOpenChange(false)
    } catch (err) {
      if (err instanceof LibraryApiError) {
        setError(err.message)
      } else {
        setError('Failed to delete library. Please try again.')
      }
    }
  }

  const resetState = () => {
    setKeepConfig(true)
    setKeepDatabase(true)
    setKeepFolders(true)
    setError(null)
  }

  const handleOpenChange = (isOpen: boolean) => {
    if (!isOpen) {
      resetState()
    }
    onOpenChange(isOpen)
  }

  return (
    <Dialog open={open} onOpenChange={handleOpenChange}>
      <DialogContent className="sm:max-w-md">
        <DialogHeader>
          <DialogTitle className="flex items-center gap-2">
            <AlertTriangle className="h-5 w-5 text-destructive" />
            Delete Library
          </DialogTitle>
          <DialogDescription>
            Are you sure you want to delete "{library.name}"? The library record
            will be removed from the database.
          </DialogDescription>
        </DialogHeader>

        <div className="space-y-4 py-4">
          {/* Error message */}
          {error && (
            <div className="p-3 text-sm text-destructive bg-destructive/10 rounded-md border border-destructive/20">
              {error}
            </div>
          )}

          {/* Resource options */}
          <div className="space-y-4">
            <p className="text-sm text-muted-foreground">
              Select which resources to keep. Unchecked items will be permanently deleted.
            </p>

            <div className="space-y-3">
              <div className="flex items-center space-x-3">
                <Checkbox
                  id="keep-config"
                  checked={keepConfig}
                  onCheckedChange={(checked) => setKeepConfig(checked as boolean)}
                />
                <Label htmlFor="keep-config" className="text-sm cursor-pointer">
                  Keep configuration file
                  <span className="block text-xs text-muted-foreground">
                    {library.config_path}
                  </span>
                </Label>
              </div>

              <div className="flex items-center space-x-3">
                <Checkbox
                  id="keep-database"
                  checked={keepDatabase}
                  onCheckedChange={(checked) => setKeepDatabase(checked as boolean)}
                />
                <Label htmlFor="keep-database" className="text-sm cursor-pointer">
                  Keep database file
                  <span className="block text-xs text-muted-foreground">
                    {library.database_path}
                  </span>
                </Label>
              </div>

              <div className="flex items-center space-x-3">
                <Checkbox
                  id="keep-folders"
                  checked={keepFolders}
                  onCheckedChange={(checked) => setKeepFolders(checked as boolean)}
                />
                <Label htmlFor="keep-folders" className="text-sm cursor-pointer">
                  Keep library and import folders
                  <span className="block text-xs text-muted-foreground">
                    {library.library_path} &amp; {library.import_path}
                  </span>
                </Label>
              </div>
            </div>
          </div>

          {/* Warning message when resources will be deleted */}
          {willDeleteResources && (
            <div className="p-3 text-sm bg-amber-500/10 text-amber-700 dark:text-amber-400 rounded-md border border-amber-500/20">
              <strong>Warning:</strong> The unchecked resources will be permanently
              deleted and cannot be recovered.
            </div>
          )}
        </div>

        <DialogFooter className="gap-2 sm:gap-0">
          <Button
            variant="outline"
            onClick={() => handleOpenChange(false)}
            disabled={deleteMutation.isPending}
          >
            Cancel
          </Button>
          <Button
            variant="destructive"
            onClick={handleDelete}
            disabled={deleteMutation.isPending}
          >
            {deleteMutation.isPending && (
              <Loader2 className="h-4 w-4 mr-2 animate-spin" />
            )}
            Delete Library
          </Button>
        </DialogFooter>
      </DialogContent>
    </Dialog>
  )
}
