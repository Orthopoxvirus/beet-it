import {
  Dialog,
  DialogContent,
  DialogHeader,
  DialogTitle,
  DialogDescription,
} from '@/components/ui/dialog'

import { type Library } from '@/api/libraries'

interface LibraryInfoModalProps {
  library: Library | null
  open: boolean
  onOpenChange: (open: boolean) => void
}

export function LibraryInfoModal({ library, open, onOpenChange }: LibraryInfoModalProps) {
  if (!library) return null

  const formatDate = (dateString: string | null) => {
    if (!dateString) return 'Not set'
    return new Date(dateString).toLocaleDateString()
  }

  return (
    <Dialog open={open} onOpenChange={onOpenChange}>
      <DialogContent className="sm:max-w-lg">
        <DialogHeader>
          <DialogTitle>{library.name}</DialogTitle>
          <DialogDescription>
            {library.description || 'No description set'}
          </DialogDescription>
        </DialogHeader>
        <div className="space-y-4">
          <div>
            <h4 className="text-sm font-medium text-muted-foreground">Library Path</h4>
            <p className="text-sm break-all">{library.library_path}</p>
          </div>
          <div>
            <h4 className="text-sm font-medium text-muted-foreground">Config Path</h4>
            <p className="text-sm break-all">{library.config_path}</p>
          </div>
          <div>
            <h4 className="text-sm font-medium text-muted-foreground">Database Path</h4>
            <p className="text-sm break-all">{library.database_path}</p>
          </div>
          <div>
            <h4 className="text-sm font-medium text-muted-foreground">Import Path</h4>
            <p className="text-sm break-all">{library.import_path}</p>
          </div>
          <div className="grid grid-cols-2 gap-4">
            <div>
              <h4 className="text-sm font-medium text-muted-foreground">Created</h4>
              <p className="text-sm">{formatDate(library.created_at)}</p>
            </div>
            <div>
              <h4 className="text-sm font-medium text-muted-foreground">Updated</h4>
              <p className="text-sm">{formatDate(library.updated_at)}</p>
            </div>
          </div>
        </div>
      </DialogContent>
    </Dialog>
  )
}
