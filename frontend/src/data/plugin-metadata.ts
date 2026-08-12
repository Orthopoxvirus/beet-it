/**
 * Plugin metadata registry for beets plugins.
 * Contains descriptions, documentation URLs, and settings configuration.
 */

export interface PluginMetadata {
  name: string
  description: string
  docsUrl: string
  hasSettings: boolean
}

const BEETS_DOCS_BASE = 'https://beets.readthedocs.io/en/stable/plugins'

/**
 * Complete registry of beets plugin metadata.
 * Includes all default plugins and additional available plugins.
 */
export const PLUGIN_METADATA: Record<string, PluginMetadata> = {
  // Default plugins (14 total)
  web: {
    name: 'web',
    description: 'Provides a web interface and REST API for browsing and querying your music library.',
    docsUrl: `${BEETS_DOCS_BASE}/web.html`,
    hasSettings: false,
  },
  fetchart: {
    name: 'fetchart',
    description: 'Downloads album artwork from various online sources automatically during import.',
    docsUrl: `${BEETS_DOCS_BASE}/fetchart.html`,
    hasSettings: true,
  },
  embedart: {
    name: 'embedart',
    description: 'Embeds album artwork directly into audio files as metadata.',
    docsUrl: `${BEETS_DOCS_BASE}/embedart.html`,
    hasSettings: true,
  },
  convert: {
    name: 'convert',
    description: 'Transcodes audio files to different formats during import or on-demand.',
    docsUrl: `${BEETS_DOCS_BASE}/convert.html`,
    hasSettings: true,
  },
  scrub: {
    name: 'scrub',
    description: 'Removes non-standard metadata tags from audio files for cleaner organization.',
    docsUrl: `${BEETS_DOCS_BASE}/scrub.html`,
    hasSettings: true,
  },
  replaygain: {
    name: 'replaygain',
    description: 'Calculates ReplayGain volume normalization values for consistent playback levels.',
    docsUrl: `${BEETS_DOCS_BASE}/replaygain.html`,
    hasSettings: true,
  },
  lastgenre: {
    name: 'lastgenre',
    description: 'Fetches genre tags from Last.fm to automatically classify your music.',
    docsUrl: `${BEETS_DOCS_BASE}/lastgenre.html`,
    hasSettings: true,
  },
  chroma: {
    name: 'chroma',
    description: 'Uses acoustic fingerprinting via AcoustID to identify and tag unknown tracks.',
    docsUrl: `${BEETS_DOCS_BASE}/chroma.html`,
    hasSettings: false,
  },
  embyupdate: {
    name: 'embyupdate',
    description:
      'Emby/Jellyfin connection for the post-import library refresh. beet-it now triggers the refresh itself (non-fatal if Emby is down), so enabling the beets plugin would only duplicate it — just set host/API key in its settings.',
    docsUrl: `${BEETS_DOCS_BASE}/embyupdate.html`,
    hasSettings: true,
  },
  musicbrainz: {
    name: 'musicbrainz',
    description: 'Core metadata source using the MusicBrainz database for accurate tagging.',
    docsUrl: 'https://beets.readthedocs.io/en/stable/reference/config.html#musicbrainz-options',
    hasSettings: false,
  },
  discogs: {
    name: 'discogs',
    description: 'Fetches additional metadata from Discogs, useful for vinyl and rare releases.',
    docsUrl: `${BEETS_DOCS_BASE}/discogs.html`,
    hasSettings: true,
  },
  deezer: {
    name: 'deezer',
    description: 'Uses Deezer as an additional metadata source for album and track information.',
    docsUrl: `${BEETS_DOCS_BASE}/deezer.html`,
    hasSettings: false,
  },
  spotify: {
    name: 'spotify',
    description: 'Uses Spotify as a metadata source for albums, tracks, and additional info.',
    docsUrl: `${BEETS_DOCS_BASE}/spotify.html`,
    hasSettings: false,
  },
  permissions: {
    name: 'permissions',
    description: 'Sets file and directory permissions for imported music files.',
    docsUrl: `${BEETS_DOCS_BASE}/permissions.html`,
    hasSettings: true,
  },

  // Additional available plugins (~35 more)
  acousticbrainz: {
    name: 'acousticbrainz',
    description: 'Fetches acoustic analysis data like BPM, mood, and key from AcousticBrainz.',
    docsUrl: `${BEETS_DOCS_BASE}/acousticbrainz.html`,
    hasSettings: false,
  },
  badfiles: {
    name: 'badfiles',
    description: 'Checks for and reports corrupted or invalid audio files in your library.',
    docsUrl: `${BEETS_DOCS_BASE}/badfiles.html`,
    hasSettings: false,
  },
  bpd: {
    name: 'bpd',
    description: 'Provides an MPD-compatible server interface for playing music from beets.',
    docsUrl: `${BEETS_DOCS_BASE}/bpd.html`,
    hasSettings: false,
  },
  bucket: {
    name: 'bucket',
    description: 'Groups albums into bucket directories by first letter or custom ranges.',
    docsUrl: `${BEETS_DOCS_BASE}/bucket.html`,
    hasSettings: false,
  },
  duplicates: {
    name: 'duplicates',
    description: 'Finds and manages duplicate tracks in your music library.',
    docsUrl: `${BEETS_DOCS_BASE}/duplicates.html`,
    hasSettings: false,
  },
  edit: {
    name: 'edit',
    description: 'Opens track metadata in your favorite text editor for manual editing.',
    docsUrl: `${BEETS_DOCS_BASE}/edit.html`,
    hasSettings: false,
  },
  export: {
    name: 'export',
    description: 'Exports library metadata to JSON or other formats for external use.',
    docsUrl: `${BEETS_DOCS_BASE}/export.html`,
    hasSettings: false,
  },
  fish: {
    name: 'fish',
    description: 'Provides shell completions for the fish shell.',
    docsUrl: `${BEETS_DOCS_BASE}/fish.html`,
    hasSettings: false,
  },
  fuzzy: {
    name: 'fuzzy',
    description: 'Enables fuzzy string matching for more flexible library queries.',
    docsUrl: `${BEETS_DOCS_BASE}/fuzzy.html`,
    hasSettings: false,
  },
  hook: {
    name: 'hook',
    description: 'Runs custom shell commands when specific beets events occur.',
    docsUrl: `${BEETS_DOCS_BASE}/hook.html`,
    hasSettings: false,
  },
  ihate: {
    name: 'ihate',
    description: 'Automatically skips importing albums matching specified criteria.',
    docsUrl: `${BEETS_DOCS_BASE}/ihate.html`,
    hasSettings: false,
  },
  importadded: {
    name: 'importadded',
    description: 'Preserves file modification times as the "added" date during import.',
    docsUrl: `${BEETS_DOCS_BASE}/importadded.html`,
    hasSettings: false,
  },
  importfeeds: {
    name: 'importfeeds',
    description: 'Creates M3U playlists and symlinks of recently imported music.',
    docsUrl: `${BEETS_DOCS_BASE}/importfeeds.html`,
    hasSettings: false,
  },
  info: {
    name: 'info',
    description: 'Displays detailed metadata information about tracks and albums.',
    docsUrl: `${BEETS_DOCS_BASE}/info.html`,
    hasSettings: false,
  },
  inline: {
    name: 'inline',
    description: 'Defines custom template fields using Python expressions.',
    docsUrl: `${BEETS_DOCS_BASE}/inline.html`,
    hasSettings: false,
  },
  ipfs: {
    name: 'ipfs',
    description: 'Stores music files on IPFS (InterPlanetary File System) for distributed access.',
    docsUrl: `${BEETS_DOCS_BASE}/ipfs.html`,
    hasSettings: false,
  },
  keyfinder: {
    name: 'keyfinder',
    description: 'Detects musical key of tracks using the keyfinder library.',
    docsUrl: `${BEETS_DOCS_BASE}/keyfinder.html`,
    hasSettings: false,
  },
  kodiupdate: {
    name: 'kodiupdate',
    description: 'Notifies Kodi to update its music library after imports.',
    docsUrl: `${BEETS_DOCS_BASE}/kodiupdate.html`,
    hasSettings: false,
  },
  lyrics: {
    name: 'lyrics',
    description: 'Fetches song lyrics from various online sources and embeds them.',
    docsUrl: `${BEETS_DOCS_BASE}/lyrics.html`,
    hasSettings: false,
  },
  mbcollection: {
    name: 'mbcollection',
    description: 'Syncs your library with your MusicBrainz collection.',
    docsUrl: `${BEETS_DOCS_BASE}/mbcollection.html`,
    hasSettings: false,
  },
  mbsubmit: {
    name: 'mbsubmit',
    description: 'Assists in submitting new releases to MusicBrainz.',
    docsUrl: `${BEETS_DOCS_BASE}/mbsubmit.html`,
    hasSettings: false,
  },
  mbsync: {
    name: 'mbsync',
    description: 'Updates metadata from MusicBrainz for already-imported items.',
    docsUrl: `${BEETS_DOCS_BASE}/mbsync.html`,
    hasSettings: false,
  },
  metasync: {
    name: 'metasync',
    description: 'Syncs metadata between beets and media players like Amarok.',
    docsUrl: `${BEETS_DOCS_BASE}/metasync.html`,
    hasSettings: false,
  },
  missing: {
    name: 'missing',
    description: 'Lists albums that are missing tracks compared to their releases.',
    docsUrl: `${BEETS_DOCS_BASE}/missing.html`,
    hasSettings: false,
  },
  mpdstats: {
    name: 'mpdstats',
    description: 'Collects play statistics from MPD for library analysis.',
    docsUrl: `${BEETS_DOCS_BASE}/mpdstats.html`,
    hasSettings: false,
  },
  mpdupdate: {
    name: 'mpdupdate',
    description: 'Notifies MPD to update its database after imports.',
    docsUrl: `${BEETS_DOCS_BASE}/mpdupdate.html`,
    hasSettings: false,
  },
  parentwork: {
    name: 'parentwork',
    description: 'Fetches parent work information from MusicBrainz for classical music.',
    docsUrl: `${BEETS_DOCS_BASE}/parentwork.html`,
    hasSettings: false,
  },
  play: {
    name: 'play',
    description: 'Plays music directly from beets using your configured player.',
    docsUrl: `${BEETS_DOCS_BASE}/play.html`,
    hasSettings: false,
  },
  playlist: {
    name: 'playlist',
    description: 'Manages and updates M3U playlist files for your library.',
    docsUrl: `${BEETS_DOCS_BASE}/playlist.html`,
    hasSettings: false,
  },
  plexupdate: {
    name: 'plexupdate',
    description: 'Notifies Plex to update its music library after imports.',
    docsUrl: `${BEETS_DOCS_BASE}/plexupdate.html`,
    hasSettings: false,
  },
  random: {
    name: 'random',
    description: 'Selects random albums or tracks from your library.',
    docsUrl: `${BEETS_DOCS_BASE}/random.html`,
    hasSettings: false,
  },
  smartplaylist: {
    name: 'smartplaylist',
    description: 'Creates smart playlists based on queries that update automatically.',
    docsUrl: `${BEETS_DOCS_BASE}/smartplaylist.html`,
    hasSettings: false,
  },
  sonosupdate: {
    name: 'sonosupdate',
    description: 'Updates Sonos music library index after imports.',
    docsUrl: `${BEETS_DOCS_BASE}/sonosupdate.html`,
    hasSettings: false,
  },
  subsonic: {
    name: 'subsonic',
    description: 'Serves your library via a Subsonic-compatible API.',
    docsUrl: `${BEETS_DOCS_BASE}/subsonic.html`,
    hasSettings: false,
  },
  the: {
    name: 'the',
    description: 'Moves "The" from the beginning of artist names to the end.',
    docsUrl: `${BEETS_DOCS_BASE}/the.html`,
    hasSettings: false,
  },
  thumbnails: {
    name: 'thumbnails',
    description: 'Creates album art thumbnails for use with file managers.',
    docsUrl: `${BEETS_DOCS_BASE}/thumbnails.html`,
    hasSettings: false,
  },
  types: {
    name: 'types',
    description: 'Defines custom flexible attribute types for advanced querying.',
    docsUrl: `${BEETS_DOCS_BASE}/types.html`,
    hasSettings: false,
  },
  unimported: {
    name: 'unimported',
    description: 'Lists files in your library directory that are not in the database.',
    docsUrl: `${BEETS_DOCS_BASE}/unimported.html`,
    hasSettings: false,
  },
  zero: {
    name: 'zero',
    description: 'Removes specific metadata fields during import based on rules.',
    docsUrl: `${BEETS_DOCS_BASE}/zero.html`,
    hasSettings: false,
  },

  // Additional plugins that may have settings (non-default but configurable)
  match: {
    name: 'match',
    description: 'Configures autotagger matching threshold for import accuracy.',
    docsUrl: 'https://beets.readthedocs.io/en/stable/reference/config.html#match',
    hasSettings: true,
  },
  replace: {
    name: 'replace',
    description: 'Applies character replacement rules to file paths during import.',
    docsUrl: 'https://beets.readthedocs.io/en/stable/reference/config.html#replace',
    hasSettings: true,
  },
}

/**
 * Gets metadata for a specific plugin.
 * Returns a default entry if the plugin is not found in the registry.
 */
export function getPluginMetadata(pluginName: string): PluginMetadata {
  const metadata = PLUGIN_METADATA[pluginName]
  if (metadata) {
    return metadata
  }

  // Return a default entry for unknown plugins
  return {
    name: pluginName,
    description: `The ${pluginName} plugin for beets.`,
    docsUrl: `${BEETS_DOCS_BASE}/${pluginName}.html`,
    hasSettings: false,
  }
}

/**
 * List of plugins that have settings dialogs.
 * Used to determine when to show the settings cog icon.
 */
export const PLUGINS_WITH_SETTINGS = Object.entries(PLUGIN_METADATA)
  .filter(([, meta]) => meta.hasSettings)
  .map(([name]) => name)
