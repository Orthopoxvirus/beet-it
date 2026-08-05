import { useQuery, useMutation, useQueryClient } from '@tanstack/react-query'
import {
  getSettings,
  updateSettings,
  type UserSettingsUpdate,
} from '@/api/settings'

// Query keys for cache management
export const settingsKeys = {
  all: ['settings'] as const,
  detail: () => [...settingsKeys.all, 'detail'] as const,
}

// ============================================================================
// Query Hooks
// ============================================================================

/**
 * Hook to fetch user settings
 * Uses TanStack Query for caching and refetching
 */
export function useSettings() {
  return useQuery({
    queryKey: settingsKeys.detail(),
    queryFn: getSettings,
    // Settings don't change often, keep them cached longer
    staleTime: 10 * 60 * 1000, // 10 minutes
    // Don't retry too aggressively for settings
    retry: 1,
  })
}

// ============================================================================
// Mutation Hooks
// ============================================================================

/**
 * Hook to update user settings
 * Automatically invalidates the settings cache on success
 */
export function useUpdateSettings() {
  const queryClient = useQueryClient()

  return useMutation({
    mutationFn: (data: UserSettingsUpdate) => updateSettings(data),
    onSuccess: (updatedSettings) => {
      // Update the cache with the new settings
      queryClient.setQueryData(settingsKeys.detail(), updatedSettings)
    },
    onError: (error) => {
      // Log error for debugging but let the caller handle it
      console.error('Failed to update settings:', error)
    },
  })
}
