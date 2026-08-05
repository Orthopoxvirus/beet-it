import { z } from 'zod'

// ============================================================================
// Import Configuration
// ============================================================================

export const importConfigSchema = z.object({
  write: z.boolean().default(true),
  copy: z.boolean().default(true),
  move: z.boolean().default(false),
  resume: z
    .preprocess((v) => {
      if (typeof v === "boolean") return v
      if (typeof v === "string") {
        const lowered = v.trim().toLowerCase()
        if (lowered === "yes" || lowered === "true" || lowered === "ask") return true
        if (lowered === "no" || lowered === "false") return false
      }
      return v
    }, z.boolean())
    .default(true),
  incremental: z.boolean().default(false),
  quiet_fallback: z.enum(['skip', 'asis']).default('skip'),
  timid: z.boolean().default(false),
  log: z.string().nullable().default(null),
})

export type ImportConfig = z.infer<typeof importConfigSchema>

// ============================================================================
// Paths Configuration
// ============================================================================

export const pathsConfigSchema = z.object({
  default: z
    .string()
    .default('$albumartist/$album%aunique{}/%if{$multidisc,$disc-}$track - $title'),
  singleton: z.string().default('Singles/$artist - $title'),
  comp: z
    .string()
    .default('Compilations/$album%aunique{}/%if{$multidisc,$disc-}$track - $title'),
  albumtype_soundtrack: z
    .string()
    .default('Soundtracks/$album/%if{$multidisc,$disc-}$track $title'),
})

export type PathsConfig = z.infer<typeof pathsConfigSchema>

// ============================================================================
// Convert Configuration
// ============================================================================

export const convertConfigSchema = z.object({
  auto: z.boolean().default(false),
  ffmpeg: z.string().default('/usr/bin/ffmpeg'),
  opts: z.string().default('-ab 320k -ac 2 -ar 48000'),
  max_bitrate: z.number().default(320),
  threads: z.number().default(1),
})

export type ConvertConfig = z.infer<typeof convertConfigSchema>

// ============================================================================
// Plugin Configurations
// ============================================================================

export const lastgenreConfigSchema = z.object({
  auto: z.boolean().default(true),
  source: z.enum(['album', 'track']).default('album'),
})

export type LastgenreConfig = z.infer<typeof lastgenreConfigSchema>

export const embedartConfigSchema = z.object({
  auto: z.boolean().default(true),
})

export type EmbedartConfig = z.infer<typeof embedartConfigSchema>

export const fetchartConfigSchema = z.object({
  auto: z.boolean().default(true),
})

export type FetchartConfig = z.infer<typeof fetchartConfigSchema>

export const replaygainConfigSchema = z.object({
  auto: z.boolean().default(false),
})

export type ReplaygainConfig = z.infer<typeof replaygainConfigSchema>

export const scrubConfigSchema = z.object({
  auto: z.boolean().default(true),
})

export type ScrubConfig = z.infer<typeof scrubConfigSchema>

// ============================================================================
// Replace Configuration
// ============================================================================

export const replaceRuleSchema = z.object({
  pattern: z.string(),
  replacement: z.string(),
})

export type ReplaceRule = z.infer<typeof replaceRuleSchema>

export const replaceConfigSchema = z.array(replaceRuleSchema)

export type ReplaceConfig = z.infer<typeof replaceConfigSchema>

// ============================================================================
// Emby Configuration
// ============================================================================

export const embyConfigSchema = z.object({
  host: z.string().default(''),
  port: z.number().default(8096),
  userid: z.string().default(''),
  apikey: z.string().default(''),
})

export type EmbyConfig = z.infer<typeof embyConfigSchema>

// ============================================================================
// Discogs Configuration
// ============================================================================

export const discogsConfigSchema = z.object({
  user_token: z.string().default(''),
})

export type DiscogsConfig = z.infer<typeof discogsConfigSchema>

// ============================================================================
// Permissions Configuration
// ============================================================================

export const permissionsConfigSchema = z.object({
  file: z.number().default(664),
  dir: z.number().default(775),
})

export type PermissionsConfig = z.infer<typeof permissionsConfigSchema>

// ============================================================================
// Match Configuration
// ============================================================================

export const matchConfigSchema = z.object({
  strong_rec_thresh: z.number().min(0).max(1).default(0.04),
})

export type MatchConfig = z.infer<typeof matchConfigSchema>

// ============================================================================
// Complete Beets Configuration Schema
// ============================================================================

export const beetsConfigSchema = z.object({
  directory: z.string(),
  library: z.string(),
  art_filename: z.string().default('albumart'),
  threaded: z.boolean().default(true),
  original_date: z.boolean().default(false),
  per_disc_numbering: z.boolean().default(false),
  plugins: z.array(z.string()),
  item_fields: z.record(z.string()).default({ multidisc: '1 if disctotal > 1 else 0' }),
  import: importConfigSchema,
  paths: pathsConfigSchema,
  convert: convertConfigSchema,
  lastgenre: lastgenreConfigSchema,
  embedart: embedartConfigSchema,
  fetchart: fetchartConfigSchema,
  replaygain: replaygainConfigSchema,
  scrub: scrubConfigSchema,
  replace: replaceConfigSchema,
  emby: embyConfigSchema,
  discogs: discogsConfigSchema,
  permissions: permissionsConfigSchema,
  match: matchConfigSchema,
})

export type BeetsConfig = z.infer<typeof beetsConfigSchema>

// ============================================================================
// Emby Test Request/Response
// ============================================================================

export const embyTestRequestSchema = z.object({
  host: z.string().min(1, 'Host is required'),
  port: z.number().min(1).max(65535),
  userid: z.string().min(1, 'User ID is required'),
  apikey: z.string().min(1, 'API key is required'),
})

export type EmbyTestRequest = z.infer<typeof embyTestRequestSchema>

export interface EmbyTestResponse {
  success: boolean
  message: string
  server_name?: string
  server_version?: string
}

// ============================================================================
// Filesystem Browse Types
// ============================================================================

export interface FilesystemEntry {
  name: string
  path: string
  type: 'directory' | 'file'
  size?: number
  modified?: string
}

export interface FilesystemBrowseResponse {
  path: string
  parent: string | null
  entries: FilesystemEntry[]
}

export interface FilesystemCreateRequest {
  path: string
  name: string
}

export interface FilesystemCreateResponse {
  success: boolean
  path: string
}

// ============================================================================
// Default Values
// ============================================================================

export const DEFAULT_PLUGINS = [
  'web',
  'fetchart',
  'embedart',
  'convert',
  'scrub',
  'replaygain',
  'lastgenre',
  'chroma',
  'musicbrainz',
  'discogs',
  'deezer',
  'spotify',
  'permissions',
  'inline',
]

export const AVAILABLE_PLUGINS = [
  'web',
  'fetchart',
  'embedart',
  'convert',
  'scrub',
  'replaygain',
  'lastgenre',
  'chroma',
  'embyupdate',
  'musicbrainz',
  'discogs',
  'deezer',
  'spotify',
  'permissions',
  'acousticbrainz',
  'badfiles',
  'bpd',
  'bucket',
  'duplicates',
  'edit',
  'export',
  'fish',
  'fuzzy',
  'hook',
  'ihate',
  'importadded',
  'importfeeds',
  'info',
  'inline',
  'ipfs',
  'keyfinder',
  'kodiupdate',
  'lyrics',
  'mbcollection',
  'mbsubmit',
  'mbsync',
  'metasync',
  'missing',
  'mpdstats',
  'mpdupdate',
  'parentwork',
  'play',
  'playlist',
  'plexupdate',
  'random',
  'smartplaylist',
  'sonosupdate',
  'subsonic',
  'the',
  'thumbnails',
  'types',
  'unimported',
  'zero',
  'match',
  'replace',
]

export const DEFAULT_REPLACE_RULES: ReplaceRule[] = [
  { pattern: '^\\.', replacement: '_' },
  { pattern: '[\\x00-\\x1f]', replacement: '_' },
  { pattern: '[<>:"\\?\\*\\|]', replacement: '_' },
  { pattern: '[\\xE8-\\xEB]', replacement: 'e' },
  { pattern: '[\\xEC-\\xEF]', replacement: 'i' },
  { pattern: '[\\xE2-\\xE6]', replacement: 'a' },
  { pattern: '[\\xF2-\\xF6]', replacement: 'o' },
  { pattern: '[\\xF8]', replacement: 'o' },
  { pattern: '\\.$', replacement: '_' },
  { pattern: '\\s+$', replacement: '' },
]

export const PATH_TEMPLATE_VARIABLES = [
  { variable: '$albumartist', description: 'Album artist name' },
  { variable: '$artist', description: 'Track artist name' },
  { variable: '$album', description: 'Album title' },
  { variable: '$track', description: 'Track number (zero-padded)' },
  { variable: '$title', description: 'Track title' },
  { variable: '$year', description: 'Release year' },
  { variable: '$genre', description: 'Genre' },
  { variable: '$disc', description: 'Disc number' },
  { variable: '$disctotal', description: 'Total number of discs' },
  { variable: '%aunique{}', description: 'Disambiguation string for albums with same name' },
  { variable: '%if{$comp,text}', description: 'Conditional: output text if compilation' },
  { variable: '%upper{$var}', description: 'Convert to uppercase' },
  { variable: '%lower{$var}', description: 'Convert to lowercase' },
  { variable: '%title{$var}', description: 'Convert to title case' },
]

// ============================================================================
// Helper function to get default config
// ============================================================================

export function getDefaultBeetsConfig(
  directory: string,
  library: string
): BeetsConfig {
  return {
    directory,
    library,
    art_filename: 'albumart',
    threaded: true,
    original_date: false,
    per_disc_numbering: false,
    plugins: [...DEFAULT_PLUGINS],
    item_fields: { multidisc: '1 if disctotal > 1 else 0' },
    import: {
      write: true,
      copy: true,
      move: false,
      resume: true,
      incremental: false,
      quiet_fallback: 'skip',
      timid: false,
      log: null,
    },
    paths: {
      default: '$albumartist/$album%aunique{}/%if{$multidisc,$disc-}$track - $title',
      singleton: 'Singles/$artist - $title',
      comp: 'Compilations/$album%aunique{}/%if{$multidisc,$disc-}$track - $title',
      albumtype_soundtrack: 'Soundtracks/$album/%if{$multidisc,$disc-}$track $title',
    },
    convert: {
      auto: false,
      ffmpeg: '/usr/bin/ffmpeg',
      opts: '-ab 320k -ac 2 -ar 48000',
      max_bitrate: 320,
      threads: 1,
    },
    lastgenre: {
      auto: true,
      source: 'album',
    },
    embedart: {
      auto: true,
    },
    fetchart: {
      auto: true,
    },
    replaygain: {
      auto: false,
    },
    scrub: {
      auto: true,
    },
    replace: [...DEFAULT_REPLACE_RULES],
    emby: {
      host: '',
      port: 8096,
      userid: '',
      apikey: '',
    },
    discogs: {
      user_token: '',
    },
    permissions: {
      file: 664,
      dir: 775,
    },
    match: {
      strong_rec_thresh: 0.04,
    },
  }
}

// ============================================================================
// Library Initialization Types
// ============================================================================

/**
 * Response from GET /api/v1/libraries/{library_id}/config/path-status endpoint.
 */
export interface PathStatusResponse {
  /** Whether the library directory exists on disk */
  directoryExists: boolean
  /** Whether the beets database file exists on disk */
  databaseExists: boolean
  /** The configured library directory path (null if not configured) */
  directoryPath: string | null
  /** The configured database file path (null if not configured) */
  databasePath: string | null
}

/**
 * Raw API response (snake_case) before transformation.
 */
export interface RawPathStatusResponse {
  directory_exists: boolean
  database_exists: boolean
  directory_path: string | null
  database_path: string | null
}

/**
 * Response from POST /api/v1/libraries/{library_id}/config/initialize endpoint.
 */
export interface InitializeResponse {
  /** Whether initialization completed successfully */
  success: boolean
  /** Whether the library directory was created (false if already existed) */
  directoryCreated: boolean
  /** Whether the database was initialized (false if already existed) */
  databaseInitialized: boolean
  /** Human-readable status message */
  message: string
}

/**
 * Raw API response (snake_case) before transformation.
 */
export interface RawInitializeResponse {
  success: boolean
  directory_created: boolean
  database_initialized: boolean
  message: string
}

/**
 * Transform snake_case path status response to camelCase.
 */
export function transformPathStatusResponse(
  raw: RawPathStatusResponse
): PathStatusResponse {
  return {
    directoryExists: raw.directory_exists,
    databaseExists: raw.database_exists,
    directoryPath: raw.directory_path,
    databasePath: raw.database_path,
  }
}

/**
 * Transform snake_case initialize response to camelCase.
 */
export function transformInitializeResponse(
  raw: RawInitializeResponse
): InitializeResponse {
  return {
    success: raw.success,
    directoryCreated: raw.directory_created,
    databaseInitialized: raw.database_initialized,
    message: raw.message,
  }
}
