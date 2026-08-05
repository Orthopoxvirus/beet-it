const API_URL = import.meta.env.VITE_API_URL || '/api'

// ============================================================================
// TypeScript Types
// ============================================================================

/**
 * Theme mode options
 * - "light": Always use light theme
 * - "dark": Always use dark theme
 * - "system": Match OS theme preference
 */
export type ThemeMode = 'light' | 'dark' | 'system'

/**
 * User preferences stored in the backend
 * Extensible - new settings will be added as additional fields
 */
export interface UserSettingsPreferences {
  themeMode: ThemeMode
}

/**
 * Full user settings response from the API
 */
export interface UserSettingsResponse {
  id: number
  preferences: UserSettingsPreferences
  createdAt: string
  updatedAt: string
}

/**
 * Request body for updating user settings
 */
export interface UserSettingsUpdate {
  preferences: Partial<UserSettingsPreferences>
}

/**
 * API error response
 */
export interface SettingsApiError {
  detail: string
}

// ============================================================================
// API Response Types (snake_case from backend)
// ============================================================================

interface ApiPreferences {
  theme_mode: ThemeMode
}

interface ApiSettingsResponse {
  id: number
  preferences: ApiPreferences
  created_at: string
  updated_at: string
}

interface ApiSettingsUpdate {
  preferences: {
    theme_mode?: ThemeMode
  }
}

// ============================================================================
// Error Handling
// ============================================================================

export class SettingsApiError extends Error {
  status: number

  constructor(message: string, status: number) {
    super(message)
    this.name = 'SettingsApiError'
    this.status = status
  }
}

async function handleResponse<T>(response: Response): Promise<T> {
  if (!response.ok) {
    let errorMessage = 'An unknown error occurred'
    try {
      const errorData = await response.json()
      errorMessage = errorData.detail || errorMessage
    } catch {
      // Response body may not be JSON
    }
    throw new SettingsApiError(errorMessage, response.status)
  }
  return response.json()
}

// ============================================================================
// Transform Functions
// ============================================================================

/**
 * Transform API response to frontend format (snake_case -> camelCase)
 */
function transformResponse(data: ApiSettingsResponse): UserSettingsResponse {
  return {
    id: data.id,
    preferences: {
      themeMode: data.preferences.theme_mode,
    },
    createdAt: data.created_at,
    updatedAt: data.updated_at,
  }
}

/**
 * Transform frontend update to API format (camelCase -> snake_case)
 */
function transformUpdate(data: UserSettingsUpdate): ApiSettingsUpdate {
  return {
    preferences: {
      ...(data.preferences.themeMode !== undefined && {
        theme_mode: data.preferences.themeMode,
      }),
    },
  }
}

// ============================================================================
// API Client Functions
// ============================================================================

/**
 * Fetch the current user's settings
 * Creates default settings if none exist
 */
export async function getSettings(): Promise<UserSettingsResponse> {
  const response = await fetch(`${API_URL}/v1/settings`)
  const data = await handleResponse<ApiSettingsResponse>(response)
  return transformResponse(data)
}

/**
 * Update the user's settings
 * Performs partial update - only provided fields are updated
 */
export async function updateSettings(
  update: UserSettingsUpdate
): Promise<UserSettingsResponse> {
  const response = await fetch(`${API_URL}/v1/settings`, {
    method: 'PUT',
    headers: {
      'Content-Type': 'application/json',
    },
    body: JSON.stringify(transformUpdate(update)),
  })
  const data = await handleResponse<ApiSettingsResponse>(response)
  return transformResponse(data)
}
