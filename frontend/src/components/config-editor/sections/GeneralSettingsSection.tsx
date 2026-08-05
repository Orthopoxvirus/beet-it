import { useState } from 'react'
import { Folder, AlertTriangle, Loader2, CheckCircle } from 'lucide-react'
import { UseFormReturn } from 'react-hook-form'

import { Button } from '@/components/ui/button'
import { Input } from '@/components/ui/input'
import { Label } from '@/components/ui/label'
import { Switch } from '@/components/ui/switch'
import {
  Dialog,
  DialogContent,
  DialogHeader,
  DialogTitle,
} from '@/components/ui/dialog'
import {
  Tooltip,
  TooltipContent,
  TooltipProvider,
  TooltipTrigger,
} from '@/components/ui/tooltip'
import { Alert, AlertDescription } from '@/components/ui/alert'
import FileTreeBrowser from '../FileTreeBrowser'
import type { BeetsConfig } from '@/types/beets-config'
import { useLibraryPathStatus, useInitializeLibrary } from '@/hooks/useConfig'

interface GeneralSettingsSectionProps {
  form: UseFormReturn<BeetsConfig>
  libraryId?: number
}

type PathField = 'directory' | 'library'

/**
 * Warning icon component that displays a tooltip when path doesn't exist
 */
function PathWarningIcon({ message }: { message: string }) {
  return (
    <TooltipProvider>
      <Tooltip>
        <TooltipTrigger asChild>
          <AlertTriangle
            className="h-4 w-4 text-yellow-500 shrink-0"
            aria-label="Warning"
          />
        </TooltipTrigger>
        <TooltipContent>
          <p>{message}</p>
        </TooltipContent>
      </Tooltip>
    </TooltipProvider>
  )
}

export default function GeneralSettingsSection({
  form,
  libraryId,
}: GeneralSettingsSectionProps) {
  const [browsingField, setBrowsingField] = useState<PathField | null>(null)
  const [tempSelectedPath, setTempSelectedPath] = useState<string>('')
  const [initMessage, setInitMessage] = useState<{
    type: 'success' | 'error'
    text: string
  } | null>(null)

  const { watch, setValue, register } = form
  const directory = watch('directory')
  const library = watch('library')

  // Fetch path status when libraryId is provided
  const {
    data: pathStatus,
    isLoading: isLoadingPathStatus,
    error: pathStatusError,
  } = useLibraryPathStatus(libraryId)

  // Initialize library mutation
  const initializeMutation = useInitializeLibrary()

  const handleOpenBrowser = (field: PathField) => {
    const currentValue = field === 'directory' ? directory : library
    setTempSelectedPath(currentValue || '/')
    setBrowsingField(field)
  }

  const handleSelectPath = () => {
    if (browsingField && tempSelectedPath) {
      if (browsingField === 'library') {
        // For library, we want the full path including filename
        // If selecting a directory, append the default database name
        const path = tempSelectedPath.endsWith('.db')
          ? tempSelectedPath
          : `${tempSelectedPath}/library.db`
        setValue('library', path, { shouldDirty: true })
      } else {
        setValue('directory', tempSelectedPath, { shouldDirty: true })
      }
      setBrowsingField(null)
    }
  }

  const handleInitialize = async () => {
    if (!libraryId) return

    setInitMessage(null)

    try {
      const result = await initializeMutation.mutateAsync(libraryId)
      setInitMessage({
        type: 'success',
        text: result.message,
      })
    } catch (error) {
      setInitMessage({
        type: 'error',
        text:
          error instanceof Error
            ? error.message
            : 'Failed to initialize library resources',
      })
    }
  }

  // Determine if we should show the Initialize button
  const showInitializeButton =
    libraryId &&
    pathStatus &&
    (!pathStatus.directoryExists || !pathStatus.databaseExists)

  // Show warning indicators based on path status
  const showDirectoryWarning =
    libraryId && pathStatus && !pathStatus.directoryExists
  const showDatabaseWarning =
    libraryId && pathStatus && !pathStatus.databaseExists

  return (
    <div className="space-y-6">
      {/* Directory Path */}
      <div className="space-y-2">
        <Label htmlFor="directory">Library Directory</Label>
        <p className="text-xs text-muted-foreground">
          The directory where your organized music files are stored
        </p>
        <div className="flex gap-2 items-center">
          <Input
            id="directory"
            {...register('directory')}
            placeholder="/data/libraries/my-music"
            className="font-mono text-sm"
          />
          <Button
            type="button"
            variant="outline"
            size="icon"
            onClick={() => handleOpenBrowser('directory')}
            title="Browse for directory"
          >
            <Folder className="h-4 w-4" />
          </Button>
          {showDirectoryWarning && (
            <PathWarningIcon message="Directory does not exist on disk" />
          )}
        </div>
      </div>

      {/* Database Path */}
      <div className="space-y-2">
        <Label htmlFor="library">Database File</Label>
        <p className="text-xs text-muted-foreground">
          Path to the beets SQLite database file
        </p>
        <div className="flex gap-2 items-center">
          <Input
            id="library"
            {...register('library')}
            placeholder="/data/databases/library.db"
            className="font-mono text-sm"
          />
          <Button
            type="button"
            variant="outline"
            size="icon"
            onClick={() => handleOpenBrowser('library')}
            title="Browse for database location"
          >
            <Folder className="h-4 w-4" />
          </Button>
          {showDatabaseWarning && (
            <PathWarningIcon message="Database file does not exist on disk" />
          )}
        </div>
      </div>

      {/* Initialize Button Section */}
      {showInitializeButton && (
        <div className="space-y-3 p-4 border rounded-lg bg-muted/30">
          <div className="flex items-start gap-2">
            <AlertTriangle className="h-5 w-5 text-yellow-500 shrink-0 mt-0.5" />
            <div className="space-y-1">
              <p className="text-sm font-medium">
                Library resources need initialization
              </p>
              <p className="text-xs text-muted-foreground">
                {!pathStatus.directoryExists && !pathStatus.databaseExists
                  ? 'Both the library directory and database file are missing.'
                  : !pathStatus.directoryExists
                    ? 'The library directory does not exist.'
                    : 'The database file does not exist.'}
              </p>
            </div>
          </div>
          <Button
            type="button"
            variant="secondary"
            onClick={handleInitialize}
            disabled={initializeMutation.isPending}
            className="w-full"
          >
            {initializeMutation.isPending ? (
              <>
                <Loader2 className="h-4 w-4 mr-2 animate-spin" />
                Initializing...
              </>
            ) : (
              'Initialize Library Resources'
            )}
          </Button>
        </div>
      )}

      {/* Initialization Status Message */}
      {initMessage && (
        <Alert variant={initMessage.type === 'success' ? 'default' : 'destructive'}>
          {initMessage.type === 'success' ? (
            <CheckCircle className="h-4 w-4" />
          ) : (
            <AlertTriangle className="h-4 w-4" />
          )}
          <AlertDescription>{initMessage.text}</AlertDescription>
        </Alert>
      )}

      {/* Path Status Loading/Error State */}
      {libraryId && isLoadingPathStatus && (
        <div className="flex items-center gap-2 text-xs text-muted-foreground">
          <Loader2 className="h-3 w-3 animate-spin" />
          Checking path status...
        </div>
      )}

      {libraryId && pathStatusError && (
        <p className="text-xs text-destructive">
          Failed to check path status:{' '}
          {pathStatusError instanceof Error
            ? pathStatusError.message
            : 'Unknown error'}
        </p>
      )}

      {/* Art Filename */}
      <div className="space-y-2">
        <Label htmlFor="art_filename">Art Filename</Label>
        <p className="text-xs text-muted-foreground">
          Filename for album artwork (without extension)
        </p>
        <Input
          id="art_filename"
          {...register('art_filename')}
          placeholder="albumart"
        />
      </div>

      {/* Toggles */}
      <div className="space-y-4 pt-4 border-t">
        <h4 className="text-sm font-medium">Options</h4>

        <div className="flex items-center justify-between">
          <div className="space-y-0.5">
            <Label htmlFor="threaded">Threaded Operations</Label>
            <p className="text-xs text-muted-foreground">
              Enable multi-threaded import processing
            </p>
          </div>
          <Switch
            id="threaded"
            checked={watch('threaded')}
            onCheckedChange={(checked) => setValue('threaded', checked, { shouldDirty: true })}
          />
        </div>

        <div className="flex items-center justify-between">
          <div className="space-y-0.5">
            <Label htmlFor="original_date">Use Original Date</Label>
            <p className="text-xs text-muted-foreground">
              Use original release date instead of re-release date
            </p>
          </div>
          <Switch
            id="original_date"
            checked={watch('original_date')}
            onCheckedChange={(checked) => setValue('original_date', checked, { shouldDirty: true })}
          />
        </div>

        <div className="flex items-center justify-between">
          <div className="space-y-0.5">
            <Label htmlFor="per_disc_numbering">Per-Disc Track Numbers</Label>
            <p className="text-xs text-muted-foreground">
              Number tracks per disc instead of across album
            </p>
          </div>
          <Switch
            id="per_disc_numbering"
            checked={watch('per_disc_numbering')}
            onCheckedChange={(checked) =>
              setValue('per_disc_numbering', checked, { shouldDirty: true })
            }
          />
        </div>
      </div>

      {/* Path Browser Dialog */}
      <Dialog
        open={browsingField !== null}
        onOpenChange={(open) => !open && setBrowsingField(null)}
      >
        <DialogContent className="sm:max-w-lg">
          <DialogHeader>
            <DialogTitle>
              {browsingField === 'directory'
                ? 'Select Library Directory'
                : 'Select Database Location'}
            </DialogTitle>
          </DialogHeader>
          <FileTreeBrowser
            initialPath={
              browsingField === 'directory'
                ? directory || '/data/libraries'
                : library
                ? library.substring(0, library.lastIndexOf('/'))
                : '/data/databases'
            }
            selectedPath={tempSelectedPath}
            onSelect={setTempSelectedPath}
          />
          <div className="flex justify-end gap-2 pt-4">
            <Button
              type="button"
              variant="outline"
              onClick={() => setBrowsingField(null)}
            >
              Cancel
            </Button>
            <Button
              type="button"
              onClick={handleSelectPath}
              disabled={!tempSelectedPath}
            >
              Select
            </Button>
          </div>
        </DialogContent>
      </Dialog>
    </div>
  )
}
