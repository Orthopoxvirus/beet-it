import { keepPreviousData, useQuery } from '@tanstack/react-query'

import { fetchTitleArtists, fetchTitles, type TitleFilters } from '@/api/titles'

export const titleKeys = {
  all: ['titles'] as const,
  list: (slug: string, filters: TitleFilters, page: number, perPage: number) =>
    [...titleKeys.all, 'list', { slug, ...filters, page, perPage }] as const,
  // Artist dropdown depends only on search + BPM, not the selection itself.
  artists: (slug: string, filters: TitleFilters) =>
    [
      ...titleKeys.all,
      'artists',
      {
        slug,
        search: filters.search,
        bpmMin: filters.bpmMin,
        bpmMax: filters.bpmMax,
        includeHalfDouble: filters.includeHalfDouble,
      },
    ] as const,
}

export function useTitles(
  slug: string | undefined,
  filters: TitleFilters,
  page: number,
  perPage: number
) {
  return useQuery({
    queryKey: titleKeys.list(slug || '', filters, page, perPage),
    queryFn: () => fetchTitles(slug as string, filters, page, perPage),
    enabled: !!slug,
    // Keep the previous page on screen while the next one loads — avoids the
    // table collapsing to a spinner on every keystroke/page change.
    placeholderData: keepPreviousData,
  })
}

export function useTitleArtists(slug: string | undefined, filters: TitleFilters) {
  return useQuery({
    queryKey: titleKeys.artists(slug || '', filters),
    queryFn: () => fetchTitleArtists(slug as string, filters),
    enabled: !!slug,
    placeholderData: keepPreviousData,
  })
}
