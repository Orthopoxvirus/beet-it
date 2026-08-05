import { Info } from 'lucide-react'

import { Input } from '@/components/ui/input'
import { Label } from '@/components/ui/label'
import {
  Tooltip,
  TooltipContent,
  TooltipProvider,
  TooltipTrigger,
} from '@/components/ui/tooltip'
import type { PermissionsConfig } from '@/types/beets-config'
import PluginSettingsDialog from './PluginSettingsDialog'

interface PermissionsSettingsDialogProps {
  open: boolean
  onOpenChange: (open: boolean) => void
  config: PermissionsConfig
  onSave: () => void
}

export default function PermissionsSettingsDialog({
  open,
  onOpenChange,
  config,
  onSave,
}: PermissionsSettingsDialogProps) {
  // Permissions are read-only, so no local state needed
  const handleSave = () => {
    onSave()
  }

  const handleCancel = () => {
    // No changes to discard
  }

  return (
    <PluginSettingsDialog
      open={open}
      onOpenChange={onOpenChange}
      pluginName="permissions"
      onSave={handleSave}
      onCancel={handleCancel}
    >
      {/* Info Banner */}
      <div className="flex items-start gap-3 p-4 border rounded-md bg-muted/30">
        <TooltipProvider>
          <Tooltip>
            <TooltipTrigger>
              <Info className="h-5 w-5 text-muted-foreground mt-0.5" />
            </TooltipTrigger>
            <TooltipContent side="right" className="max-w-xs">
              <p>
                These permissions are system-managed and cannot be changed
                through the UI. They ensure consistent file access across the
                application.
              </p>
            </TooltipContent>
          </Tooltip>
        </TooltipProvider>
        <div>
          <p className="text-sm font-medium">Read-only Settings</p>
          <p className="text-xs text-muted-foreground">
            Permission values are managed by the system and cannot be modified
            here.
          </p>
        </div>
      </div>

      {/* Permission Fields */}
      <div className="grid grid-cols-2 gap-4">
        <div className="space-y-2">
          <Label htmlFor="permissions-file">File Permissions</Label>
          <div className="flex items-center gap-2">
            <Input
              id="permissions-file"
              value={config.file}
              readOnly
              disabled
              className="w-24 font-mono text-sm bg-muted"
            />
            <span className="text-xs text-muted-foreground">
              (octal: {config.file.toString(8).padStart(3, '0')})
            </span>
          </div>
        </div>

        <div className="space-y-2">
          <Label htmlFor="permissions-dir">Directory Permissions</Label>
          <div className="flex items-center gap-2">
            <Input
              id="permissions-dir"
              value={config.dir}
              readOnly
              disabled
              className="w-24 font-mono text-sm bg-muted"
            />
            <span className="text-xs text-muted-foreground">
              (octal: {config.dir.toString(8).padStart(3, '0')})
            </span>
          </div>
        </div>
      </div>

      {/* Default Values Info */}
      <div className="pt-2 text-xs text-muted-foreground bg-muted/50 p-3 rounded-md">
        <p className="font-medium mb-1">Default values:</p>
        <ul className="space-y-1">
          <li>
            <code>664</code> (rw-rw-r--) for files - owner and group can
            read/write
          </li>
          <li>
            <code>775</code> (rwxrwxr-x) for directories - owner and group have
            full access
          </li>
        </ul>
      </div>
    </PluginSettingsDialog>
  )
}
