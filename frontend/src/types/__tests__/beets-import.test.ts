import { describe, it, expect } from 'vitest'
import {
  LINK_PATTERNS,
  detectProvider,
  isValidLink,
} from '../beets-import'

describe('Link Validation Utilities', () => {
  describe('LINK_PATTERNS', () => {
    describe('Deezer pattern', () => {
      it('should match basic deezer album URL', () => {
        expect(LINK_PATTERNS.deezer.test('https://www.deezer.com/album/12345')).toBe(true)
      })

      it('should match deezer URL without www', () => {
        expect(LINK_PATTERNS.deezer.test('https://deezer.com/album/12345')).toBe(true)
      })

      it('should match deezer URL with country code', () => {
        expect(LINK_PATTERNS.deezer.test('https://www.deezer.com/us/album/12345')).toBe(true)
        expect(LINK_PATTERNS.deezer.test('https://www.deezer.com/fr/album/12345')).toBe(true)
        expect(LINK_PATTERNS.deezer.test('https://www.deezer.com/de/album/12345')).toBe(true)
      })

      it('should match deezer URL with http', () => {
        expect(LINK_PATTERNS.deezer.test('http://www.deezer.com/album/12345')).toBe(true)
      })

      it('should not match deezer track URL', () => {
        expect(LINK_PATTERNS.deezer.test('https://www.deezer.com/track/12345')).toBe(false)
      })
    })

    describe('Spotify pattern', () => {
      it('should match basic spotify album URL', () => {
        expect(LINK_PATTERNS.spotify.test('https://open.spotify.com/album/4LH4d3cOWNNsVw41Gqt2kv')).toBe(true)
      })

      it('should match spotify URL with intl prefix', () => {
        expect(LINK_PATTERNS.spotify.test('https://open.spotify.com/intl-de/album/4LH4d3cOWNNsVw41Gqt2kv')).toBe(true)
        expect(LINK_PATTERNS.spotify.test('https://open.spotify.com/intl-fr/album/4LH4d3cOWNNsVw41Gqt2kv')).toBe(true)
      })

      it('should match spotify URL with http', () => {
        expect(LINK_PATTERNS.spotify.test('http://open.spotify.com/album/abc123')).toBe(true)
      })

      it('should not match spotify track URL', () => {
        expect(LINK_PATTERNS.spotify.test('https://open.spotify.com/track/abc123')).toBe(false)
      })

      it('should not match spotify playlist URL', () => {
        expect(LINK_PATTERNS.spotify.test('https://open.spotify.com/playlist/abc123')).toBe(false)
      })
    })

    describe('Discogs pattern', () => {
      it('should match basic discogs release URL', () => {
        expect(LINK_PATTERNS.discogs.test('https://www.discogs.com/release/12345')).toBe(true)
      })

      it('should match discogs URL without www', () => {
        expect(LINK_PATTERNS.discogs.test('https://discogs.com/release/12345')).toBe(true)
      })

      it('should match discogs master URL', () => {
        expect(LINK_PATTERNS.discogs.test('https://www.discogs.com/master/12345')).toBe(true)
      })

      it('should match discogs URL with http', () => {
        expect(LINK_PATTERNS.discogs.test('http://www.discogs.com/release/12345')).toBe(true)
      })

      it('should not match discogs artist URL', () => {
        expect(LINK_PATTERNS.discogs.test('https://www.discogs.com/artist/12345')).toBe(false)
      })
    })

    describe('MusicBrainz URL pattern', () => {
      it('should match musicbrainz release URL', () => {
        expect(LINK_PATTERNS.musicbrainzUrl.test(
          'https://musicbrainz.org/release/a1b2c3d4-e5f6-7890-abcd-ef1234567890'
        )).toBe(true)
      })

      it('should match musicbrainz URL with www', () => {
        expect(LINK_PATTERNS.musicbrainzUrl.test(
          'https://www.musicbrainz.org/release/a1b2c3d4-e5f6-7890-abcd-ef1234567890'
        )).toBe(true)
      })

      it('should match musicbrainz URL with http', () => {
        expect(LINK_PATTERNS.musicbrainzUrl.test(
          'http://musicbrainz.org/release/a1b2c3d4-e5f6-7890-abcd-ef1234567890'
        )).toBe(true)
      })

      it('should not match invalid UUID in URL', () => {
        expect(LINK_PATTERNS.musicbrainzUrl.test(
          'https://musicbrainz.org/release/invalid-uuid'
        )).toBe(false)
      })

      it('should not match musicbrainz artist URL', () => {
        expect(LINK_PATTERNS.musicbrainzUrl.test(
          'https://musicbrainz.org/artist/a1b2c3d4-e5f6-7890-abcd-ef1234567890'
        )).toBe(false)
      })
    })

    describe('MusicBrainz UUID pattern', () => {
      it('should match valid UUID', () => {
        expect(LINK_PATTERNS.musicbrainzUuid.test('a1b2c3d4-e5f6-7890-abcd-ef1234567890')).toBe(true)
      })

      it('should match UUID with uppercase letters', () => {
        expect(LINK_PATTERNS.musicbrainzUuid.test('A1B2C3D4-E5F6-7890-ABCD-EF1234567890')).toBe(true)
      })

      it('should not match partial UUID', () => {
        expect(LINK_PATTERNS.musicbrainzUuid.test('a1b2c3d4-e5f6-7890')).toBe(false)
      })

      it('should not match UUID with extra characters', () => {
        expect(LINK_PATTERNS.musicbrainzUuid.test('a1b2c3d4-e5f6-7890-abcd-ef1234567890-extra')).toBe(false)
      })

      it('should not match URL as UUID', () => {
        expect(LINK_PATTERNS.musicbrainzUuid.test(
          'https://musicbrainz.org/release/a1b2c3d4-e5f6-7890-abcd-ef1234567890'
        )).toBe(false)
      })
    })
  })

  describe('detectProvider', () => {
    it('should detect Deezer from URL', () => {
      expect(detectProvider('https://www.deezer.com/album/12345')).toBe('deezer')
      expect(detectProvider('https://deezer.com/us/album/98765')).toBe('deezer')
    })

    it('should detect Spotify from URL', () => {
      expect(detectProvider('https://open.spotify.com/album/4LH4d3cOWNNsVw41Gqt2kv')).toBe('spotify')
      expect(detectProvider('https://open.spotify.com/intl-de/album/abc123')).toBe('spotify')
    })

    it('should detect Discogs from URL', () => {
      expect(detectProvider('https://www.discogs.com/release/12345')).toBe('discogs')
      expect(detectProvider('https://discogs.com/master/67890')).toBe('discogs')
    })

    it('should detect MusicBrainz from URL', () => {
      expect(detectProvider(
        'https://musicbrainz.org/release/a1b2c3d4-e5f6-7890-abcd-ef1234567890'
      )).toBe('musicbrainz')
    })

    it('should detect MusicBrainz from UUID only', () => {
      expect(detectProvider('a1b2c3d4-e5f6-7890-abcd-ef1234567890')).toBe('musicbrainz')
    })

    it('should return null for invalid links', () => {
      expect(detectProvider('https://invalid-site.com/album/123')).toBe(null)
      expect(detectProvider('not-a-url')).toBe(null)
      expect(detectProvider('')).toBe(null)
    })

    it('should trim whitespace before detection', () => {
      expect(detectProvider('  https://www.deezer.com/album/12345  ')).toBe('deezer')
    })
  })

  describe('isValidLink', () => {
    it('should return true for valid Deezer links', () => {
      expect(isValidLink('https://www.deezer.com/album/12345')).toBe(true)
    })

    it('should return true for valid Spotify links', () => {
      expect(isValidLink('https://open.spotify.com/album/abc123')).toBe(true)
    })

    it('should return true for valid Discogs links', () => {
      expect(isValidLink('https://www.discogs.com/release/12345')).toBe(true)
    })

    it('should return true for valid MusicBrainz URLs', () => {
      expect(isValidLink(
        'https://musicbrainz.org/release/a1b2c3d4-e5f6-7890-abcd-ef1234567890'
      )).toBe(true)
    })

    it('should return true for valid MusicBrainz UUIDs', () => {
      expect(isValidLink('a1b2c3d4-e5f6-7890-abcd-ef1234567890')).toBe(true)
    })

    it('should return false for invalid links', () => {
      expect(isValidLink('https://invalid-site.com/album/123')).toBe(false)
      expect(isValidLink('not-a-url')).toBe(false)
      expect(isValidLink('')).toBe(false)
    })

    it('should return false for track URLs', () => {
      expect(isValidLink('https://open.spotify.com/track/abc123')).toBe(false)
      expect(isValidLink('https://www.deezer.com/track/12345')).toBe(false)
    })
  })
})
