import '@testing-library/jest-dom'
import { afterEach, vi } from 'vitest'
import { cleanup } from '@testing-library/react'

// Cleanup after each test
afterEach(() => {
  cleanup()
})

// Mock scrollIntoView - needed for Radix UI Select components
Element.prototype.scrollIntoView = vi.fn()

// Mock ResizeObserver - needed for Radix UI components.
// Use a real class so vi.restoreAllMocks() in test afterEach hooks doesn't strip the implementation.
class MockResizeObserver {
  observe() {}
  unobserve() {}
  disconnect() {}
}
;(global as unknown as { ResizeObserver: typeof MockResizeObserver }).ResizeObserver = MockResizeObserver

// Mock hasPointerCapture and related pointer methods
Element.prototype.hasPointerCapture = vi.fn(() => false)
Element.prototype.setPointerCapture = vi.fn()
Element.prototype.releasePointerCapture = vi.fn()

// Mock EventSource for SSE testing
class MockEventSource {
  static instances: MockEventSource[] = []

  url: string
  readyState: number = 0
  onopen: ((event: Event) => void) | null = null
  onerror: ((event: Event) => void) | null = null
  onmessage: ((event: MessageEvent) => void) | null = null

  private listeners: Map<string, ((event: MessageEvent) => void)[]> = new Map()

  constructor(url: string) {
    this.url = url
    MockEventSource.instances.push(this)
  }

  addEventListener(type: string, listener: (event: MessageEvent) => void) {
    if (!this.listeners.has(type)) {
      this.listeners.set(type, [])
    }
    this.listeners.get(type)!.push(listener)
  }

  removeEventListener(type: string, listener: (event: MessageEvent) => void) {
    const listeners = this.listeners.get(type)
    if (listeners) {
      const index = listeners.indexOf(listener)
      if (index > -1) {
        listeners.splice(index, 1)
      }
    }
  }

  close() {
    this.readyState = 2
    const index = MockEventSource.instances.indexOf(this)
    if (index > -1) {
      MockEventSource.instances.splice(index, 1)
    }
  }

  // Test helpers
  simulateOpen() {
    this.readyState = 1
    if (this.onopen) {
      this.onopen(new Event('open'))
    }
  }

  simulateError() {
    if (this.onerror) {
      this.onerror(new Event('error'))
    }
  }

  simulateMessage(type: string, data: unknown) {
    const event = new MessageEvent(type, {
      data: JSON.stringify(data),
    })

    const listeners = this.listeners.get(type) || []
    listeners.forEach((listener) => listener(event))
  }

  static reset() {
    MockEventSource.instances = []
  }

  static getLastInstance(): MockEventSource | undefined {
    return MockEventSource.instances[MockEventSource.instances.length - 1]
  }
}

// Assign to global
;(global as unknown as { EventSource: typeof MockEventSource }).EventSource = MockEventSource

// Export for test usage
export { MockEventSource }

// Mock fetch for API tests
global.fetch = vi.fn()

// Mock environment variables
vi.stubEnv('VITE_API_URL', '/api')

// ---------------------------------------------------------------------------
// Web Audio API mock — jsdom doesn't ship one, so AudioPlayer's ensureContext
// call returns null and the component sits in its "Web Audio API not
// available" branch. A minimal mock covering the surface AudioPlayer touches
// (AudioContext, createGain, decodeAudioData, createBufferSource,
// createMediaStreamDestination, ctx.destination, MediaMetadata) lets the
// playback path actually run under tests.
// ---------------------------------------------------------------------------
class MockAudioBufferSourceNode {
  buffer: unknown = null
  onended: ((this: unknown, ev: Event) => unknown) | null = null
  connect = vi.fn()
  disconnect = vi.fn()
  start = vi.fn()
  stop = vi.fn()
}

class MockGainNode {
  gain = { value: 1 }
  connect = vi.fn()
  disconnect = vi.fn()
}

class MockMediaStreamAudioDestinationNode {
  stream = {} as MediaStream
}

class MockAudioContext {
  state: 'suspended' | 'running' | 'closed' = 'running'
  currentTime = 0
  destination = {} as AudioDestinationNode

  createGain() {
    return new MockGainNode()
  }
  createBufferSource() {
    return new MockAudioBufferSourceNode()
  }
  createMediaStreamDestination() {
    return new MockMediaStreamAudioDestinationNode()
  }
  decodeAudioData(
    _data: ArrayBuffer,
    success?: (buf: unknown) => void,
    _error?: (err: unknown) => void
  ): Promise<unknown> {
    const buf = { duration: 60, sampleRate: 44100, numberOfChannels: 2, length: 60 * 44100 }
    if (success) success(buf)
    return Promise.resolve(buf)
  }
  resume() {
    this.state = 'running'
    return Promise.resolve()
  }
  suspend() {
    this.state = 'suspended'
    return Promise.resolve()
  }
  close() {
    this.state = 'closed'
    return Promise.resolve()
  }
}

;(global as unknown as { AudioContext: typeof MockAudioContext }).AudioContext = MockAudioContext
;(window as unknown as { AudioContext: typeof MockAudioContext }).AudioContext = MockAudioContext

// jsdom doesn't implement <audio> playback controls; stub them so components
// that call audio.play()/pause() (e.g. the import-folder track preview) don't
// emit "Not implemented" noise under tests.
HTMLMediaElement.prototype.play = vi.fn().mockResolvedValue(undefined)
HTMLMediaElement.prototype.pause = vi.fn()

// MediaMetadata is read by AudioPlayer for lock-screen metadata; jsdom omits it.
class MockMediaMetadata {
  title: string
  artist: string
  album: string
  artwork: unknown
  constructor(init: { title?: string; artist?: string; album?: string; artwork?: unknown } = {}) {
    this.title = init.title ?? ''
    this.artist = init.artist ?? ''
    this.album = init.album ?? ''
    this.artwork = init.artwork ?? []
  }
}
;(global as unknown as { MediaMetadata: typeof MockMediaMetadata }).MediaMetadata = MockMediaMetadata
;(window as unknown as { MediaMetadata: typeof MockMediaMetadata }).MediaMetadata = MockMediaMetadata
