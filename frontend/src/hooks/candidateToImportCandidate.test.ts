import { describe, it, expect } from 'vitest'
import { candidateToImportCandidate } from './useBeetsImport'
import type { Candidate } from '@/types/beets-import'

const base: Candidate = {
  source: 'Deezer',
  sourceId: 'dz-1',
  similarity: 1,
  artist: 'Artist',
  album: 'Album',
  year: 2020,
  label: null,
  country: null,
  media: null,
  tracks: [],
  changes: [],
  trackChanges: [],
}

describe('candidateToImportCandidate — cover URL threading (#148)', () => {
  it('carries the candidate cover URL into the import request', () => {
    const result = candidateToImportCandidate({
      ...base,
      coverUrl: 'https://cdn.example/cover_xl.jpg',
    })
    expect(result.coverUrl).toBe('https://cdn.example/cover_xl.jpg')
  })

  it('leaves coverUrl undefined when the candidate has none', () => {
    expect(candidateToImportCandidate(base).coverUrl).toBeUndefined()
    expect(candidateToImportCandidate({ ...base, coverUrl: null }).coverUrl).toBeUndefined()
  })
})
