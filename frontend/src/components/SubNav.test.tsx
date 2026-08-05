import { describe, it, expect, vi } from 'vitest'
import { render, screen } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { MemoryRouter } from 'react-router-dom'
import SubNav from './SubNav'

const libraryItems = [
  { label: 'Albums', to: 'albums' },
  { label: 'Batch Edit', to: 'batch-edit' },
  { label: 'Settings', to: 'settings' },
]

const importItems = [
  { label: 'Beets', to: 'beets' },
  { label: 'Upload', to: 'upload' },
]

function renderSubNav(
  props: {
    items?: { label: string; to: string }[]
    basePath?: string
    collapsed?: boolean
    onLinkClick?: () => void
  },
  initialRoute = '/libraries/my-music/albums'
) {
  return render(
    <MemoryRouter initialEntries={[initialRoute]}>
      <SubNav
        items={props.items || libraryItems}
        basePath={props.basePath || '/libraries/my-music'}
        collapsed={props.collapsed}
        onLinkClick={props.onLinkClick}
      />
    </MemoryRouter>
  )
}

describe('SubNav', () => {
  describe('rendering', () => {
    it('renders all navigation items', () => {
      renderSubNav({ items: libraryItems })
      expect(screen.getByText('Albums')).toBeInTheDocument()
      expect(screen.getByText('Batch Edit')).toBeInTheDocument()
      expect(screen.getByText('Settings')).toBeInTheDocument()
    })

    it('renders import navigation items', () => {
      renderSubNav({ items: importItems, basePath: '/import/vinyl-rips' })
      expect(screen.getByText('Beets')).toBeInTheDocument()
      expect(screen.getByText('Upload')).toBeInTheDocument()
    })

    it('renders nothing when collapsed', () => {
      const { container } = renderSubNav({ collapsed: true })
      expect(container).toBeEmptyDOMElement()
    })

    it('does not render a title header', () => {
      renderSubNav({})
      // The title/header was removed in the refactor
      // Ensure no uppercase tracking text exists (old title style)
      const uppercaseElements = document.querySelectorAll('.uppercase')
      expect(uppercaseElements.length).toBe(0)
    })
  })

  describe('navigation links', () => {
    it('generates correct href for library items', () => {
      renderSubNav({ basePath: '/libraries/my-music' })

      expect(screen.getByRole('link', { name: 'Albums' })).toHaveAttribute(
        'href',
        '/libraries/my-music/albums'
      )
      expect(screen.getByRole('link', { name: 'Batch Edit' })).toHaveAttribute(
        'href',
        '/libraries/my-music/batch-edit'
      )
      expect(screen.getByRole('link', { name: 'Settings' })).toHaveAttribute(
        'href',
        '/libraries/my-music/settings'
      )
    })

    it('generates correct href for import items', () => {
      renderSubNav({ items: importItems, basePath: '/import/vinyl-rips' })

      expect(screen.getByRole('link', { name: 'Beets' })).toHaveAttribute(
        'href',
        '/import/vinyl-rips/beets'
      )
      expect(screen.getByRole('link', { name: 'Upload' })).toHaveAttribute(
        'href',
        '/import/vinyl-rips/upload'
      )
    })
  })

  describe('active state', () => {
    it('highlights the active link based on current route', () => {
      renderSubNav({}, '/libraries/my-music/albums')

      const albumsLink = screen.getByRole('link', { name: 'Albums' })
      const settingsLink = screen.getByRole('link', { name: 'Settings' })

      // Active link should have the active class (font-medium)
      expect(albumsLink.className).toContain('font-medium')
      // Inactive link should not have the active class
      expect(settingsLink.className).not.toContain('font-medium')
    })

    it('highlights settings when on settings route', () => {
      renderSubNav({}, '/libraries/my-music/settings')

      const albumsLink = screen.getByRole('link', { name: 'Albums' })
      const settingsLink = screen.getByRole('link', { name: 'Settings' })

      expect(settingsLink.className).toContain('font-medium')
      expect(albumsLink.className).not.toContain('font-medium')
    })

    it('highlights correct import page', () => {
      renderSubNav(
        { items: importItems, basePath: '/import/vinyl-rips' },
        '/import/vinyl-rips/upload'
      )

      const beetsLink = screen.getByRole('link', { name: 'Beets' })
      const uploadLink = screen.getByRole('link', { name: 'Upload' })

      expect(uploadLink.className).toContain('font-medium')
      expect(beetsLink.className).not.toContain('font-medium')
    })
  })

  describe('onLinkClick callback', () => {
    it('calls onLinkClick when a link is clicked', async () => {
      const onLinkClick = vi.fn()
      const user = userEvent.setup()

      renderSubNav({ onLinkClick })

      await user.click(screen.getByRole('link', { name: 'Albums' }))

      expect(onLinkClick).toHaveBeenCalled()
    })
  })
})
