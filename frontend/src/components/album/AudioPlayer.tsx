import {
  useCallback,
  useEffect,
  useMemo,
  useRef,
  useState,
} from 'react'
import {
  Play,
  Pause,
  Square,
  SkipBack,
  SkipForward,
  Volume2,
  VolumeX,
  AlertCircle,
} from 'lucide-react'

import { Button } from '@/components/ui/button'
import { Slider } from '@/components/ui/slider'
import { getAlbumCoverUrl, getTrackStreamUrl, type Track } from '@/api/albums'

// ============================================================================
// AudioPlayer (Web Audio API edition)
//
// We dropped the HTML <audio>-element approach because mobile browsers
// retire the OS Media Session every time an <audio> element fires `ended`
// — even with two-element ping-pong the audio focus transfer was enough
// for Android Chrome to drop the lock-screen tile after each track.
//
// Web Audio API is the fix: one AudioContext that runs continuously, plus
// AudioBufferSourceNodes that we schedule sample-accurately. Decoding the
// next track in advance means transitions are gap-less; the OS never sees
// silence and never thinks the session has ended.
//
// Trade-offs:
// - decodeAudioData buffers the full PCM in memory. A 30-min FLAC at
//   16-bit/44.1kHz is ~250MB — we keep at most current + next buffer
//   in memory and drop them on advance.
// - Initial track-start latency is "fetch full file + decode" instead of
//   "fetch first chunk + play". For a typical library on a fast LAN that's
//   <1s for music, 2-3s for long audiobooks; acceptable for the upside.
// - Seeking re-creates the AudioBufferSourceNode at the new offset, which
//   is fine because the buffer is already decoded in memory.
// ============================================================================

export interface AudioPlayerProps {
  /** The library slug for streaming URLs */
  slug: string
  /** All tracks in the album */
  tracks: Track[]
  /** Currently selected track index (0-based) */
  currentTrackIndex: number | null
  /** Callback when a track change is requested */
  onTrackChange: (index: number | null) => void
  /** Optional album cover URL — used for OS-level media session artwork. */
  albumCoverUrl?: string | null
  /** Optional album id — used to build size-specific MediaSession artwork. */
  albumId?: number | null
  /** Optional album title — used for OS-level media session metadata. */
  albumTitle?: string | null
}

function formatDuration(seconds: number): string {
  if (!isFinite(seconds) || seconds < 0) return '0:00'
  const mins = Math.floor(seconds / 60)
  const secs = Math.floor(seconds % 60)
  return `${mins}:${secs.toString().padStart(2, '0')}`
}

interface DecodedTrack {
  trackId: number
  buffer: AudioBuffer
}

export function AudioPlayer({
  slug,
  tracks,
  currentTrackIndex,
  onTrackChange,
  albumCoverUrl,
  albumId,
  albumTitle,
}: AudioPlayerProps) {
  const [isPlaying, setIsPlaying] = useState(false)
  const [currentTime, setCurrentTime] = useState(0)
  const [duration, setDuration] = useState(0)
  const [volume, setVolume] = useState(1)
  const [isMuted, setIsMuted] = useState(false)
  const [isLoading, setIsLoading] = useState(false)
  const [playbackError, setPlaybackError] = useState<string | null>(null)

  // -------- Web Audio plumbing --------
  const audioContextRef = useRef<AudioContext | null>(null)
  const gainNodeRef = useRef<GainNode | null>(null)
  // We pipe Web Audio output through a hidden <audio> element via a
  // MediaStreamAudioDestinationNode. Without this, mobile Chrome and iOS
  // Safari don't surface a Media Session UI on the lock screen — they
  // tie that UI to an active media element, not to AudioContext output.
  // Routing AudioContext → MediaStreamDest → <audio>.srcObject keeps the
  // sample-accurate scheduling while letting the OS see "a media element
  // is playing" so it shows + maintains the lock-screen tile.
  const mediaStreamDestRef = useRef<MediaStreamAudioDestinationNode | null>(
    null
  )
  const sinkAudioRef = useRef<HTMLAudioElement>(null)
  // Source node currently routed to the destination. Set when a track
  // starts; cleared when the track ends (handled or interrupted).
  const sourceNodeRef = useRef<AudioBufferSourceNode | null>(null)
  // Suppress the next `ended` callback — we set this when *we* stop a
  // source on purpose (track change, seek, pause) so the natural
  // auto-advance only fires for actual end-of-buffer events.
  const suppressEndedRef = useRef(false)
  // Decoded buffer of the currently playing track + the upcoming track.
  // We keep at most these two in memory.
  const currentTrackBufRef = useRef<DecodedTrack | null>(null)
  const nextTrackBufRef = useRef<DecodedTrack | null>(null)
  // contextTime when the current source started. Combined with
  // pauseOffsetRef this gives us a sample-accurate currentTime
  // independent of any HTML audio element.
  const startedAtCtxTimeRef = useRef(0)
  // Where we left off when paused, so resume can recreate the source
  // node at the same point.
  const pauseOffsetRef = useRef(0)
  // Most recent in-flight track-id load + decode promise. Lets us bail
  // when a stale fetch resolves after the user has moved on.
  const loadGenerationRef = useRef(0)
  // rAF id so we can cancel the time-update tick on cleanup / pause.
  const rafIdRef = useRef<number | null>(null)

  const currentTrack =
    currentTrackIndex !== null ? tracks[currentTrackIndex] ?? null : null

  // ----------------------------------------------------------------------
  // AudioContext bootstrap. Mobile browsers (Safari, some Chrome) require
  // an AudioContext to be created in response to a user gesture, so we
  // lazily init on the first play() / track-change call.
  // ----------------------------------------------------------------------
  const ensureContext = useCallback((): AudioContext | null => {
    if (audioContextRef.current) {
      // Resume after browser autosuspended (mobile background, tab
      // focus loss, etc).
      if (audioContextRef.current.state === 'suspended') {
        audioContextRef.current.resume().catch(() => {
          /* ignore */
        })
      }
      return audioContextRef.current
    }
    if (typeof window === 'undefined') return null
    const Ctor =
      window.AudioContext ||
      (window as unknown as { webkitAudioContext?: typeof AudioContext })
        .webkitAudioContext
    if (!Ctor) return null
    const ctx = new Ctor()
    const gain = ctx.createGain()
    // Route gain → MediaStreamDestination → <audio>.srcObject (so the OS
    // sees a media element to attach the lock-screen tile to). We do
    // NOT also connect to ctx.destination — that would play the audio
    // twice (once via the context, once via the <audio> element).
    let dest: MediaStreamAudioDestinationNode | null = null
    try {
      dest = ctx.createMediaStreamDestination()
      gain.connect(dest)
      const sink = sinkAudioRef.current
      if (sink) {
        sink.srcObject = dest.stream
        // Mobile autoplay policy still applies — but ensureContext is
        // called from a user-gesture path, so this play() should resolve.
        sink.play().catch((err) => {
          console.warn(
            '[AudioPlayer] sink <audio>.play() rejected, falling back to ctx.destination',
            err
          )
          // Fall back to direct destination if the sink couldn't start.
          // Lock-screen UI may not appear, but at least audio plays.
          try {
            gain.disconnect(dest!)
          } catch {
            // ignore
          }
          gain.connect(ctx.destination)
        })
      } else {
        gain.connect(ctx.destination)
      }
    } catch (err) {
      console.warn(
        '[AudioPlayer] MediaStreamDestination unavailable; using ctx.destination',
        err
      )
      gain.connect(ctx.destination)
    }
    audioContextRef.current = ctx
    gainNodeRef.current = gain
    mediaStreamDestRef.current = dest
    return ctx
  }, [])

  // ----------------------------------------------------------------------
  // Fetch + decode a track's stream into an AudioBuffer.
  // ----------------------------------------------------------------------
  const fetchAndDecode = useCallback(
    async (track: Track, signal?: AbortSignal): Promise<DecodedTrack | null> => {
      const ctx = ensureContext()
      if (!ctx) return null
      const url = getTrackStreamUrl(slug, track.id)
      const res = await fetch(url, { signal, credentials: 'include' })
      if (!res.ok) {
        throw new Error(`Stream fetch ${res.status} for track ${track.id}`)
      }
      const arrayBuf = await res.arrayBuffer()
      // decodeAudioData returns a Promise on modern browsers; old Safari
      // wants the callback signature, so wrap.
      const buffer: AudioBuffer = await new Promise((resolve, reject) => {
        try {
          const maybe = ctx.decodeAudioData(
            arrayBuf,
            (b) => resolve(b),
            (e) => reject(e)
          )
          if (maybe && typeof (maybe as Promise<AudioBuffer>).then === 'function') {
            ;(maybe as Promise<AudioBuffer>).then(resolve, reject)
          }
        } catch (e) {
          reject(e)
        }
      })
      return { trackId: track.id, buffer }
    },
    [slug, ensureContext]
  )

  // ----------------------------------------------------------------------
  // Schedule an AudioBuffer to start at a specific contextTime + offset.
  // Returns the source node (caller is responsible for disconnect on
  // interruption) so we can hook onended for auto-advance.
  // ----------------------------------------------------------------------
  const startBuffer = useCallback(
    (buffer: AudioBuffer, offsetSeconds: number, when: number) => {
      const ctx = audioContextRef.current
      const gain = gainNodeRef.current
      if (!ctx || !gain) return null
      const src = ctx.createBufferSource()
      src.buffer = buffer
      src.connect(gain)
      // Web Audio source nodes are one-shot — calling start() begins
      // playback. The when/offset combo lets us schedule sample-accurately.
      src.start(when, offsetSeconds)
      return src
    },
    []
  )

  // ----------------------------------------------------------------------
  // Stop the currently playing source (if any) without firing the auto-
  // advance. Used for explicit user actions (pause, seek, track-row click).
  // ----------------------------------------------------------------------
  const stopCurrentSource = useCallback(() => {
    const src = sourceNodeRef.current
    if (!src) return
    suppressEndedRef.current = true
    src.onended = null
    try {
      src.stop()
    } catch {
      // already stopped — ignore
    }
    src.disconnect()
    sourceNodeRef.current = null
  }, [])

  // Cancel an in-flight rAF tick.
  const cancelTick = useCallback(() => {
    if (rafIdRef.current !== null) {
      cancelAnimationFrame(rafIdRef.current)
      rafIdRef.current = null
    }
  }, [])

  // ----------------------------------------------------------------------
  // Active-source state — drives currentTime tracking + "ended" handling.
  // We keep these in refs to avoid stale closures inside the rAF loop.
  // ----------------------------------------------------------------------
  const isPlayingRef = useRef(false)
  isPlayingRef.current = isPlaying

  const currentTrackIndexRef = useRef<number | null>(currentTrackIndex)
  currentTrackIndexRef.current = currentTrackIndex
  const tracksRef = useRef<Track[]>(tracks)
  tracksRef.current = tracks
  const onTrackChangeRef = useRef(onTrackChange)
  onTrackChangeRef.current = onTrackChange

  // ----------------------------------------------------------------------
  // Time-update tick. Web Audio doesn't surface a `timeupdate`-style event,
  // so we drive currentTime ourselves off audioContext.currentTime. rAF
  // ~60Hz when the page is visible; backgrounded tabs throttle to ~1Hz,
  // which still updates the OS lock-screen scrubber.
  // ----------------------------------------------------------------------
  const tick = useCallback(() => {
    rafIdRef.current = null
    const ctx = audioContextRef.current
    const buf = currentTrackBufRef.current?.buffer
    if (!ctx || !buf) return
    const t = ctx.currentTime - startedAtCtxTimeRef.current
    if (t >= 0) {
      setCurrentTime(Math.min(t, buf.duration))
    }
    if (isPlayingRef.current) {
      rafIdRef.current = requestAnimationFrame(tick)
    }
  }, [])

  const startTick = useCallback(() => {
    if (rafIdRef.current === null) {
      rafIdRef.current = requestAnimationFrame(tick)
    }
  }, [tick])

  // ----------------------------------------------------------------------
  // Auto-advance handler — fires when an AudioBufferSourceNode reaches the
  // end of its buffer naturally.
  // ----------------------------------------------------------------------
  const advanceToNextRef = useRef<() => void>(() => {})

  const handleSourceEnded = useCallback(() => {
    if (suppressEndedRef.current) {
      suppressEndedRef.current = false
      return
    }
    advanceToNextRef.current()
  }, [])

  // ----------------------------------------------------------------------
  // Build MediaSession metadata for a track. Pure helper.
  // ----------------------------------------------------------------------
  const buildMediaMetadata = useCallback(
    (track: Track | null): MediaMetadata | null => {
      if (
        !track ||
        typeof window === 'undefined' ||
        !('MediaMetadata' in window)
      ) {
        return null
      }
      const artwork =
        albumId != null
          ? [
              { src: getAlbumCoverUrl(slug, albumId, 512), sizes: '512x512', type: 'image/webp' },
              { src: getAlbumCoverUrl(slug, albumId, 256), sizes: '256x256', type: 'image/webp' },
              { src: getAlbumCoverUrl(slug, albumId, 128), sizes: '128x128', type: 'image/webp' },
            ]
          : albumCoverUrl
            ? [{ src: albumCoverUrl, sizes: '512x512' }]
            : []
      return new MediaMetadata({
        title: track.title || '',
        artist: track.artist || '',
        album: albumTitle || '',
        artwork,
      })
    },
    [albumCoverUrl, albumId, albumTitle, slug]
  )

  const pushMediaMetadataNow = useCallback(
    (track: Track | null) => {
      if (typeof navigator === 'undefined' || !('mediaSession' in navigator)) {
        return
      }
      try {
        const meta = buildMediaMetadata(track)
        navigator.mediaSession.metadata = meta
      } catch {
        // ignore
      }
    },
    [buildMediaMetadata]
  )

  // ----------------------------------------------------------------------
  // Kick off playback of a specific track. Decodes (or reuses cached
  // buffer), schedules a source node, hooks the ended callback, starts the
  // tick, and lazily preloads the next track.
  // ----------------------------------------------------------------------
  const loadAndPlayTrack = useCallback(
    async (trackIdx: number) => {
      const track = tracksRef.current[trackIdx]
      if (!track) return

      const ctx = ensureContext()
      if (!ctx) {
        setPlaybackError('Web Audio API is not available in this browser.')
        return
      }
      // Stop whatever was playing before (no auto-advance).
      stopCurrentSource()

      const generation = ++loadGenerationRef.current
      setPlaybackError(null)
      setIsLoading(true)

      // Promote the pre-decoded next-buffer if it matches.
      let decoded: DecodedTrack | null = null
      if (nextTrackBufRef.current?.trackId === track.id) {
        decoded = nextTrackBufRef.current
        nextTrackBufRef.current = null
      }
      try {
        if (!decoded) {
          decoded = await fetchAndDecode(track)
        }
      } catch (err) {
        if (loadGenerationRef.current !== generation) return
        console.error('[AudioPlayer] decode failed:', err)
        setPlaybackError('Failed to load audio file')
        setIsLoading(false)
        return
      }
      // Bail if a newer load took over while we were decoding.
      if (loadGenerationRef.current !== generation || !decoded) return

      currentTrackBufRef.current = decoded
      setDuration(decoded.buffer.duration)
      setCurrentTime(0)

      // Push metadata + playing state to the OS *before* the source
      // starts playing so the lock-screen tile updates synchronously.
      pushMediaMetadataNow(track)
      if (typeof navigator !== 'undefined' && 'mediaSession' in navigator) {
        try {
          navigator.mediaSession.playbackState = 'playing'
        } catch {
          // ignore
        }
      }

      const startedAt = ctx.currentTime
      startedAtCtxTimeRef.current = startedAt
      pauseOffsetRef.current = 0
      const src = startBuffer(decoded.buffer, 0, startedAt)
      if (!src) {
        setPlaybackError('Could not start audio source')
        setIsLoading(false)
        return
      }
      src.onended = handleSourceEnded
      sourceNodeRef.current = src
      setIsLoading(false)
      setIsPlaying(true)
      startTick()

      // Start preloading the *next* track in the background. We deliberately
      // don't await this — playback shouldn't wait on it, and an error here
      // is non-fatal (next track will just decode-on-demand instead).
      const next = tracksRef.current[trackIdx + 1]
      if (next && nextTrackBufRef.current?.trackId !== next.id) {
        nextTrackBufRef.current = null
        ;(async () => {
          try {
            const decodedNext = await fetchAndDecode(next)
            // Only stash if we're still on the same active track; otherwise
            // a newer load has already moved on.
            if (
              decodedNext &&
              currentTrackBufRef.current?.trackId === track.id
            ) {
              nextTrackBufRef.current = decodedNext
            }
          } catch (err) {
            console.warn('[AudioPlayer] preload failed:', err)
          }
        })()
      }
    },
    [
      ensureContext,
      fetchAndDecode,
      handleSourceEnded,
      pushMediaMetadataNow,
      startBuffer,
      startTick,
      stopCurrentSource,
    ]
  )

  // Concrete advanceToNext, set into the ref so handleSourceEnded can call
  // through it without a closure-staleness dance.
  useEffect(() => {
    advanceToNextRef.current = () => {
      const idx = currentTrackIndexRef.current
      const len = tracksRef.current.length
      if (idx === null || idx >= len - 1) {
        // End of album.
        stopCurrentSource()
        currentTrackBufRef.current = null
        setIsPlaying(false)
        setCurrentTime(0)
        cancelTick()
        if (typeof navigator !== 'undefined' && 'mediaSession' in navigator) {
          try {
            navigator.mediaSession.playbackState = 'none'
          } catch {
            // ignore
          }
        }
        onTrackChangeRef.current(null)
        return
      }
      const nextIdx = idx + 1
      onTrackChangeRef.current(nextIdx)
      // The track-change effect downstream calls loadAndPlayTrack(nextIdx).
    }
  }, [cancelTick, stopCurrentSource])

  // ----------------------------------------------------------------------
  // Effect: when the active track index changes, drive playback.
  // Compare against currentTrackBufRef to skip a redundant load if the
  // index changed but the underlying track is still the same (rare).
  // ----------------------------------------------------------------------
  useEffect(() => {
    if (currentTrackIndex === null) {
      // No track selected — stop everything cleanly.
      stopCurrentSource()
      currentTrackBufRef.current = null
      cancelTick()
      setIsPlaying(false)
      setCurrentTime(0)
      setDuration(0)
      return
    }
    const track = tracks[currentTrackIndex]
    if (!track) return
    if (currentTrackBufRef.current?.trackId === track.id && sourceNodeRef.current) {
      // Already playing this track — nothing to do.
      return
    }
    void loadAndPlayTrack(currentTrackIndex)
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [currentTrackIndex])

  // ----------------------------------------------------------------------
  // Volume → GainNode. Mute by zeroing gain (the GainNode keeps its
  // visual volume value separately from "muted" in our state).
  // ----------------------------------------------------------------------
  useEffect(() => {
    const gain = gainNodeRef.current
    if (!gain) return
    // Set gain directly — the previous setTargetAtTime smoothing ramped
    // every track start from the previous gain's interpolated value, which
    // showed up as "starts slower and lower" on the first second. Volume
    // slider clicks are acceptable; perceived fade-in is not.
    gain.gain.value = isMuted ? 0 : volume
  }, [volume, isMuted])

  // ----------------------------------------------------------------------
  // Playback Controls
  // ----------------------------------------------------------------------

  const play = useCallback(() => {
    if (currentTrackBufRef.current && sourceNodeRef.current === null) {
      // Resume from pause: recreate source at pauseOffset.
      const ctx = ensureContext()
      const buf = currentTrackBufRef.current.buffer
      if (!ctx) return
      const offset = pauseOffsetRef.current
      const startedAt = ctx.currentTime
      startedAtCtxTimeRef.current = startedAt - offset
      const src = startBuffer(buf, offset, startedAt)
      if (!src) return
      src.onended = handleSourceEnded
      sourceNodeRef.current = src
      setIsPlaying(true)
      startTick()
      if (typeof navigator !== 'undefined' && 'mediaSession' in navigator) {
        try {
          navigator.mediaSession.playbackState = 'playing'
        } catch {
          // ignore
        }
      }
      return
    }
    if (!currentTrack && tracks.length > 0) {
      onTrackChange(0)
      return
    }
  }, [
    currentTrack,
    ensureContext,
    handleSourceEnded,
    onTrackChange,
    startBuffer,
    startTick,
    tracks.length,
  ])

  const pause = useCallback(() => {
    const ctx = audioContextRef.current
    if (!ctx) return
    if (sourceNodeRef.current) {
      pauseOffsetRef.current = Math.min(
        ctx.currentTime - startedAtCtxTimeRef.current,
        currentTrackBufRef.current?.buffer.duration ?? 0
      )
    }
    stopCurrentSource()
    setIsPlaying(false)
    cancelTick()
    if (typeof navigator !== 'undefined' && 'mediaSession' in navigator) {
      try {
        navigator.mediaSession.playbackState = 'paused'
      } catch {
        // ignore
      }
    }
  }, [cancelTick, stopCurrentSource])

  const stop = useCallback(() => {
    pauseOffsetRef.current = 0
    stopCurrentSource()
    setIsPlaying(false)
    setCurrentTime(0)
    cancelTick()
  }, [cancelTick, stopCurrentSource])

  const playPause = useCallback(() => {
    if (isPlaying) {
      pause()
      return
    }
    if (currentTrackIndex === null && tracks.length > 0) {
      onTrackChange(0)
      return
    }
    play()
  }, [
    isPlaying,
    pause,
    play,
    currentTrackIndex,
    tracks.length,
    onTrackChange,
  ])

  const previousTrack = useCallback(() => {
    if (currentTrackIndex !== null && currentTrackIndex > 0) {
      onTrackChange(currentTrackIndex - 1)
    }
  }, [currentTrackIndex, onTrackChange])

  const nextTrack = useCallback(() => {
    if (currentTrackIndex !== null && currentTrackIndex < tracks.length - 1) {
      onTrackChange(currentTrackIndex + 1)
    }
  }, [currentTrackIndex, tracks.length, onTrackChange])

  const handleSeek = useCallback(
    (value: number[]) => {
      const buf = currentTrackBufRef.current?.buffer
      const ctx = audioContextRef.current
      if (!buf || !ctx) return
      const offset = Math.max(0, Math.min(value[0], buf.duration))
      const wasPlaying = sourceNodeRef.current !== null
      stopCurrentSource()
      pauseOffsetRef.current = offset
      setCurrentTime(offset)
      if (wasPlaying) {
        const startedAt = ctx.currentTime
        startedAtCtxTimeRef.current = startedAt - offset
        const src = startBuffer(buf, offset, startedAt)
        if (src) {
          src.onended = handleSourceEnded
          sourceNodeRef.current = src
        }
      }
    },
    [handleSourceEnded, startBuffer, stopCurrentSource]
  )

  const handleVolumeChange = useCallback(
    (value: number[]) => {
      const newVolume = value[0]
      setVolume(newVolume)
      if (newVolume > 0 && isMuted) {
        setIsMuted(false)
      }
    },
    [isMuted]
  )

  const toggleMute = useCallback(() => {
    setIsMuted((prev) => !prev)
  }, [])

  // ----------------------------------------------------------------------
  // MediaSession action handlers
  // ----------------------------------------------------------------------
  useEffect(() => {
    if (typeof navigator === 'undefined' || !('mediaSession' in navigator)) {
      return
    }
    const ms = navigator.mediaSession
    const safeSet = (action: MediaSessionAction, handler: (() => void) | null) => {
      try {
        ms.setActionHandler(action, handler)
      } catch {
        // unsupported actions — ignore
      }
    }
    safeSet('play', () => play())
    safeSet('pause', () => pause())
    safeSet('previoustrack', () => previousTrack())
    safeSet('nexttrack', () => nextTrack())
    safeSet('stop', () => stop())
    return () => {
      safeSet('play', null)
      safeSet('pause', null)
      safeSet('previoustrack', null)
      safeSet('nexttrack', null)
      safeSet('stop', null)
    }
  }, [play, pause, previousTrack, nextTrack, stop])

  // Keep position-state up to date so the OS lock-screen scrubber moves.
  useEffect(() => {
    if (typeof navigator === 'undefined' || !('mediaSession' in navigator)) {
      return
    }
    if (!isFinite(duration) || duration <= 0) return
    try {
      navigator.mediaSession.setPositionState?.({
        duration,
        position: Math.min(currentTime, duration),
        playbackRate: 1,
      })
    } catch {
      // ignore range errors
    }
  }, [currentTime, duration])

  // Fallback metadata sync (in case the immediate push in
  // loadAndPlayTrack lost a race with a parent re-render).
  useEffect(() => {
    pushMediaMetadataNow(currentTrack)
  }, [currentTrack, pushMediaMetadataNow])

  // ----------------------------------------------------------------------
  // Cleanup on unmount: stop sources, close AudioContext.
  // ----------------------------------------------------------------------
  useEffect(() => {
    return () => {
      cancelTick()
      stopCurrentSource()
      currentTrackBufRef.current = null
      nextTrackBufRef.current = null
      const sink = sinkAudioRef.current
      if (sink) {
        try {
          sink.pause()
          sink.srcObject = null
        } catch {
          // ignore
        }
      }
      const ctx = audioContextRef.current
      if (ctx) {
        try {
          ctx.close()
        } catch {
          // ignore
        }
        audioContextRef.current = null
        gainNodeRef.current = null
        mediaStreamDestRef.current = null
      }
    }
  }, [cancelTick, stopCurrentSource])

  // ----------------------------------------------------------------------
  // Render
  // ----------------------------------------------------------------------
  const hasTrack = currentTrack !== null
  const canPrevious = currentTrackIndex !== null && currentTrackIndex > 0
  const canNext = currentTrackIndex !== null && currentTrackIndex < tracks.length - 1

  // memoize so the slider's max prop doesn't churn on every tick.
  const sliderMax = useMemo(() => duration || 100, [duration])

  return (
    <div className="bg-card border rounded-lg p-4 space-y-3">
      {/* Hidden sink <audio> element. Web Audio output is piped here via
          MediaStreamDestination so the OS Media Session UI (lock-screen
          tile, Bluetooth headset controls) recognises the page as a
          media app. The user never sees or interacts with it. */}
      <audio
        ref={sinkAudioRef}
        playsInline
        // muted={false} explicit so iOS doesn't auto-mute background
        // playback; volume is controlled via the GainNode upstream.
      />

      {/* Now Playing Info */}
      <div className="text-center min-h-[44px]">
        {currentTrack ? (
          <>
            <p className="font-medium truncate">{currentTrack.title}</p>
            <p className="text-sm text-muted-foreground truncate">
              {currentTrack.artist}
            </p>
          </>
        ) : (
          <p className="text-muted-foreground">No track selected</p>
        )}
      </div>

      {/* Playback error */}
      {playbackError && (
        <div className="flex items-center gap-2 rounded-md bg-destructive/10 text-destructive text-sm px-3 py-2">
          <AlertCircle className="h-4 w-4 flex-shrink-0" />
          <span>{playbackError}</span>
        </div>
      )}

      {/* Progress Bar */}
      <div className="space-y-1">
        <Slider
          value={[currentTime]}
          min={0}
          max={sliderMax}
          step={1}
          onValueChange={handleSeek}
          disabled={!hasTrack}
          className="w-full"
        />
        <div className="flex justify-between text-xs text-muted-foreground">
          <span>{formatDuration(currentTime)}</span>
          <span>{formatDuration(duration)}</span>
        </div>
      </div>

      {/* Playback Controls */}
      <div className="flex items-center justify-center gap-2">
        <Button
          variant="ghost"
          size="icon"
          onClick={previousTrack}
          disabled={!canPrevious}
          aria-label="Previous track"
        >
          <SkipBack className="h-5 w-5" />
        </Button>

        <Button
          variant="ghost"
          size="icon"
          onClick={stop}
          disabled={!hasTrack}
          aria-label="Stop"
        >
          <Square className="h-5 w-5" />
        </Button>

        <Button
          variant="default"
          size="icon"
          onClick={playPause}
          disabled={tracks.length === 0 || isLoading}
          aria-label={isPlaying ? 'Pause' : 'Play'}
          className="h-12 w-12"
        >
          {isPlaying ? (
            <Pause className="h-6 w-6" />
          ) : (
            <Play className="h-6 w-6 ml-0.5" />
          )}
        </Button>

        <Button
          variant="ghost"
          size="icon"
          onClick={nextTrack}
          disabled={!canNext}
          aria-label="Next track"
        >
          <SkipForward className="h-5 w-5" />
        </Button>
      </div>

      {/* Volume Control */}
      <div className="flex items-center gap-2 px-2">
        <Button
          variant="ghost"
          size="icon"
          onClick={toggleMute}
          aria-label={isMuted ? 'Unmute' : 'Mute'}
          className="h-8 w-8"
        >
          {isMuted || volume === 0 ? (
            <VolumeX className="h-4 w-4" />
          ) : (
            <Volume2 className="h-4 w-4" />
          )}
        </Button>
        <Slider
          value={[isMuted ? 0 : volume]}
          min={0}
          max={1}
          step={0.01}
          onValueChange={handleVolumeChange}
          className="w-24"
          aria-label="Volume"
        />
      </div>
    </div>
  )
}

export default AudioPlayer
