import { useEffect } from 'react'
import { Sun, Moon, Monitor } from 'lucide-react'

import {
  Card,
  CardContent,
  CardDescription,
  CardHeader,
  CardTitle,
} from '@/components/ui/card'
import { Label } from '@/components/ui/label'
import { RadioGroup, RadioGroupItem } from '@/components/ui/radio-group'
import { useTheme, type ThemeMode } from '@/components/theme-provider'
import { useSettings, useUpdateSettings } from '@/hooks/useSettings'

const THEME_OPTIONS: { value: ThemeMode; label: string; description: string; icon: typeof Sun }[] = [
  {
    value: 'light',
    label: 'Light',
    description: 'Always use light theme',
    icon: Sun,
  },
  {
    value: 'dark',
    label: 'Dark',
    description: 'Always use dark theme',
    icon: Moon,
  },
  {
    value: 'system',
    label: 'System',
    description: 'Match your operating system preference',
    icon: Monitor,
  },
]

export default function SettingsPage() {
  const { themeMode, setThemeMode } = useTheme()
  const { data: settings, isLoading, error } = useSettings()
  const updateSettings = useUpdateSettings()

  // Sync theme mode from backend settings on load
  useEffect(() => {
    if (settings?.preferences?.themeMode) {
      const backendMode = settings.preferences.themeMode
      // Only update if different from current localStorage value
      if (backendMode !== themeMode) {
        setThemeMode(backendMode)
      }
    }
  }, [settings?.preferences?.themeMode]) // eslint-disable-line react-hooks/exhaustive-deps

  const handleThemeModeChange = (value: string) => {
    const newMode = value as ThemeMode
    // Update localStorage and UI immediately via ThemeProvider
    setThemeMode(newMode)

    // Sync to backend (fire and forget - don't block UI)
    updateSettings.mutate({
      preferences: { themeMode: newMode },
    })
  }

  return (
    <div className="space-y-6">
      <div>
        <h1 className="text-2xl font-bold">Settings</h1>
        <p className="text-muted-foreground">
          Manage your application preferences
        </p>
      </div>

      {/* Loading state */}
      {isLoading && (
        <div className="flex items-center justify-center py-12">
          <div className="animate-spin rounded-full h-8 w-8 border-b-2 border-primary"></div>
        </div>
      )}

      {/* Error state - show settings anyway since we have localStorage */}
      {!isLoading && error && (
        <div className="rounded-lg border border-destructive/50 bg-destructive/10 p-4">
          <p className="text-sm text-destructive">
            Failed to load settings from server. Your preferences are saved locally.
          </p>
        </div>
      )}

      {/* Theme settings card */}
      <Card>
        <CardHeader>
          <CardTitle>Appearance</CardTitle>
          <CardDescription>
            Customize how the application looks on your device
          </CardDescription>
        </CardHeader>
        <CardContent>
          <div className="space-y-4">
            <div className="space-y-2">
              <Label className="text-base">Theme</Label>
              <p className="text-sm text-muted-foreground">
                Select your preferred color theme
              </p>
            </div>

            <RadioGroup
              value={themeMode}
              onValueChange={handleThemeModeChange}
              className="grid gap-4"
            >
              {THEME_OPTIONS.map((option) => {
                const Icon = option.icon
                return (
                  <div key={option.value} className="flex items-start space-x-3">
                    <RadioGroupItem
                      value={option.value}
                      id={`theme-${option.value}`}
                      className="mt-1"
                    />
                    <div className="flex-1 space-y-1">
                      <Label
                        htmlFor={`theme-${option.value}`}
                        className="flex items-center gap-2 text-sm font-medium cursor-pointer"
                      >
                        <Icon className="h-4 w-4" />
                        {option.label}
                      </Label>
                      <p className="text-sm text-muted-foreground">
                        {option.description}
                      </p>
                    </div>
                  </div>
                )
              })}
            </RadioGroup>

            {/* Show saving indicator */}
            {updateSettings.isPending && (
              <p className="text-sm text-muted-foreground">Saving...</p>
            )}

            {/* Show sync error but don't block */}
            {updateSettings.isError && (
              <p className="text-sm text-destructive">
                Failed to sync to server. Your preference is saved locally.
              </p>
            )}
          </div>
        </CardContent>
      </Card>
    </div>
  )
}
