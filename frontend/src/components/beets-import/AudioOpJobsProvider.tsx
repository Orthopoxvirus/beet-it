import {
  createContext,
  useCallback,
  useContext,
  useEffect,
  useMemo,
  useRef,
  useState,
  type ReactNode,
} from 'react'
import { useQueryClient } from '@tanstack/react-query'

import {
  getAudioOpStatus,
  startConvertAudio,
  startDedupeWav,
} from '@/api/beets-import'
import { importTreeKeys } from '@/hooks/useImportTree'
import { scanKeys } from '@/hooks/useScanStatus'
import { beetsAnalysisKeys } from '@/hooks/useBeetsAnalysis'
import { toast } from '@/components/ui/toast'
import type {
  AudioOpActiveStatus,
  ConvertAudioParams,
  ConvertTarget,
} from '@/types/beets-import'

// ============================================================================
// Types
// ============================================================================

export type AudioOpKind = 'convert' | 'dedupe'

interface AudioOpJobEntry {
  /** Backend job id; null in the brief window before the POST returns. */
  jobId: string | null
  kind: AudioOpKind
  status: AudioOpActiveStatus
  /** Convert target, kept only to word the completion toast. */
  targetFormat?: ConvertTarget
}

export interface AudioOpJobsApi {
  /** Active (queued/running) jobs keyed by absolute album path. */
  activeJobs: Record<string, AudioOpJobEntry>
  /** Enqueue a WAV/WMA → FLAC/MP3 conversion for an album. No-op if one is already running. */
  startConvert: (albumPath: string, params: ConvertAudioParams) => void
  /** Enqueue a duplicate-WAV cleanup for an album. No-op if one is already running. */
  startDedupe: (albumPath: string) => void
  /** The album's active status (queued/running), or undefined when idle. */
  statusFor: (albumPath: string) => AudioOpActiveStatus | undefined
  /** Whether the album currently has a queued or running audio op. */
  isActive: (albumPath: string) => boolean
}

const AudioOpJobsContext = createContext<AudioOpJobsApi | null>(null)

/**
 * Read the shared audio-op registry. Returns null when no provider is mounted
 * (the standalone /beets and Prepare pages), so consumers fall back to their own
 * local convert state.
 */
export function useAudioOpJobs(): AudioOpJobsApi | null {
  return useContext(AudioOpJobsContext)
}

const POLL_INTERVAL_MS = 1500

// ============================================================================
// Provider
// ============================================================================

interface AudioOpJobsProviderProps {
  librarySlug: string
  /** Absolute import root (no trailing slash); normalises relative paths to keys. */
  importBasePath: string
  /** Select an album in the tree — wired to the completion toast's album link. */
  onSelectAlbum?: (albumPath: string) => void
  children: ReactNode
}

const albumNameOf = (key: string) => key.split('/').filter(Boolean).pop() || key

/**
 * Owns every in-flight WAV/WMA convert + dedup job for the combined import view,
 * keyed by absolute album path. Because it lives above the album list and the
 * candidate/local-album cards — and outlives album switches — each album's
 * spinner is driven by *its own* job, not by whichever album happens to be
 * selected. Jobs are polled to completion here (not in the triggering component)
 * so the work is truly background, and a toast fires when each album finishes.
 */
export function AudioOpJobsProvider({
  librarySlug,
  importBasePath,
  onSelectAlbum,
  children,
}: AudioOpJobsProviderProps) {
  const queryClient = useQueryClient()
  const [jobs, setJobs] = useState<Record<string, AudioOpJobEntry>>({})

  // Refs keep the long-lived poll loops reading current values, never stale ones.
  const jobsRef = useRef(jobs)
  const mountedRef = useRef(true)
  const onSelectAlbumRef = useRef(onSelectAlbum)
  const baseRef = useRef(importBasePath)
  const slugRef = useRef(librarySlug)
  useEffect(() => {
    jobsRef.current = jobs
  }, [jobs])
  useEffect(() => {
    onSelectAlbumRef.current = onSelectAlbum
  }, [onSelectAlbum])
  useEffect(() => {
    baseRef.current = importBasePath
  }, [importBasePath])
  useEffect(() => {
    slugRef.current = librarySlug
  }, [librarySlug])
  useEffect(
    () => () => {
      mountedRef.current = false
    },
    []
  )

  // Normalise any album path to one absolute key: the panel passes absolute
  // paths, the folder table passes import-root-relative ones — both must collapse
  // to the same entry so the tree spinner and either convert button agree.
  const toKey = useCallback((path: string): string => {
    const base = baseRef.current
    if (!path || !base) return path
    if (path === base || path.startsWith(`${base}/`)) return path
    if (path.startsWith('/')) return path // a different absolute path — leave as-is
    return `${base}/${path}`
  }, [])

  const removeJob = useCallback((key: string) => {
    setJobs((prev) => {
      if (!(key in prev)) return prev
      const next = { ...prev }
      delete next[key]
      return next
    })
  }, [])

  const setStatus = useCallback((key: string, status: AudioOpActiveStatus) => {
    setJobs((prev) => {
      const entry = prev[key]
      if (!entry || entry.status === status) return prev
      return { ...prev, [key]: { ...entry, status } }
    })
  }, [])

  const setJobId = useCallback((key: string, jobId: string) => {
    setJobs((prev) => {
      const entry = prev[key]
      if (!entry) return prev
      return { ...prev, [key]: { ...entry, jobId } }
    })
  }, [])

  const refreshAfterComplete = useCallback(() => {
    const slug = slugRef.current
    queryClient.invalidateQueries({ queryKey: importTreeKeys.byLibrary(slug) })
    queryClient.invalidateQueries({ queryKey: [...scanKeys.importItems(), slug] })
    queryClient.invalidateQueries({ queryKey: beetsAnalysisKeys.cacheStatus(slug) })
  }, [queryClient])

  const fireDoneToast = useCallback(
    (key: string, kind: AudioOpKind, targetFormat?: ConvertTarget) => {
      const name = albumNameOf(key)
      const link = (
        <button
          type="button"
          onClick={() => onSelectAlbumRef.current?.(key)}
          className="font-semibold underline underline-offset-2 hover:opacity-80"
          data-testid="audio-op-toast-album"
        >
          {name}
        </button>
      )
      toast.success({
        title: kind === 'dedupe' ? 'Cleanup complete' : 'Conversion complete',
        description:
          kind === 'dedupe' ? (
            <span>{link} — duplicate WAVs removed</span>
          ) : (
            <span>
              {link} converted{targetFormat ? ` to ${targetFormat.toUpperCase()}` : ''}
            </span>
          ),
      })
    },
    []
  )

  // Poll one job to a terminal state, surfacing queued → running along the way
  // and firing the completion/failure toast at the end.
  const pollJob = useCallback(
    async (
      key: string,
      jobId: string,
      kind: AudioOpKind,
      targetFormat?: ConvertTarget
    ) => {
      const slug = slugRef.current
      for (;;) {
        await new Promise((r) => setTimeout(r, POLL_INTERVAL_MS))
        if (!mountedRef.current) return
        let status
        try {
          status = await getAudioOpStatus(slug, jobId)
        } catch {
          continue // transient network hiccup — keep polling
        }
        if (!mountedRef.current) return

        if (status.status === 'queued' || status.status === 'running') {
          setStatus(key, status.status)
          continue
        }

        // Terminal: drop the entry, refresh dependent views, notify.
        removeJob(key)
        refreshAfterComplete()
        if (status.status === 'completed') {
          fireDoneToast(key, kind, targetFormat)
        } else {
          toast.error({
            title: kind === 'dedupe' ? 'Cleanup failed' : 'Conversion failed',
            description: `${albumNameOf(key)}: ${status.error || 'operation failed'}`,
          })
        }
        return
      }
    },
    [setStatus, removeJob, refreshAfterComplete, fireDoneToast]
  )

  const startConvert = useCallback(
    (albumPath: string, params: ConvertAudioParams) => {
      const key = toKey(albumPath)
      if (jobsRef.current[key]) return // already queued/running for this album
      const entry: AudioOpJobEntry = {
        jobId: null,
        kind: 'convert',
        status: 'queued',
        targetFormat: params.targetFormat,
      }
      jobsRef.current = { ...jobsRef.current, [key]: entry }
      setJobs((prev) => ({ ...prev, [key]: entry }))

      startConvertAudio(
        slugRef.current,
        albumPath,
        params.sourceFormat,
        params.targetFormat,
        params.deleteOriginals
      )
        .then((job) => {
          if (!mountedRef.current) return
          setJobId(key, job.jobId)
          if (job.status === 'running') setStatus(key, 'running')
          pollJob(key, job.jobId, 'convert', params.targetFormat)
        })
        .catch((err) => {
          if (!mountedRef.current) return
          removeJob(key)
          toast.error({
            title: 'Conversion failed',
            description: `${albumNameOf(key)}: ${
              err instanceof Error ? err.message : 'could not start'
            }`,
          })
        })
    },
    [toKey, setJobId, setStatus, pollJob, removeJob]
  )

  const startDedupe = useCallback(
    (albumPath: string) => {
      const key = toKey(albumPath)
      if (jobsRef.current[key]) return
      const entry: AudioOpJobEntry = { jobId: null, kind: 'dedupe', status: 'queued' }
      jobsRef.current = { ...jobsRef.current, [key]: entry }
      setJobs((prev) => ({ ...prev, [key]: entry }))

      startDedupeWav(slugRef.current, albumPath)
        .then((job) => {
          if (!mountedRef.current) return
          setJobId(key, job.jobId)
          if (job.status === 'running') setStatus(key, 'running')
          pollJob(key, job.jobId, 'dedupe')
        })
        .catch((err) => {
          if (!mountedRef.current) return
          removeJob(key)
          toast.error({
            title: 'Cleanup failed',
            description: `${albumNameOf(key)}: ${
              err instanceof Error ? err.message : 'could not start'
            }`,
          })
        })
    },
    [toKey, setJobId, setStatus, pollJob, removeJob]
  )

  const statusFor = useCallback(
    (albumPath: string) => jobs[toKey(albumPath)]?.status,
    [jobs, toKey]
  )
  const isActive = useCallback(
    (albumPath: string) => !!jobs[toKey(albumPath)],
    [jobs, toKey]
  )

  const value = useMemo<AudioOpJobsApi>(
    () => ({ activeJobs: jobs, startConvert, startDedupe, statusFor, isActive }),
    [jobs, startConvert, startDedupe, statusFor, isActive]
  )

  return (
    <AudioOpJobsContext.Provider value={value}>
      {children}
    </AudioOpJobsContext.Provider>
  )
}
