import { useState } from 'react'
import { Loader2, FolderPlus } from 'lucide-react'

import { Button } from '@/components/ui/button'
import { Input } from '@/components/ui/input'
import { Label } from '@/components/ui/label'
import {
  Dialog,
  DialogContent,
  DialogDescription,
  DialogFooter,
  DialogHeader,
  DialogTitle,
} from '@/components/ui/dialog'

interface FolderCreationDialogProps {
  open: boolean
  onOpenChange: (open: boolean) => void
  parentPath: string
  onCreateFolder: (name: string) => Promise<void>
  isCreating?: boolean
}

export default function FolderCreationDialog({
  open,
  onOpenChange,
  parentPath,
  onCreateFolder,
  isCreating = false,
}: FolderCreationDialogProps) {
  const [folderName, setFolderName] = useState('')
  const [error, setError] = useState<string | null>(null)

  const handleCreate = async () => {
    if (!folderName.trim()) {
      setError('Folder name is required')
      return
    }

    // Validate folder name
    if (folderName.includes('/') || folderName.includes('\\')) {
      setError('Folder name cannot contain path separators')
      return
    }

    if (folderName.startsWith('.') && folderName.length === 1) {
      setError('Invalid folder name')
      return
    }

    try {
      setError(null)
      await onCreateFolder(folderName.trim())
      setFolderName('')
      onOpenChange(false)
    } catch (err) {
      setError(err instanceof Error ? err.message : 'Failed to create folder')
    }
  }

  const handleClose = () => {
    setFolderName('')
    setError(null)
    onOpenChange(false)
  }

  return (
    <Dialog open={open} onOpenChange={handleClose}>
      <DialogContent className="sm:max-w-md">
        <DialogHeader>
          <DialogTitle className="flex items-center gap-2">
            <FolderPlus className="h-5 w-5" />
            Create New Folder
          </DialogTitle>
          <DialogDescription>
            Create a new folder in <code className="text-xs bg-muted px-1 py-0.5 rounded">{parentPath}</code>
          </DialogDescription>
        </DialogHeader>

        <div className="space-y-4 py-4">
          <div className="space-y-2">
            <Label htmlFor="folder-name">Folder Name</Label>
            <Input
              id="folder-name"
              value={folderName}
              onChange={(e) => {
                setFolderName(e.target.value)
                setError(null)
              }}
              placeholder="new-folder"
              disabled={isCreating}
              onKeyDown={(e) => {
                if (e.key === 'Enter' && !isCreating) {
                  e.preventDefault()
                  handleCreate()
                }
              }}
            />
            {error && (
              <p className="text-sm text-destructive">{error}</p>
            )}
          </div>
        </div>

        <DialogFooter>
          <Button
            type="button"
            variant="outline"
            onClick={handleClose}
            disabled={isCreating}
          >
            Cancel
          </Button>
          <Button
            type="button"
            onClick={handleCreate}
            disabled={isCreating || !folderName.trim()}
          >
            {isCreating && <Loader2 className="h-4 w-4 mr-2 animate-spin" />}
            Create
          </Button>
        </DialogFooter>
      </DialogContent>
    </Dialog>
  )
}
