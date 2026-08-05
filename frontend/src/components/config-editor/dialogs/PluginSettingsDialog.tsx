import { ReactNode } from 'react'
import { ExternalLink } from 'lucide-react'

import { Button } from '@/components/ui/button'
import {
  Dialog,
  DialogContent,
  DialogDescription,
  DialogFooter,
  DialogHeader,
  DialogTitle,
} from '@/components/ui/dialog'
import { getPluginMetadata } from '@/data/plugin-metadata'

interface PluginSettingsDialogProps {
  open: boolean
  onOpenChange: (open: boolean) => void
  pluginName: string
  onSave: () => void
  onCancel: () => void
  children: ReactNode
}

/**
 * Base wrapper dialog for plugin settings.
 * Provides consistent header, footer, and layout for all plugin dialogs.
 */
export default function PluginSettingsDialog({
  open,
  onOpenChange,
  pluginName,
  onSave,
  onCancel,
  children,
}: PluginSettingsDialogProps) {
  const metadata = getPluginMetadata(pluginName)

  const handleCancel = () => {
    onCancel()
    onOpenChange(false)
  }

  const handleSave = () => {
    onSave()
    onOpenChange(false)
  }

  return (
    <Dialog open={open} onOpenChange={onOpenChange}>
      <DialogContent className="sm:max-w-lg">
        <DialogHeader>
          <DialogTitle className="capitalize">{pluginName} Settings</DialogTitle>
          <DialogDescription className="flex items-center gap-2">
            {metadata.description}
            <a
              href={metadata.docsUrl}
              target="_blank"
              rel="noopener noreferrer"
              className="inline-flex items-center gap-1 text-primary hover:underline shrink-0"
              aria-label={`View ${pluginName} documentation (opens in new tab)`}
            >
              <ExternalLink className="h-3 w-3" />
              Docs
            </a>
          </DialogDescription>
        </DialogHeader>

        <div className="py-4 space-y-4">{children}</div>

        <DialogFooter>
          <Button type="button" variant="outline" onClick={handleCancel}>
            Cancel
          </Button>
          <Button type="button" onClick={handleSave}>
            Apply
          </Button>
        </DialogFooter>
      </DialogContent>
    </Dialog>
  )
}
