import { useState } from 'react'
import { Folder } from 'lucide-react'
import { UseFormReturn } from 'react-hook-form'

import { Button } from '@/components/ui/button'
import { Input } from '@/components/ui/input'
import { Label } from '@/components/ui/label'
import { Switch } from '@/components/ui/switch'
import {
  Select,
  SelectContent,
  SelectItem,
  SelectTrigger,
  SelectValue,
} from '@/components/ui/select'
import {
  Dialog,
  DialogContent,
  DialogHeader,
  DialogTitle,
} from '@/components/ui/dialog'
import FileTreeBrowser from '../FileTreeBrowser'
import type { BeetsConfig } from '@/types/beets-config'

interface ImportSettingsSectionProps {
  form: UseFormReturn<BeetsConfig>
}

export default function ImportSettingsSection({
  form,
}: ImportSettingsSectionProps) {
  const [showLogBrowser, setShowLogBrowser] = useState(false)
  const [tempLogPath, setTempLogPath] = useState<string>('')

  const { watch, setValue, register } = form
  const importConfig = watch('import')

  const handleSelectLogPath = () => {
    if (tempLogPath) {
      // Append a default log filename if selecting a directory
      const path = tempLogPath.endsWith('.log')
        ? tempLogPath
        : `${tempLogPath}/import.log`
      setValue('import.log', path, { shouldDirty: true })
      setShowLogBrowser(false)
    }
  }

  return (
    <div className="space-y-6">
      {/* Copy/Move Strategy */}
      <div className="space-y-4">
        <h4 className="text-sm font-medium">File Strategy</h4>
        <p className="text-xs text-muted-foreground">
          Choose how files are handled during import
        </p>

        <div className="grid grid-cols-2 gap-4">
          <div
            className={`p-4 border rounded-md cursor-pointer transition-colors ${
              importConfig.copy && !importConfig.move
                ? 'border-primary bg-primary/5'
                : 'hover:bg-muted/50'
            }`}
            onClick={() => {
              setValue('import.copy', true, { shouldDirty: true })
              setValue('import.move', false, { shouldDirty: true })
            }}
          >
            <div className="font-medium text-sm">Copy</div>
            <p className="text-xs text-muted-foreground mt-1">
              Copy files to library, keep originals
            </p>
          </div>

          <div
            className={`p-4 border rounded-md cursor-pointer transition-colors ${
              importConfig.move
                ? 'border-primary bg-primary/5'
                : 'hover:bg-muted/50'
            }`}
            onClick={() => {
              setValue('import.copy', false, { shouldDirty: true })
              setValue('import.move', true, { shouldDirty: true })
            }}
          >
            <div className="font-medium text-sm">Move</div>
            <p className="text-xs text-muted-foreground mt-1">
              Move files to library, remove originals
            </p>
          </div>
        </div>
      </div>

      {/* Import Options */}
      <div className="space-y-4 pt-4 border-t">
        <h4 className="text-sm font-medium">Import Options</h4>

        <div className="flex items-center justify-between">
          <div className="space-y-0.5">
            <Label htmlFor="import-write">Write Metadata</Label>
            <p className="text-xs text-muted-foreground">
              Write metadata tags to audio files
            </p>
          </div>
          <Switch
            id="import-write"
            checked={importConfig.write}
            onCheckedChange={(checked) => setValue('import.write', checked, { shouldDirty: true })}
          />
        </div>

        <div
          className="flex items-center justify-between opacity-50 cursor-not-allowed"
          title="Not supported - album-by-album imports do not require resume functionality"
        >
          <div className="space-y-0.5">
            <Label htmlFor="import-resume">Resume Imports</Label>
            <p className="text-xs text-muted-foreground">
              Resume interrupted import operations
            </p>
          </div>
          <Switch
            id="import-resume"
            checked={importConfig.resume}
            onCheckedChange={(checked) => setValue('import.resume', checked, { shouldDirty: true })}
            disabled
          />
        </div>

        <div
          className="flex items-center justify-between opacity-50 cursor-not-allowed"
          title="Not supported - album-by-album imports do not require incremental functionality"
        >
          <div className="space-y-0.5">
            <Label htmlFor="import-incremental">Incremental Import</Label>
            <p className="text-xs text-muted-foreground">
              Skip already-imported directories
            </p>
          </div>
          <Switch
            id="import-incremental"
            checked={importConfig.incremental}
            onCheckedChange={(checked) =>
              setValue('import.incremental', checked, { shouldDirty: true })
            }
            disabled
          />
        </div>

        <div
          className="flex items-center justify-between opacity-50 cursor-not-allowed"
          title="Not supported yet"
        >
          <div className="space-y-0.5">
            <Label htmlFor="import-timid">Timid Mode</Label>
            <p className="text-xs text-muted-foreground">
              Always confirm before auto-tagging
            </p>
          </div>
          <Switch
            id="import-timid"
            checked={importConfig.timid}
            onCheckedChange={(checked) => setValue('import.timid', checked, { shouldDirty: true })}
            disabled
          />
        </div>
      </div>

      {/* Quiet Fallback */}
      <div className="space-y-2">
        <Label htmlFor="quiet-fallback">Quiet Fallback</Label>
        <p className="text-xs text-muted-foreground">
          Action when quiet mode cannot find a match
        </p>
        <Select
          value={importConfig.quiet_fallback}
          onValueChange={(value: 'skip' | 'asis') =>
            setValue('import.quiet_fallback', value, { shouldDirty: true })
          }
        >
          <SelectTrigger id="quiet-fallback">
            <SelectValue placeholder="Select fallback action" />
          </SelectTrigger>
          <SelectContent>
            <SelectItem value="skip">Skip - Do not import</SelectItem>
            <SelectItem value="asis">As-Is - Import without tagging</SelectItem>
          </SelectContent>
        </Select>
      </div>

      {/* Log Path */}
      <div className="space-y-2">
        <Label htmlFor="import-log">Import Log Path</Label>
        <p className="text-xs text-muted-foreground">
          Path to the import log file (optional)
        </p>
        <div className="flex gap-2">
          <Input
            id="import-log"
            {...register('import.log')}
            placeholder="/data/logs/import.log"
            className="font-mono text-sm"
          />
          <Button
            type="button"
            variant="outline"
            size="icon"
            onClick={() => {
              setTempLogPath(importConfig.log || '/data/logs')
              setShowLogBrowser(true)
            }}
            title="Browse for log location"
          >
            <Folder className="h-4 w-4" />
          </Button>
        </div>
      </div>

      {/* Log Path Browser Dialog */}
      <Dialog open={showLogBrowser} onOpenChange={setShowLogBrowser}>
        <DialogContent className="sm:max-w-lg">
          <DialogHeader>
            <DialogTitle>Select Log File Location</DialogTitle>
          </DialogHeader>
          <FileTreeBrowser
            initialPath={tempLogPath || '/data/logs'}
            selectedPath={tempLogPath}
            onSelect={setTempLogPath}
          />
          <div className="flex justify-end gap-2 pt-4">
            <Button
              type="button"
              variant="outline"
              onClick={() => setShowLogBrowser(false)}
            >
              Cancel
            </Button>
            <Button
              type="button"
              onClick={handleSelectLogPath}
              disabled={!tempLogPath}
            >
              Select
            </Button>
          </div>
        </DialogContent>
      </Dialog>
    </div>
  )
}
