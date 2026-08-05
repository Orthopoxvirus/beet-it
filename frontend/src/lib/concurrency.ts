// Bounded-concurrency runner used to queue + rate-limit fan-out work (issue
// #150: searching every missing album's cover online without firing N requests
// at once). It acts as a queue — items wait for a free slot — and a rate
// limiter — never more than `concurrency` workers run in parallel. Completion
// order is not guaranteed; each item is handed to `worker` exactly once.
export async function runPool<T>(
  items: readonly T[],
  concurrency: number,
  worker: (item: T, index: number) => Promise<void>
): Promise<void> {
  const limit = Math.max(1, Math.min(concurrency, items.length))
  let cursor = 0
  // JS runs single-threaded, so `cursor++` hands each index out exactly once
  // even though several runners share it.
  const runners = Array.from({ length: limit }, async () => {
    while (cursor < items.length) {
      const index = cursor++
      await worker(items[index], index)
    }
  })
  await Promise.all(runners)
}
