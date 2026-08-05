import { UseFormReturn } from 'react-hook-form'

import { Input } from '@/components/ui/input'
import { Label } from '@/components/ui/label'
import { Switch } from '@/components/ui/switch'
import type { BeetsConfig } from '@/types/beets-config'

interface ConvertSettingsSectionProps {
  form: UseFormReturn<BeetsConfig>
}

export default function ConvertSettingsSection({
  form,
}: ConvertSettingsSectionProps) {
  const { watch, setValue, register } = form
  const convert = watch('convert')

  return (
    <div className="space-y-6">
      <div className="space-y-2">
        <h4 className="text-sm font-medium">Convert Plugin</h4>
        <p className="text-xs text-muted-foreground">
          Settings for transcoding audio files during import or on-demand
        </p>
      </div>

      {/* Auto Convert Toggle */}
      <div className="flex items-center justify-between p-4 border rounded-md bg-muted/30">
        <div className="space-y-0.5">
          <Label htmlFor="convert-auto" className="text-base">
            Auto Convert on Import
          </Label>
          <p className="text-xs text-muted-foreground">
            Automatically convert files when importing to the library
          </p>
        </div>
        <Switch
          id="convert-auto"
          checked={convert.auto}
          onCheckedChange={(checked) => setValue('convert.auto', checked, { shouldDirty: true })}
        />
      </div>

      {/* FFmpeg Path */}
      <div className="space-y-2">
        <Label htmlFor="convert-ffmpeg">FFmpeg Path</Label>
        <p className="text-xs text-muted-foreground">
          Path to the ffmpeg binary
        </p>
        <Input
          id="convert-ffmpeg"
          {...register('convert.ffmpeg')}
          placeholder="/usr/bin/ffmpeg"
          className="font-mono text-sm"
        />
      </div>

      {/* FFmpeg Options */}
      <div className="space-y-2">
        <Label htmlFor="convert-opts">FFmpeg Output Options</Label>
        <p className="text-xs text-muted-foreground">
          Command-line options passed to ffmpeg for encoding
        </p>
        <Input
          id="convert-opts"
          {...register('convert.opts')}
          placeholder="-ab 320k -ac 2 -ar 48000"
          className="font-mono text-sm"
        />
        <p className="text-xs text-muted-foreground">
          Example: <code className="bg-muted px-1 rounded">-ab 320k</code> for
          320kbps bitrate, <code className="bg-muted px-1 rounded">-ac 2</code>{' '}
          for stereo, <code className="bg-muted px-1 rounded">-ar 48000</code>{' '}
          for 48kHz sample rate
        </p>
      </div>

      {/* Max Bitrate */}
      <div className="space-y-2">
        <Label htmlFor="convert-max-bitrate">Max Bitrate (kbps)</Label>
        <p className="text-xs text-muted-foreground">
          Maximum bitrate for converted files. Files already below this
          threshold will not be converted.
        </p>
        <Input
          id="convert-max-bitrate"
          type="number"
          min={64}
          max={512}
          value={convert.max_bitrate}
          onChange={(e) =>
            setValue('convert.max_bitrate', parseInt(e.target.value) || 320, { shouldDirty: true })
          }
          placeholder="320"
          className="w-32"
        />
      </div>

      {/* Threads */}
      <div className="space-y-2">
        <Label htmlFor="convert-threads">Conversion Threads</Label>
        <p className="text-xs text-muted-foreground">
          Number of parallel conversion threads (1 for single-threaded)
        </p>
        <Input
          id="convert-threads"
          type="number"
          min={1}
          max={16}
          value={convert.threads}
          onChange={(e) =>
            setValue('convert.threads', parseInt(e.target.value) || 1, { shouldDirty: true })
          }
          placeholder="1"
          className="w-32"
        />
      </div>
    </div>
  )
}
