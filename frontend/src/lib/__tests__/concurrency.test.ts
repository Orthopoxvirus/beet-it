import { describe, it, expect } from 'vitest'

import { runPool } from '../concurrency'

describe('runPool', () => {
  it('processes every item exactly once', async () => {
    const items = [1, 2, 3, 4, 5]
    const seen: number[] = []
    await runPool(items, 2, async (n) => {
      seen.push(n)
    })
    expect(seen.sort()).toEqual(items)
  })

  it('never exceeds the concurrency limit', async () => {
    let inFlight = 0
    let peak = 0
    const items = Array.from({ length: 10 }, (_, i) => i)
    await runPool(items, 3, async () => {
      inFlight++
      peak = Math.max(peak, inFlight)
      await Promise.resolve()
      inFlight--
    })
    expect(peak).toBeLessThanOrEqual(3)
  })

  it('handles an empty list without spawning runners', async () => {
    let calls = 0
    await runPool([], 4, async () => {
      calls++
    })
    expect(calls).toBe(0)
  })
})
