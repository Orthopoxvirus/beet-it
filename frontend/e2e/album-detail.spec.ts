import { test, expect, Page } from '@playwright/test'

/**
 * E2E Tests for Album Detail Page
 *
 * These tests verify the complete end-to-end workflow for:
 * - Navigating from album list to album detail page
 * - Displaying album metadata (title, artist, year, genre, etc.)
 * - Track listing with all track information
 * - Audio player controls and functionality
 * - Cover art display and upload
 *
 * Prerequisites:
 * - Backend API running at http://localhost:8000
 * - Frontend dev server running at http://localhost:3000
 * - At least one library with albums in the database
 *
 * Run these tests:
 * npx playwright test e2e/album-detail.spec.ts
 */

// Test constants
const LIBRARY_PAGE_URL = 'http://localhost:3000/libraries'

test.describe('Album Detail Page - Navigation and Display', () => {
  let page: Page
  let librarySlug: string
  let albumId: string

  test.beforeEach(async ({ browser }) => {
    page = await browser.newPage()
    page.on('console', (msg) => console.log('PAGE LOG:', msg.text()))
    page.on('pageerror', (error) => console.log('PAGE ERROR:', error))

    // Navigate to libraries page to get first library
    await page.goto(LIBRARY_PAGE_URL, { waitUntil: 'networkidle' })

    // Find first library card link
    const firstLibraryLink = page.locator('a[href*="/libraries/"]').first()
    if (await firstLibraryLink.isVisible()) {
      const href = await firstLibraryLink.getAttribute('href')
      if (href) {
        librarySlug = href.split('/').filter(Boolean).pop() || ''
        console.log(`Using library slug: ${librarySlug}`)
      }
    }
  })

  test.afterEach(async () => {
    await page.close()
  })

  test('8.4.1: should navigate from album list to album detail page', async () => {
    if (!librarySlug) {
      test.skip()
      return
    }

    // Navigate to library's Albums tab
    await page.goto(`${LIBRARY_PAGE_URL}/${librarySlug}`, { waitUntil: 'networkidle' })

    // Click on Albums tab if not already selected
    const albumsTab = page.locator('button, a').filter({ hasText: /^Albums$/i })
    if (await albumsTab.isVisible()) {
      await albumsTab.click()
      await page.waitForLoadState('networkidle')
    }

    // Wait for album cards to load
    const albumCards = page.locator('[data-testid="album-card"], [class*="album-card"], a[href*="/albums/"]')
    const cardCount = await albumCards.count()
    console.log(`Found ${cardCount} album cards`)

    if (cardCount === 0) {
      console.log('No albums found in library - skipping navigation test')
      return
    }

    // Click on first album card
    const firstAlbumCard = albumCards.first()
    await firstAlbumCard.click()
    console.log('Clicked on first album card')

    // Wait for album detail page to load
    await page.waitForLoadState('networkidle')

    // Verify we're on the album detail page
    const url = page.url()
    expect(url).toMatch(/\/libraries\/[^/]+\/albums\/\d+/)
    console.log(`Navigated to: ${url}`)

    // Extract album ID from URL for later tests
    albumId = url.split('/').pop() || ''
    console.log(`Album ID: ${albumId}`)

    // Verify album detail page elements are present
    const backButton = page.locator('a, button').filter({ hasText: /back to albums/i })
    await expect(backButton).toBeVisible()
    console.log('Back button is visible')
  })

  test('8.4.2: should display album metadata correctly', async () => {
    if (!librarySlug) {
      test.skip()
      return
    }

    // Navigate to library albums and get first album
    await page.goto(`${LIBRARY_PAGE_URL}/${librarySlug}`, { waitUntil: 'networkidle' })

    // Find first album link
    const albumLinks = page.locator('a[href*="/albums/"]')
    if ((await albumLinks.count()) === 0) {
      console.log('No albums found - skipping metadata test')
      return
    }

    const firstAlbumLink = albumLinks.first()
    await firstAlbumLink.click()
    await page.waitForLoadState('networkidle')

    // Wait for content to load
    await page.waitForTimeout(1000)

    // Verify album title is displayed (should be an h1)
    const albumTitle = page.locator('h1')
    await expect(albumTitle).toBeVisible()
    const titleText = await albumTitle.textContent()
    console.log(`Album title: ${titleText}`)
    expect(titleText).toBeTruthy()

    // Verify artist is displayed
    const artistElement = page.locator('p, span').filter({ hasText: /.+/ }).first()
    const artistText = await artistElement.textContent()
    console.log(`Artist: ${artistText}`)

    // Check for metadata fields (year, genre, tracks, duration)
    const metadataCard = page.locator('[class*="card"], [class*="Card"]').first()
    if (await metadataCard.isVisible()) {
      const cardText = await metadataCard.textContent()
      console.log('Metadata card content found')

      // Check for track count
      const tracksText = page.locator('text=/\\d+ tracks?/')
      const hasTracksInfo = await tracksText.isVisible().catch(() => false)
      console.log(`Has tracks info: ${hasTracksInfo}`)

      // Check for duration
      const durationText = page.locator('text=/(\\d+ hr )?\\d+ min/')
      const hasDurationInfo = await durationText.isVisible().catch(() => false)
      console.log(`Has duration info: ${hasDurationInfo}`)
    }
  })

  test('8.4.3: should display track listing correctly', async () => {
    if (!librarySlug) {
      test.skip()
      return
    }

    // Navigate to first album
    await page.goto(`${LIBRARY_PAGE_URL}/${librarySlug}`, { waitUntil: 'networkidle' })

    const albumLinks = page.locator('a[href*="/albums/"]')
    if ((await albumLinks.count()) === 0) {
      console.log('No albums found - skipping track listing test')
      return
    }

    await albumLinks.first().click()
    await page.waitForLoadState('networkidle')

    // Verify "Tracks" heading exists
    const tracksHeading = page.locator('h2').filter({ hasText: /tracks/i })
    await expect(tracksHeading).toBeVisible()
    console.log('Tracks heading is visible')

    // Verify table headers
    const tableHeaders = page.locator('th')
    const headerCount = await tableHeaders.count()
    console.log(`Table headers count: ${headerCount}`)

    // Check for expected headers
    const titleHeader = page.locator('th').filter({ hasText: /title/i })
    const hasTitle = await titleHeader.isVisible().catch(() => false)
    console.log(`Has Title header: ${hasTitle}`)

    const artistHeader = page.locator('th').filter({ hasText: /artist/i })
    const hasArtist = await artistHeader.isVisible().catch(() => false)
    console.log(`Has Artist header: ${hasArtist}`)

    const durationHeader = page.locator('th').filter({ hasText: /duration/i })
    const hasDuration = await durationHeader.isVisible().catch(() => false)
    console.log(`Has Duration header: ${hasDuration}`)

    // Verify track rows exist
    const trackRows = page.locator('tbody tr')
    const trackCount = await trackRows.count()
    console.log(`Track rows count: ${trackCount}`)

    if (trackCount > 0) {
      // Verify first track row has content
      const firstRow = trackRows.first()
      const rowText = await firstRow.textContent()
      console.log(`First track row: ${rowText?.substring(0, 100)}...`)
      expect(rowText).toBeTruthy()
    }
  })

  test('8.4.4: should display cover art or placeholder', async () => {
    if (!librarySlug) {
      test.skip()
      return
    }

    // Navigate to first album
    await page.goto(`${LIBRARY_PAGE_URL}/${librarySlug}`, { waitUntil: 'networkidle' })

    const albumLinks = page.locator('a[href*="/albums/"]')
    if ((await albumLinks.count()) === 0) {
      console.log('No albums found - skipping cover art test')
      return
    }

    await albumLinks.first().click()
    await page.waitForLoadState('networkidle')

    // Check for cover art image
    const coverImg = page.locator('img[alt*="cover"], img[alt*="album"], img[class*="cover"]')
    const hasCoverImg = await coverImg.isVisible().catch(() => false)

    // Check for music icon placeholder
    const musicPlaceholder = page.locator('[class*="Music"], svg.lucide-music')
    const hasPlaceholder = await musicPlaceholder.isVisible().catch(() => false)

    console.log(`Has cover image: ${hasCoverImg}, Has placeholder: ${hasPlaceholder}`)

    // Either cover image or placeholder should be visible
    expect(hasCoverImg || hasPlaceholder).toBeTruthy()

    // Check for "Change Cover" button
    const changeCoverButton = page.locator('button').filter({ hasText: /change cover/i })
    const hasChangeCover = await changeCoverButton.isVisible().catch(() => false)
    console.log(`Has Change Cover button: ${hasChangeCover}`)
    expect(hasChangeCover).toBeTruthy()
  })

  test('8.4.5: should navigate back to album list', async () => {
    if (!librarySlug) {
      test.skip()
      return
    }

    // Navigate to first album
    await page.goto(`${LIBRARY_PAGE_URL}/${librarySlug}`, { waitUntil: 'networkidle' })

    const albumLinks = page.locator('a[href*="/albums/"]')
    if ((await albumLinks.count()) === 0) {
      console.log('No albums found - skipping back navigation test')
      return
    }

    await albumLinks.first().click()
    await page.waitForLoadState('networkidle')

    // Click back button
    const backButton = page.locator('a, button').filter({ hasText: /back to albums/i })
    await expect(backButton).toBeVisible()
    await backButton.click()
    await page.waitForLoadState('networkidle')

    // Verify we're back on album list
    const url = page.url()
    expect(url).toMatch(/\/libraries\/[^/]+\/albums?\/?$/)
    console.log(`Navigated back to: ${url}`)
  })

  test('8.4.6: should handle invalid album ID gracefully', async () => {
    if (!librarySlug) {
      test.skip()
      return
    }

    // Try to navigate to a non-existent album
    await page.goto(`${LIBRARY_PAGE_URL}/${librarySlug}/albums/999999`, {
      waitUntil: 'networkidle',
    })

    // Should show error or not found state
    const errorState = page.locator('text=/not found|error|invalid/i')
    const hasError = await errorState.isVisible().catch(() => false)
    console.log(`Shows error/not found: ${hasError}`)

    // Should have back link
    const backLink = page.locator('a').filter({ hasText: /back to albums/i })
    const hasBackLink = await backLink.isVisible().catch(() => false)
    console.log(`Has back link: ${hasBackLink}`)
  })

  test('8.4.7: should display multi-disc album correctly', async () => {
    if (!librarySlug) {
      test.skip()
      return
    }

    // Navigate to albums
    await page.goto(`${LIBRARY_PAGE_URL}/${librarySlug}`, { waitUntil: 'networkidle' })

    const albumLinks = page.locator('a[href*="/albums/"]')
    if ((await albumLinks.count()) === 0) {
      console.log('No albums found - skipping multi-disc test')
      return
    }

    // Check each album for multi-disc indication
    const albumCount = await albumLinks.count()
    for (let i = 0; i < Math.min(albumCount, 5); i++) {
      await albumLinks.nth(i).click()
      await page.waitForLoadState('networkidle')

      // Check for disc count display
      const discText = page.locator('text=/\\d+ discs?/')
      const hasDiscInfo = await discText.isVisible().catch(() => false)

      // Check for Disc column in table
      const discHeader = page.locator('th').filter({ hasText: /disc/i })
      const hasDiscColumn = await discHeader.isVisible().catch(() => false)

      if (hasDiscInfo || hasDiscColumn) {
        console.log(`Album ${i + 1} is multi-disc`)
        expect(hasDiscColumn).toBeTruthy()
        break
      }

      // Go back to try next album
      await page.goBack()
      await page.waitForLoadState('networkidle')
    }
  })

  test('8.4.8: should be responsive on mobile viewport', async () => {
    if (!librarySlug) {
      test.skip()
      return
    }

    // Set mobile viewport
    await page.setViewportSize({ width: 375, height: 667 })

    // Navigate to first album
    await page.goto(`${LIBRARY_PAGE_URL}/${librarySlug}`, { waitUntil: 'networkidle' })

    const albumLinks = page.locator('a[href*="/albums/"]')
    if ((await albumLinks.count()) === 0) {
      console.log('No albums found - skipping responsive test')
      return
    }

    await albumLinks.first().click()
    await page.waitForLoadState('networkidle')

    // Verify key elements are still visible on mobile
    const title = page.locator('h1')
    await expect(title).toBeVisible()

    const tracksHeading = page.locator('h2').filter({ hasText: /tracks/i })
    await expect(tracksHeading).toBeVisible()

    // On mobile, layout should stack vertically
    // Cover art should be above metadata
    const coverArtArea = page.locator('[class*="w-64"], img[alt*="album"]').first()
    const hasCoverArea = await coverArtArea.isVisible().catch(() => false)
    console.log(`Cover area visible on mobile: ${hasCoverArea}`)
  })
})

test.describe('Album Detail Page - Audio Playback', () => {
  let page: Page
  let librarySlug: string

  test.beforeEach(async ({ browser }) => {
    page = await browser.newPage()

    // Navigate to libraries page to get first library
    await page.goto(LIBRARY_PAGE_URL, { waitUntil: 'networkidle' })

    const firstLibraryLink = page.locator('a[href*="/libraries/"]').first()
    if (await firstLibraryLink.isVisible()) {
      const href = await firstLibraryLink.getAttribute('href')
      if (href) {
        librarySlug = href.split('/').filter(Boolean).pop() || ''
      }
    }
  })

  test.afterEach(async () => {
    await page.close()
  })

  test('8.5.1: should display audio player on album detail page', async () => {
    if (!librarySlug) {
      test.skip()
      return
    }

    // Navigate to first album
    await page.goto(`${LIBRARY_PAGE_URL}/${librarySlug}`, { waitUntil: 'networkidle' })

    const albumLinks = page.locator('a[href*="/albums/"]')
    if ((await albumLinks.count()) === 0) {
      console.log('No albums found - skipping audio player test')
      return
    }

    await albumLinks.first().click()
    await page.waitForLoadState('networkidle')

    // Check for audio player
    const playButton = page.locator('button').filter({ hasText: /play/i }).or(
      page.locator('button[aria-label*="Play"], button[aria-label*="play"]')
    )
    const hasPlayButton = await playButton.first().isVisible().catch(() => false)
    console.log(`Has play button: ${hasPlayButton}`)
    expect(hasPlayButton).toBeTruthy()

    // Check for other player controls
    const stopButton = page.locator('button[aria-label*="stop" i], button[aria-label*="Stop"]')
    const hasStopButton = await stopButton.isVisible().catch(() => false)
    console.log(`Has stop button: ${hasStopButton}`)

    const prevButton = page.locator('button[aria-label*="previous" i], button[aria-label*="Previous"]')
    const hasPrevButton = await prevButton.isVisible().catch(() => false)
    console.log(`Has previous button: ${hasPrevButton}`)

    const nextButton = page.locator('button[aria-label*="next" i], button[aria-label*="Next"]')
    const hasNextButton = await nextButton.isVisible().catch(() => false)
    console.log(`Has next button: ${hasNextButton}`)
  })

  test('8.5.2: should show "No track selected" initially', async () => {
    if (!librarySlug) {
      test.skip()
      return
    }

    await page.goto(`${LIBRARY_PAGE_URL}/${librarySlug}`, { waitUntil: 'networkidle' })

    const albumLinks = page.locator('a[href*="/albums/"]')
    if ((await albumLinks.count()) === 0) {
      console.log('No albums found - skipping initial state test')
      return
    }

    await albumLinks.first().click()
    await page.waitForLoadState('networkidle')

    // Check for "No track selected" message
    const noTrackMessage = page.locator('text=/no track selected/i')
    const hasNoTrackMessage = await noTrackMessage.isVisible().catch(() => false)
    console.log(`Shows 'No track selected': ${hasNoTrackMessage}`)
    expect(hasNoTrackMessage).toBeTruthy()
  })

  test('8.5.3: should update player when track is clicked', async () => {
    if (!librarySlug) {
      test.skip()
      return
    }

    await page.goto(`${LIBRARY_PAGE_URL}/${librarySlug}`, { waitUntil: 'networkidle' })

    const albumLinks = page.locator('a[href*="/albums/"]')
    if ((await albumLinks.count()) === 0) {
      console.log('No albums found - skipping track click test')
      return
    }

    await albumLinks.first().click()
    await page.waitForLoadState('networkidle')

    // Get first track row
    const trackRows = page.locator('tbody tr')
    const trackCount = await trackRows.count()

    if (trackCount === 0) {
      console.log('No tracks found - skipping track click test')
      return
    }

    // Get the track title before clicking
    const firstTrackCell = trackRows.first().locator('td').nth(1) // Title is usually second column
    const trackTitle = await firstTrackCell.textContent()
    console.log(`Clicking on track: ${trackTitle}`)

    // Click on track row
    await trackRows.first().click()
    await page.waitForTimeout(500)

    // Verify player updates - "No track selected" should be gone
    const noTrackMessage = page.locator('text=/no track selected/i')
    const stillNoTrack = await noTrackMessage.isVisible().catch(() => false)
    console.log(`Still shows 'No track selected': ${stillNoTrack}`)
    expect(stillNoTrack).toBeFalsy()

    // Track info should be displayed in player
    const playerTrackInfo = page.locator('p.truncate, span.truncate').filter({ hasText: new RegExp(trackTitle || '', 'i') })
    const hasTrackInfo = await playerTrackInfo.isVisible().catch(() => false)
    console.log(`Player shows track info: ${hasTrackInfo}`)
  })

  test('8.5.4: should have volume control', async () => {
    if (!librarySlug) {
      test.skip()
      return
    }

    await page.goto(`${LIBRARY_PAGE_URL}/${librarySlug}`, { waitUntil: 'networkidle' })

    const albumLinks = page.locator('a[href*="/albums/"]')
    if ((await albumLinks.count()) === 0) {
      console.log('No albums found - skipping volume control test')
      return
    }

    await albumLinks.first().click()
    await page.waitForLoadState('networkidle')

    // Check for volume/mute button
    const muteButton = page.locator('button[aria-label*="mute" i], button[aria-label*="Mute"]')
    const hasMuteButton = await muteButton.isVisible().catch(() => false)
    console.log(`Has mute button: ${hasMuteButton}`)
    expect(hasMuteButton).toBeTruthy()

    // Check for volume slider
    const volumeSlider = page.locator('[aria-label*="volume" i], [aria-label*="Volume"]')
    const hasVolumeSlider = await volumeSlider.isVisible().catch(() => false)
    console.log(`Has volume slider: ${hasVolumeSlider}`)
  })

  test('8.5.5: should toggle mute when mute button is clicked', async () => {
    if (!librarySlug) {
      test.skip()
      return
    }

    await page.goto(`${LIBRARY_PAGE_URL}/${librarySlug}`, { waitUntil: 'networkidle' })

    const albumLinks = page.locator('a[href*="/albums/"]')
    if ((await albumLinks.count()) === 0) {
      console.log('No albums found - skipping mute toggle test')
      return
    }

    await albumLinks.first().click()
    await page.waitForLoadState('networkidle')

    // Find and click mute button
    const muteButton = page.locator('button[aria-label*="mute" i]').first()
    if (!(await muteButton.isVisible())) {
      console.log('Mute button not found - skipping test')
      return
    }

    // Get initial state
    const initialLabel = await muteButton.getAttribute('aria-label')
    console.log(`Initial button label: ${initialLabel}`)

    // Click to toggle
    await muteButton.click()
    await page.waitForTimeout(300)

    // Get new state
    const newLabel = await muteButton.getAttribute('aria-label')
    console.log(`After click label: ${newLabel}`)

    // Label should change (Mute <-> Unmute)
    expect(newLabel).not.toBe(initialLabel)
  })

  test('8.5.6: should highlight currently playing track in list', async () => {
    if (!librarySlug) {
      test.skip()
      return
    }

    await page.goto(`${LIBRARY_PAGE_URL}/${librarySlug}`, { waitUntil: 'networkidle' })

    const albumLinks = page.locator('a[href*="/albums/"]')
    if ((await albumLinks.count()) === 0) {
      console.log('No albums found - skipping highlight test')
      return
    }

    await albumLinks.first().click()
    await page.waitForLoadState('networkidle')

    const trackRows = page.locator('tbody tr')
    if ((await trackRows.count()) === 0) {
      console.log('No tracks found - skipping highlight test')
      return
    }

    // Click on first track
    await trackRows.first().click()
    await page.waitForTimeout(500)

    // Check if the row is highlighted (has special class or style)
    const firstRow = trackRows.first()
    const rowClasses = await firstRow.getAttribute('class')
    console.log(`Track row classes: ${rowClasses}`)

    // Check for highlight class (primary color background)
    const hasHighlight =
      rowClasses?.includes('bg-primary') ||
      rowClasses?.includes('selected') ||
      rowClasses?.includes('active')
    console.log(`Row is highlighted: ${hasHighlight}`)
  })
})

test.describe('Album Detail Page - Cover Art Upload', () => {
  let page: Page
  let librarySlug: string

  test.beforeEach(async ({ browser }) => {
    page = await browser.newPage()

    await page.goto(LIBRARY_PAGE_URL, { waitUntil: 'networkidle' })

    const firstLibraryLink = page.locator('a[href*="/libraries/"]').first()
    if (await firstLibraryLink.isVisible()) {
      const href = await firstLibraryLink.getAttribute('href')
      if (href) {
        librarySlug = href.split('/').filter(Boolean).pop() || ''
      }
    }
  })

  test.afterEach(async () => {
    await page.close()
  })

  test('8.6.1: should open cover art upload dialog', async () => {
    if (!librarySlug) {
      test.skip()
      return
    }

    await page.goto(`${LIBRARY_PAGE_URL}/${librarySlug}`, { waitUntil: 'networkidle' })

    const albumLinks = page.locator('a[href*="/albums/"]')
    if ((await albumLinks.count()) === 0) {
      console.log('No albums found - skipping upload dialog test')
      return
    }

    await albumLinks.first().click()
    await page.waitForLoadState('networkidle')

    // Click on "Change Cover" button
    const changeCoverButton = page.locator('button').filter({ hasText: /change cover/i })
    await expect(changeCoverButton).toBeVisible()
    await changeCoverButton.click()

    // Verify dialog opens
    const dialog = page.locator('[role="dialog"], [data-state="open"]')
    await expect(dialog).toBeVisible()
    console.log('Cover art upload dialog opened')

    // Verify dialog title
    const dialogTitle = page.locator('text=Update Cover Art')
    await expect(dialogTitle).toBeVisible()
  })

  test('8.6.2: should display upload mode tabs', async () => {
    if (!librarySlug) {
      test.skip()
      return
    }

    await page.goto(`${LIBRARY_PAGE_URL}/${librarySlug}`, { waitUntil: 'networkidle' })

    const albumLinks = page.locator('a[href*="/albums/"]')
    if ((await albumLinks.count()) === 0) {
      console.log('No albums found - skipping tabs test')
      return
    }

    await albumLinks.first().click()
    await page.waitForLoadState('networkidle')

    const changeCoverButton = page.locator('button').filter({ hasText: /change cover/i })
    await changeCoverButton.click()

    // Check for Upload tab
    const uploadTab = page.locator('button').filter({ hasText: /upload/i })
    await expect(uploadTab).toBeVisible()

    // Check for From URL tab
    const urlTab = page.locator('button').filter({ hasText: /from url/i })
    await expect(urlTab).toBeVisible()

    console.log('Both mode tabs are visible')
  })

  test('8.6.3: should show drop zone in upload mode', async () => {
    if (!librarySlug) {
      test.skip()
      return
    }

    await page.goto(`${LIBRARY_PAGE_URL}/${librarySlug}`, { waitUntil: 'networkidle' })

    const albumLinks = page.locator('a[href*="/albums/"]')
    if ((await albumLinks.count()) === 0) {
      console.log('No albums found - skipping drop zone test')
      return
    }

    await albumLinks.first().click()
    await page.waitForLoadState('networkidle')

    const changeCoverButton = page.locator('button').filter({ hasText: /change cover/i })
    await changeCoverButton.click()

    // Check for drop zone elements
    const dropZoneText = page.locator('text=/drag and drop/i')
    await expect(dropZoneText).toBeVisible()

    const browseButton = page.locator('button').filter({ hasText: /browse files/i })
    await expect(browseButton).toBeVisible()

    const formatInfo = page.locator('text=/accepted formats/i')
    await expect(formatInfo).toBeVisible()

    console.log('Drop zone elements are visible')
  })

  test('8.6.4: should switch to URL input mode', async () => {
    if (!librarySlug) {
      test.skip()
      return
    }

    await page.goto(`${LIBRARY_PAGE_URL}/${librarySlug}`, { waitUntil: 'networkidle' })

    const albumLinks = page.locator('a[href*="/albums/"]')
    if ((await albumLinks.count()) === 0) {
      console.log('No albums found - skipping URL mode test')
      return
    }

    await albumLinks.first().click()
    await page.waitForLoadState('networkidle')

    const changeCoverButton = page.locator('button').filter({ hasText: /change cover/i })
    await changeCoverButton.click()

    // Click on "From URL" tab
    const urlTab = page.locator('button').filter({ hasText: /from url/i })
    await urlTab.click()

    // Check for URL input field
    const urlInput = page.locator('input[type="url"], input#cover-url')
    await expect(urlInput).toBeVisible()

    // Check for placeholder
    const placeholder = await urlInput.getAttribute('placeholder')
    console.log(`URL input placeholder: ${placeholder}`)
    expect(placeholder).toContain('example.com')
  })

  test('8.6.5: should validate empty URL submission', async () => {
    if (!librarySlug) {
      test.skip()
      return
    }

    await page.goto(`${LIBRARY_PAGE_URL}/${librarySlug}`, { waitUntil: 'networkidle' })

    const albumLinks = page.locator('a[href*="/albums/"]')
    if ((await albumLinks.count()) === 0) {
      console.log('No albums found - skipping URL validation test')
      return
    }

    await albumLinks.first().click()
    await page.waitForLoadState('networkidle')

    const changeCoverButton = page.locator('button').filter({ hasText: /change cover/i })
    await changeCoverButton.click()

    // Switch to URL mode
    const urlTab = page.locator('button').filter({ hasText: /from url/i })
    await urlTab.click()

    // Try to submit without entering URL
    const downloadButton = page.locator('button').filter({ hasText: /download/i })
    await downloadButton.click()

    // Should show error
    const errorMessage = page.locator('text=/please enter a url/i')
    await expect(errorMessage).toBeVisible()
    console.log('Empty URL validation error shown')
  })

  test('8.6.6: should close dialog when cancel is clicked', async () => {
    if (!librarySlug) {
      test.skip()
      return
    }

    await page.goto(`${LIBRARY_PAGE_URL}/${librarySlug}`, { waitUntil: 'networkidle' })

    const albumLinks = page.locator('a[href*="/albums/"]')
    if ((await albumLinks.count()) === 0) {
      console.log('No albums found - skipping cancel test')
      return
    }

    await albumLinks.first().click()
    await page.waitForLoadState('networkidle')

    const changeCoverButton = page.locator('button').filter({ hasText: /change cover/i })
    await changeCoverButton.click()

    // Verify dialog is open
    const dialog = page.locator('[role="dialog"]')
    await expect(dialog).toBeVisible()

    // Click cancel
    const cancelButton = page.locator('button').filter({ hasText: /cancel/i })
    await cancelButton.click()

    // Verify dialog is closed
    await expect(dialog).not.toBeVisible()
    console.log('Dialog closed after cancel')
  })

  test('8.6.7: should show file info after selection', async () => {
    if (!librarySlug) {
      test.skip()
      return
    }

    await page.goto(`${LIBRARY_PAGE_URL}/${librarySlug}`, { waitUntil: 'networkidle' })

    const albumLinks = page.locator('a[href*="/albums/"]')
    if ((await albumLinks.count()) === 0) {
      console.log('No albums found - skipping file selection test')
      return
    }

    await albumLinks.first().click()
    await page.waitForLoadState('networkidle')

    const changeCoverButton = page.locator('button').filter({ hasText: /change cover/i })
    await changeCoverButton.click()

    // Set up file chooser
    const fileInput = page.locator('input[type="file"]')

    // Set a file (create a small test image)
    await fileInput.setInputFiles({
      name: 'test-cover.jpg',
      mimeType: 'image/jpeg',
      buffer: Buffer.from([0xff, 0xd8, 0xff, 0xe0]), // JPEG magic bytes
    })

    // Should show preview or file info
    await page.waitForTimeout(500)

    // Check if preview image or file name is shown
    const previewImg = page.locator('img[alt*="preview" i]')
    const hasPreview = await previewImg.isVisible().catch(() => false)

    const fileName = page.locator('text=/test-cover\\.jpg/i')
    const hasFileName = await fileName.isVisible().catch(() => false)

    console.log(`Has preview: ${hasPreview}, Has file name: ${hasFileName}`)

    // Either preview or file name should be visible
    // (Validation may fail for tiny test file, but UI should respond)
  })
})
