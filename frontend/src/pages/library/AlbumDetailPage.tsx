import { useState, useCallback, useEffect } from 'react'
import { useParams, useLocation, useNavigate, Link } from 'react-router-dom'
import {
  ArrowLeft,
  Music,
  Calendar,
  Tag,
  Disc3,
  Clock,
  Building2,
  Upload,
  Play,
  Pause,
  AlertCircle,
  FileAudio,
  Gauge,
  ArrowRightLeft,
  Download,
} from 'lucide-react'

import { Button } from '@/components/ui/button'
import { Card, CardContent } from '@/components/ui/card'
import {
  Table,
  TableBody,
  TableCell,
  TableHead,
  TableHeader,
  TableRow,
} from '@/components/ui/table'
import { AudioPlayer } from '@/components/album'
import { ConvertWavDialog } from '@/components/album'
import { CoverArtUpload } from '@/components/album'
import { MoveAlbumDialog } from '@/components/album'

import { useAlbumDetail, useAlbumTracks } from '@/hooks/useAlbums'
import { getAlbumCoverUrl, getAlbumDownloadUrl, type Track } from '@/api/albums'

// ============================================================================
// Helper Functions
// ============================================================================

/**
 * Format seconds into mm:ss or h:mm:ss format.
 */
function formatDuration(seconds: number): string {
  if (!isFinite(seconds) || seconds < 0) return '0:00'

  const hours = Math.floor(seconds / 3600)
  const mins = Math.floor((seconds % 3600) / 60)
  const secs = Math.floor(seconds % 60)

  if (hours > 0) {
    return `${hours}:${mins.toString().padStart(2, '0')}:${secs.toString().padStart(2, '0')}`
  }
  return `${mins}:${secs.toString().padStart(2, '0')}`
}

/**
 * Format total album duration into human-readable format.
 */
function formatTotalDuration(seconds: number): string {
  if (!isFinite(seconds) || seconds < 0) return '0 min'

  const hours = Math.floor(seconds / 3600)
  const mins = Math.floor((seconds % 3600) / 60)

  if (hours > 0) {
    return `${hours} hr ${mins} min`
  }
  return `${mins} min`
}

/**
 * Build a human-readable quality string from track audio properties.
 * Lossy formats show bitrate in kbps; lossless formats show bit-depth/sample-rate.
 */
function formatQuality(album: {
  format: string | null
  bitrate: number | null
  sample_rate: number | null
  bit_depth: number | null
}): string | null {
  const parts: string[] = []

  // Bit depth + sample rate for lossless formats
  if (album.bit_depth && album.sample_rate) {
    parts.push(`${album.bit_depth}-bit`)
    parts.push(`${(album.sample_rate / 1000).toFixed(1)} kHz`)
  } else if (album.sample_rate) {
    parts.push(`${(album.sample_rate / 1000).toFixed(1)} kHz`)
  }

  // Bitrate (kbps) — more meaningful for lossy formats
  if (album.bitrate && !album.bit_depth) {
    parts.push(`${Math.round(album.bitrate / 1000)} kbps`)
  }

  return parts.length > 0 ? parts.join(' · ') : null
}

// ============================================================================
// Loading Skeleton Components
// ============================================================================

function AlbumDetailSkeleton() {
  return (
    <div className="space-y-6">
      {/* Back button */}
      <div className="h-9 w-32 bg-muted animate-pulse rounded" />

      {/* Header section */}
      <div className="flex flex-col md:flex-row gap-6">
        <div className="w-64 h-64 bg-muted animate-pulse rounded-lg flex-shrink-0" />
        <div className="flex-1 space-y-4">
          <div className="h-8 w-3/4 bg-muted animate-pulse rounded" />
          <div className="h-6 w-1/2 bg-muted animate-pulse rounded" />
          <div className="grid grid-cols-2 gap-4 mt-4">
            {Array.from({ length: 6 }).map((_, i) => (
              <div key={i} className="h-5 bg-muted animate-pulse rounded w-2/3" />
            ))}
          </div>
        </div>
      </div>

      {/* Track list skeleton */}
      <div className="space-y-2">
        {Array.from({ length: 5 }).map((_, i) => (
          <div key={i} className="h-12 bg-muted animate-pulse rounded" />
        ))}
      </div>
    </div>
  )
}

// ============================================================================
// Track Row Component
// ============================================================================

interface TrackRowProps {
  track: Track
  isPlaying: boolean
  isCurrentTrack: boolean
  onPlay: () => void
  showDiscNumber: boolean
}

function TrackRow({
  track,
  isPlaying,
  isCurrentTrack,
  onPlay,
  showDiscNumber,
}: TrackRowProps) {
  return (
    <TableRow
      className={`cursor-pointer ${isCurrentTrack ? 'bg-primary/10' : ''}`}
      onClick={onPlay}
    >
      {showDiscNumber && (
        <TableCell className="w-12 text-muted-foreground">
          {track.disc_number}
        </TableCell>
      )}
      <TableCell className="w-16 text-muted-foreground">
        <div className="flex items-center gap-2">
          {isCurrentTrack && isPlaying ? (
            <Pause className="h-4 w-4 text-primary" />
          ) : isCurrentTrack ? (
            <Play className="h-4 w-4 text-primary" />
          ) : (
            <span>{track.track_number}</span>
          )}
        </div>
      </TableCell>
      <TableCell className="font-medium">
        <span className={isCurrentTrack ? 'text-primary' : ''}>
          {track.title}
        </span>
      </TableCell>
      <TableCell className="hidden sm:table-cell text-muted-foreground">{track.artist}</TableCell>
      <TableCell className="text-right text-muted-foreground w-20">
        {formatDuration(track.duration)}
      </TableCell>
    </TableRow>
  )
}

// ============================================================================
// Album Detail Page Component
// ============================================================================

export default function AlbumDetailPage() {
  const { slug, albumId: albumIdParam } = useParams<{
    slug: string
    albumId: string
  }>()

  const albumId = albumIdParam ? parseInt(albumIdParam, 10) : undefined

  // "Back to Albums" returns to the exact grid the user came from (preserving
  // the view + folder/artist filter encoded in its query string), passed via
  // router state by the album card. Falls back to the bare albums list when
  // the album was opened directly (deep link / refresh — no originating URL).
  const location = useLocation()
  const navigate = useNavigate()
  const backTo =
    (location.state as { from?: string } | null)?.from ??
    `/libraries/${slug}/albums`

  const [currentTrackIndex, setCurrentTrackIndex] = useState<number | null>(null)
  const [isPlaying, setIsPlaying] = useState(false)
  const [showUploadDialog, setShowUploadDialog] = useState(false)
  const [showMoveDialog, setShowMoveDialog] = useState(false)
  const [showConvertDialog, setShowConvertDialog] = useState(false)
  const [imgError, setImgError] = useState(false)

  const {
    data: album,
    isLoading: albumLoading,
    error: albumError,
  } = useAlbumDetail(slug, albumId)

  const {
    data: tracksData,
    isLoading: tracksLoading,
  } = useAlbumTracks(slug, albumId)

  const tracks = tracksData?.items || []
  const isLoading = albumLoading || tracksLoading

  // In-place WAV→FLAC conversion is offered whenever the album still has WAV
  // tracks — also for mixed-format albums, where the aggregate `album.format`
  // may already read FLAC.
  const wavTrackCount = tracks.filter(
    (track) => track.format?.toUpperCase() === 'WAV'
  ).length

  // Check if we need to show disc numbers (multi-disc album)
  const showDiscNumbers = album ? album.disc_count > 1 : false

  // Reset image error when album changes
  useEffect(() => {
    setImgError(false)
  }, [albumId])

  // ============================================================================
  // Playback Handlers
  // ============================================================================

  const handleTrackPlay = useCallback((index: number) => {
    if (currentTrackIndex === index) {
      // Toggle play/pause for current track
      setIsPlaying((prev) => !prev)
    } else {
      // Switch to new track
      setCurrentTrackIndex(index)
      setIsPlaying(true)
    }
  }, [currentTrackIndex])

  const handleTrackChange = useCallback((index: number | null) => {
    setCurrentTrackIndex(index)
    setIsPlaying(index !== null)
  }, [])

  // ============================================================================
  // Cover Art URL
  // ============================================================================

  // 768px is the largest thumbnail size the backend offers; covers the
  // full-width cover on mobile (≤414 CSS px → up to ~828 device px on
  // 2x retina) and the 256-px cover on desktop without falling back to
  // the original multi-MB artwork.
  const coverUrl =
    slug && album?.cover_art_path && !imgError
      ? getAlbumCoverUrl(slug, album.id, 768, album.cover_version)
      : null

  // ============================================================================
  // Render States
  // ============================================================================

  if (!slug || !albumId || isNaN(albumId)) {
    return (
      <div className="text-center py-12 border rounded-lg bg-muted/20">
        <AlertCircle className="h-12 w-12 mx-auto text-destructive" />
        <h3 className="mt-4 text-lg font-medium">Invalid Album</h3>
        <p className="mt-2 text-muted-foreground">
          The album ID is not valid.
        </p>
        <Button asChild className="mt-4">
          <Link to={backTo}>Back to Albums</Link>
        </Button>
      </div>
    )
  }

  if (isLoading) {
    return <AlbumDetailSkeleton />
  }

  if (albumError) {
    const isNotFound =
      albumError instanceof Error &&
      'status' in albumError &&
      (albumError as { status: number }).status === 404

    return (
      <div className="text-center py-12 border rounded-lg bg-muted/20">
        <AlertCircle className="h-12 w-12 mx-auto text-destructive" />
        <h3 className="mt-4 text-lg font-medium">
          {isNotFound ? 'Album Not Found' : 'Error Loading Album'}
        </h3>
        <p className="mt-2 text-muted-foreground">
          {albumError instanceof Error
            ? albumError.message
            : 'An unknown error occurred'}
        </p>
        <Button asChild className="mt-4">
          <Link to={backTo}>Back to Albums</Link>
        </Button>
      </div>
    )
  }

  if (!album) {
    return (
      <div className="text-center py-12 border rounded-lg bg-muted/20">
        <AlertCircle className="h-12 w-12 mx-auto text-muted-foreground" />
        <h3 className="mt-4 text-lg font-medium">Album Not Found</h3>
        <p className="mt-2 text-muted-foreground">
          The album you're looking for doesn't exist.
        </p>
        <Button asChild className="mt-4">
          <Link to={backTo}>Back to Albums</Link>
        </Button>
      </div>
    )
  }

  // ============================================================================
  // Main Render
  // ============================================================================

  return (
    <div className="space-y-6">
      {/* Back Navigation */}
      <Button variant="ghost" asChild className="-ml-2">
        <Link to={backTo}>
          <ArrowLeft className="h-4 w-4 mr-2" />
          Back to Albums
        </Link>
      </Button>

      {/* Album Header */}
      <div className="flex flex-col md:flex-row gap-6">
        {/* Cover Art — full width on mobile so the artwork dominates the
            top of the screen; pinned to 16rem on md+ where the album info
            sits next to it. */}
        <div className="w-full md:w-64 md:flex-shrink-0 space-y-3">
          <div
            className="aspect-square bg-muted rounded-lg overflow-hidden cursor-pointer group relative"
            onClick={() => setShowUploadDialog(true)}
          >
            {coverUrl ? (
              <img
                src={coverUrl}
                alt={`${album.title} by ${album.artist}`}
                className="w-full h-full object-cover"
                onError={() => setImgError(true)}
              />
            ) : (
              <div className="w-full h-full flex items-center justify-center">
                <Music className="h-16 w-16 text-muted-foreground" />
              </div>
            )}
            {/* Overlay on hover */}
            <div className="absolute inset-0 bg-black/50 opacity-0 group-hover:opacity-100 transition-opacity flex items-center justify-center">
              <Upload className="h-8 w-8 text-white" />
            </div>
          </div>
          <Button
            variant="outline"
            className="w-full"
            onClick={() => setShowUploadDialog(true)}
          >
            <Upload className="h-4 w-4 mr-2" />
            Change Cover
          </Button>
          <Button
            variant="outline"
            className="w-full"
            onClick={() => setShowMoveDialog(true)}
          >
            <ArrowRightLeft className="h-4 w-4 mr-2" />
            Move to Library
          </Button>
          {wavTrackCount > 0 && (
            <Button
              variant="outline"
              className="w-full"
              onClick={() => setShowConvertDialog(true)}
            >
              <FileAudio className="h-4 w-4 mr-2" />
              Convert WAV to FLAC
            </Button>
          )}
          {/* Plain anchor with `download` — the browser streams the archive
              straight to disk using the filename from Content-Disposition,
              so there's no need to pull it into memory via fetch. */}
          <Button variant="outline" className="w-full" asChild>
            <a href={getAlbumDownloadUrl(slug, album.id)} download>
              <Download className="h-4 w-4 mr-2" />
              Download ZIP
            </a>
          </Button>
        </div>

        {/* Album Info */}
        <div className="flex-1 space-y-4">
          <div>
            <h1 className="text-3xl font-bold">{album.title}</h1>
            <p className="text-xl text-muted-foreground mt-1">{album.artist}</p>
          </div>

          <Card>
            <CardContent className="pt-4">
              {/* leading-6 (24px) keeps the icon-text rows tall enough that
                  thin lucide strokes (Clock hands etc.) don't visually
                  collide with the row above on small screens. */}
              <div className="grid grid-cols-2 md:grid-cols-3 gap-x-4 gap-y-4 text-sm leading-6">
                {album.year && (
                  <div className="flex items-center gap-2">
                    <Calendar className="h-4 w-4 shrink-0 text-muted-foreground" />
                    <span>{album.year}</span>
                  </div>
                )}
                {album.genre && (
                  <div className="flex items-center gap-2">
                    <Tag className="h-4 w-4 shrink-0 text-muted-foreground" />
                    <span>{album.genre}</span>
                  </div>
                )}
                {album.label && (
                  <div className="flex items-center gap-2">
                    <Building2 className="h-4 w-4 shrink-0 text-muted-foreground" />
                    <span>{album.label}</span>
                  </div>
                )}
                <div className="flex items-center gap-2">
                  <Disc3 className="h-4 w-4 shrink-0 text-muted-foreground" />
                  <span>
                    {album.total_tracks} track{album.total_tracks !== 1 ? 's' : ''}
                    {album.disc_count > 1 && ` (${album.disc_count} discs)`}
                  </span>
                </div>
                <div className="flex items-center gap-2">
                  <Clock className="h-4 w-4 shrink-0 text-muted-foreground" />
                  <span>{formatTotalDuration(album.total_duration)}</span>
                </div>
                {album.album_type && (
                  <div className="flex items-center gap-2">
                    <Music className="h-4 w-4 shrink-0 text-muted-foreground" />
                    <span className="capitalize">{album.album_type}</span>
                  </div>
                )}
                {album.format && (
                  <div className="flex items-center gap-2">
                    <FileAudio className="h-4 w-4 shrink-0 text-muted-foreground" />
                    <span>{album.format}</span>
                  </div>
                )}
                {(() => {
                  const quality = formatQuality(album)
                  return quality ? (
                    <div className="flex items-center gap-2">
                      <Gauge className="h-4 w-4 shrink-0 text-muted-foreground" />
                      <span>{quality}</span>
                    </div>
                  ) : null
                })()}
              </div>
            </CardContent>
          </Card>
        </div>
      </div>

      {/* Audio Player */}
      {tracks.length > 0 && (
        <AudioPlayer
          slug={slug}
          tracks={tracks}
          currentTrackIndex={currentTrackIndex}
          onTrackChange={handleTrackChange}
          albumId={album.id}
          albumTitle={album.title}
          albumCoverUrl={coverUrl}
        />
      )}

      {/* Track Listing */}
      <div>
        <h2 className="text-xl font-semibold mb-4">Tracks</h2>
        {tracks.length > 0 ? (
          <Card>
            <Table>
              <TableHeader>
                <TableRow>
                  {showDiscNumbers && (
                    <TableHead className="w-12">Disc</TableHead>
                  )}
                  <TableHead className="w-16">#</TableHead>
                  <TableHead>Title</TableHead>
                  <TableHead className="hidden sm:table-cell">Artist</TableHead>
                  <TableHead className="text-right w-20">Duration</TableHead>
                </TableRow>
              </TableHeader>
              <TableBody>
                {tracks.map((track, index) => (
                  <TrackRow
                    key={track.id}
                    track={track}
                    isPlaying={isPlaying && currentTrackIndex === index}
                    isCurrentTrack={currentTrackIndex === index}
                    onPlay={() => handleTrackPlay(index)}
                    showDiscNumber={showDiscNumbers}
                  />
                ))}
              </TableBody>
            </Table>
          </Card>
        ) : (
          <div className="text-center py-8 border rounded-lg bg-muted/20">
            <Music className="h-12 w-12 mx-auto text-muted-foreground" />
            <p className="mt-4 text-muted-foreground">
              No tracks found for this album.
            </p>
          </div>
        )}
      </div>

      {/* Cover Art Upload Dialog */}
      <CoverArtUpload
        slug={slug}
        albumId={album.id}
        isOpen={showUploadDialog}
        onClose={() => setShowUploadDialog(false)}
        onSuccess={() => setImgError(false)}
      />

      {/* In-place WAV→FLAC Conversion Dialog */}
      <ConvertWavDialog
        slug={slug}
        albumId={album.id}
        albumTitle={album.title}
        albumArtist={album.artist}
        wavTrackCount={wavTrackCount}
        isOpen={showConvertDialog}
        onClose={() => setShowConvertDialog(false)}
      />

      {/* Move-to-Library Dialog */}
      <MoveAlbumDialog
        sourceSlug={slug}
        albumId={album.id}
        albumTitle={album.title}
        albumArtist={album.artist}
        isOpen={showMoveDialog}
        onClose={() => setShowMoveDialog(false)}
        // The moved album is about to vanish from this detail page, so return
        // to the overview the user came from (same target as "Back to Albums").
        onMoved={() => navigate(backTo)}
      />
    </div>
  )
}
