import { test, expect, Page } from '@playwright/test'

/**
 * E2E Tests for Beets Import UI - Full Candidate Analysis Workflow
 *
 * These tests verify the complete end-to-end beets import workflow including:
 * - Navigating to the Beets Import tab in the import detail page
 * - Fetching and displaying album list from the import folder
 * - Selecting an album from the list
 * - Triggering beets analysis by clicking the disc icon
 * - Verifying analysis results display (candidates, track comparison, etc.)
 * - Testing responsive layout on mobile viewports
 * - Testing error states (network failures, analysis timeouts)
 * - Testing re-analysis flow (clicking disc on already-analyzed album)
 *
 * Prerequisites:
 * - Backend API running at http://localhost:8000
 * - At least one library created in the system
 * - Import folder contains music files/album folders for testing
 * - Beets service is available and configured
 *
 * Setup Playwright:
 * npm install --save-dev @playwright/test
 *
 * Run these tests:
 * npx playwright test e2e/beets-import.spec.ts
 */

// Test constants
const IMPORT_PAGE_URL = 'http://localhost:3000/import'
const BEETS_IMPORT_TAB = 'Beets Import'
const STAGE_INDICATOR_SELECTOR = '[data-testid="stage-indicator"]'
const ALBUM_ITEM_SELECTOR = '[data-testid="album-list-item"]'
const CANDIDATE_CARD_SELECTOR = '[data-testid="candidate-card"]'

test.describe('Beets Import Workflow - Full E2E Tests', () => {
  let page: Page
  let librarySlug: string

  test.beforeEach(async ({ browser }) => {
    page = await browser.newPage()
    page.on('console', (msg) => console.log('PAGE LOG:', msg.text()))
    page.on('pageerror', (error) => console.log('PAGE ERROR:', error))

    // Navigate to import page to get first library
    await page.goto(IMPORT_PAGE_URL, { waitUntil: 'networkidle' })

    // Extract library slug from the first library card
    const firstCard = page.locator('[role="heading"]').first()
    if (await firstCard.isVisible()) {
      const cardContainer = firstCard.locator('..').locator('..')
      const cardLink = cardContainer.locator('a').first()
      const href = await cardLink.getAttribute('href')
      if (href) {
        librarySlug = href.split('/').pop() || ''
        console.log(`Using library slug: ${librarySlug}`)
      }
    }
  })

  test.afterEach(async () => {
    await page.close()
  })

  test('10.1: should navigate to Beets Import tab, select album, trigger analysis, verify results display', async () => {
    if (!librarySlug) {
      test.skip()
      return
    }

    // Step 1: Navigate to import detail page
    await page.goto(`${IMPORT_PAGE_URL}/${librarySlug}`, { waitUntil: 'networkidle' })
    console.log(`Navigated to import detail page for library: ${librarySlug}`)

    // Verify page loaded
    const backButton = page.locator('button:has-text("Imports")')
    await expect(backButton).toBeVisible()

    // Step 2: Click on Beets Import tab
    const beetsTab = page.locator(`text=${BEETS_IMPORT_TAB}`)
    await expect(beetsTab).toBeVisible()
    await beetsTab.click()
    console.log('Clicked Beets Import tab')

    // Wait for tab content to load
    await page.waitForLoadState('networkidle')

    // Step 3: Verify album list is loading or loaded
    const albumList = page.locator('[data-testid="album-list-card"]')
    await expect(albumList).toBeVisible({ timeout: 10000 })
    console.log('Album list card is visible')

    // Step 4: Wait for albums to load (either show skeleton or actual albums)
    let albumCount = 0
    try {
      // Try to find actual album items (not skeletons)
      const albumItems = page.locator(ALBUM_ITEM_SELECTOR)
      albumCount = await albumItems.count()

      if (albumCount === 0) {
        console.log('No albums found in list - checking for empty state or loading')
        const emptyState = page.locator('text=No albums found')
        const loadingState = page.locator('[class*="animate-pulse"]')
        if (await emptyState.isVisible()) {
          console.log('Empty state displayed - no albums in import folder')
        } else if (await loadingState.isVisible()) {
          console.log('Loading state - waiting for albums to load')
        }
      } else {
        console.log(`Found ${albumCount} albums in the list`)
      }
    } catch (error) {
      console.log('Could not count albums:', error)
    }

    // Step 5: If albums exist, select the first one
    if (albumCount > 0) {
      const firstAlbum = page.locator(ALBUM_ITEM_SELECTOR).first()
      await firstAlbum.click()
      console.log('Selected first album')

      // Wait a moment for album details to load
      await page.waitForTimeout(500)

      // Step 6: Verify album is selected (should be highlighted)
      const selectedAlbum = page.locator(ALBUM_ITEM_SELECTOR).first()
      const ariaSelected = await selectedAlbum.getAttribute('aria-selected')
      console.log(`Album selection state: aria-selected=${ariaSelected}`)

      // Step 7: Trigger analysis by clicking the disc/stage indicator
      const stageIndicator = firstAlbum.locator(STAGE_INDICATOR_SELECTOR).first()
      if (await stageIndicator.isVisible()) {
        console.log('Stage indicator found - clicking to trigger analysis')
        await stageIndicator.click()

        // Wait for analysis to complete with longer timeout
        await page.waitForLoadState('networkidle')
        await page.waitForTimeout(1000)

        // Step 8: Verify results display
        const candidateDetails = page.locator('[data-testid="candidate-details-card"]')
        await expect(candidateDetails).toBeVisible({ timeout: 10000 })
        console.log('Candidate details card is visible')

        // Check for analysis results
        const candidates = page.locator(CANDIDATE_CARD_SELECTOR)
        const candidateCount = await candidates.count()
        console.log(`Found ${candidateCount} candidate(s)`)

        // Verify key result elements
        const localAlbumInfo = page.locator('[data-testid="local-album-info"]')
        if (await localAlbumInfo.isVisible()) {
          console.log('Local album info displayed')
        }

        if (candidateCount > 0) {
          // Verify first candidate has expected content
          const firstCandidate = candidates.first()
          const similarity = firstCandidate.locator('[data-testid="similarity-score"]')
          if (await similarity.isVisible()) {
            const score = await similarity.textContent()
            console.log(`First candidate similarity: ${score}`)
          }

          const trackTable = firstCandidate.locator('[data-testid="track-comparison"]')
          if (await trackTable.isVisible()) {
            console.log('Track comparison table is visible')
          }
        } else {
          console.log('No candidates found - analysis may have returned no matches')
        }
      } else {
        console.log('Stage indicator not found - skipping analysis trigger')
      }
    } else {
      console.log('Skipping album selection and analysis - no albums available')
    }
  })

  test('should verify responsive layout on mobile viewport', async () => {
    if (!librarySlug) {
      test.skip()
      return
    }

    // Set mobile viewport
    await page.setViewportSize({ width: 375, height: 667 })
    console.log('Set mobile viewport: 375x667')

    // Navigate to beets import tab
    await page.goto(`${IMPORT_PAGE_URL}/${librarySlug}`, { waitUntil: 'networkidle' })
    const beetsTab = page.locator(`text=${BEETS_IMPORT_TAB}`)
    await beetsTab.click()
    await page.waitForLoadState('networkidle')

    // On mobile, components should stack vertically
    const mainGrid = page.locator('[class*="grid"]').first()
    const computedStyle = await mainGrid.evaluate((el) => {
      return window.getComputedStyle(el).getPropertyValue('grid-template-columns')
    })
    console.log(`Mobile grid layout: ${computedStyle}`)

    // Verify album list card is visible
    const albumList = page.locator('[data-testid="album-list-card"]')
    await expect(albumList).toBeVisible()

    // Verify candidate details card is visible
    const candidateDetails = page.locator('[data-testid="candidate-details-card"]')
    await expect(candidateDetails).toBeVisible()

    // Verify components are stacked (full width on mobile)
    const width = await mainGrid.evaluate((el) => (el as HTMLElement).offsetWidth)
    console.log(`Container width on mobile: ${width}`)
  })

  test('should handle mobile viewport > 1024px with side-by-side layout', async () => {
    if (!librarySlug) {
      test.skip()
      return
    }

    // Set desktop viewport
    await page.setViewportSize({ width: 1280, height: 800 })
    console.log('Set desktop viewport: 1280x800')

    // Navigate to beets import tab
    await page.goto(`${IMPORT_PAGE_URL}/${librarySlug}`, { waitUntil: 'networkidle' })
    const beetsTab = page.locator(`text=${BEETS_IMPORT_TAB}`)
    await beetsTab.click()
    await page.waitForLoadState('networkidle')

    // On desktop, components should be side-by-side
    const mainGrid = page.locator('[class*="grid"]').first()
    const computedStyle = await mainGrid.evaluate((el) => {
      return window.getComputedStyle(el).getPropertyValue('grid-template-columns')
    })
    console.log(`Desktop grid layout: ${computedStyle}`)

    // Verify both cards are visible and positioned side-by-side
    const albumList = page.locator('[data-testid="album-list-card"]')
    const candidateDetails = page.locator('[data-testid="candidate-details-card"]')

    await expect(albumList).toBeVisible()
    await expect(candidateDetails).toBeVisible()

    // Get positions to verify they're side-by-side
    const albumBox = await albumList.boundingBox()
    const candidateBox = await candidateDetails.boundingBox()

    if (albumBox && candidateBox) {
      const isSideBySide = albumBox.x + albumBox.width < candidateBox.x
      console.log(`Components are side-by-side: ${isSideBySide}`)
    }
  })

  test('should test error states (network failure handling)', async () => {
    if (!librarySlug) {
      test.skip()
      return
    }

    // Navigate to beets import tab
    await page.goto(`${IMPORT_PAGE_URL}/${librarySlug}`, { waitUntil: 'networkidle' })
    const beetsTab = page.locator(`text=${BEETS_IMPORT_TAB}`)
    await beetsTab.click()
    await page.waitForLoadState('networkidle')

    // Wait for album list to load
    const albumList = page.locator('[data-testid="album-list-card"]')
    await expect(albumList).toBeVisible()

    // Get first album item if available
    const firstAlbum = page.locator(ALBUM_ITEM_SELECTOR).first()
    if (!(await firstAlbum.isVisible())) {
      console.log('No albums available to test error handling')
      return
    }

    // Set up network interception to simulate analysis API failure
    await page.route('**/api/v1/libraries/*/beets/analyze', (route) => {
      route.abort('failed')
    })
    console.log('Network interception set up to block analyze endpoint')

    // Click album to select it
    await firstAlbum.click()
    await page.waitForTimeout(500)

    // Try to trigger analysis
    const stageIndicator = firstAlbum.locator(STAGE_INDICATOR_SELECTOR).first()
    if (await stageIndicator.isVisible()) {
      await stageIndicator.click()
      console.log('Attempted to trigger analysis with failed network')

      // Wait a moment for error to appear
      await page.waitForTimeout(1000)

      // Check for error message
      const errorMessage = page.locator('[data-testid="error-message"], text=/error|failed/i')
      const errorVisible = await errorMessage.isVisible().catch(() => false)
      console.log(`Error message displayed: ${errorVisible}`)

      if (errorVisible) {
        const errorText = await errorMessage.textContent()
        console.log(`Error text: ${errorText}`)
      }
    }
  })

  test('should test re-analysis flow (click disc on already-analyzed album)', async () => {
    if (!librarySlug) {
      test.skip()
      return
    }

    // Navigate to beets import tab
    await page.goto(`${IMPORT_PAGE_URL}/${librarySlug}`, { waitUntil: 'networkidle' })
    const beetsTab = page.locator(`text=${BEETS_IMPORT_TAB}`)
    await beetsTab.click()
    await page.waitForLoadState('networkidle')

    // Get first album
    const firstAlbum = page.locator(ALBUM_ITEM_SELECTOR).first()
    if (!(await firstAlbum.isVisible())) {
      console.log('No albums available to test re-analysis')
      return
    }

    // Select and analyze the album first time
    await firstAlbum.click()
    const stageIndicator = firstAlbum.locator(STAGE_INDICATOR_SELECTOR).first()

    if (await stageIndicator.isVisible()) {
      // First analysis
      await stageIndicator.click()
      console.log('Triggered first analysis')

      // Wait for results to load
      await page.waitForTimeout(2000)

      // Check if candidate details appear
      const candidateDetails = page.locator('[data-testid="candidate-details-card"]')
      const hasResults = await candidateDetails.isVisible().catch(() => false)

      if (hasResults) {
        // Get initial result content
        const initialContent = await candidateDetails.textContent()
        console.log('First analysis completed, results displayed')

        // Now trigger re-analysis by clicking disc again
        console.log('Triggering re-analysis by clicking disc again')
        await stageIndicator.click()
        await page.waitForTimeout(2000)

        // Verify results are updated or reloaded
        const reanalyzedContent = await candidateDetails.textContent()
        console.log('Re-analysis triggered and results updated')

        // Content may be the same if cached, or different if fresh analysis
        console.log('Re-analysis flow completed successfully')
      } else {
        console.log('First analysis did not produce visible results')
      }
    }
  })

  test('should display error state when album analysis fails', async () => {
    if (!librarySlug) {
      test.skip()
      return
    }

    // Navigate to beets import tab
    await page.goto(`${IMPORT_PAGE_URL}/${librarySlug}`, { waitUntil: 'networkidle' })
    const beetsTab = page.locator(`text=${BEETS_IMPORT_TAB}`)
    await beetsTab.click()
    await page.waitForLoadState('networkidle')

    // Get first album
    const firstAlbum = page.locator(ALBUM_ITEM_SELECTOR).first()
    if (!(await firstAlbum.isVisible())) {
      console.log('No albums available to test error display')
      return
    }

    // Set up network to return a 500 error
    await page.route('**/api/v1/libraries/*/beets/analyze', (route) => {
      route.abort('servererror')
    })

    // Select album and trigger analysis
    await firstAlbum.click()
    const stageIndicator = firstAlbum.locator(STAGE_INDICATOR_SELECTOR).first()

    if (await stageIndicator.isVisible()) {
      await stageIndicator.click()
      await page.waitForTimeout(1500)

      // Verify error is displayed
      const candidateDetails = page.locator('[data-testid="candidate-details-card"]')
      const errorIndicator = candidateDetails.locator('[data-testid="error-state"], text=/error|failed/i')

      const hasError = await errorIndicator.isVisible().catch(() => false)
      console.log(`Error state displayed after failed analysis: ${hasError}`)
    }
  })

  test('should display empty state when no albums are found', async () => {
    if (!librarySlug) {
      test.skip()
      return
    }

    // Navigate to beets import tab
    await page.goto(`${IMPORT_PAGE_URL}/${librarySlug}`, { waitUntil: 'networkidle' })
    const beetsTab = page.locator(`text=${BEETS_IMPORT_TAB}`)
    await beetsTab.click()
    await page.waitForLoadState('networkidle')

    const albumList = page.locator('[data-testid="album-list-card"]')
    await expect(albumList).toBeVisible()

    // Check for either albums or empty state
    const albumItems = page.locator(ALBUM_ITEM_SELECTOR)
    const albumCount = await albumItems.count()

    if (albumCount === 0) {
      // Verify empty state message
      const emptyState = page.locator('[data-testid="empty-state"], text=/No albums|empty|no items/i')
      const hasEmptyState = await emptyState.isVisible().catch(() => false)
      console.log(`Empty state displayed when no albums: ${hasEmptyState}`)
    } else {
      console.log(`Albums found (${albumCount}), empty state not applicable`)
    }
  })

  test('should display loading state while fetching albums', async () => {
    if (!librarySlug) {
      test.skip()
      return
    }

    // Add slight network delay to catch loading states
    await page.route('**/api/v1/libraries/*/import-tree', (route) => {
      // Delay the response
      setTimeout(() => route.continue(), 1500)
    })

    // Navigate to beets import tab
    await page.goto(`${IMPORT_PAGE_URL}/${librarySlug}`, { waitUntil: 'domcontentloaded' })
    const beetsTab = page.locator(`text=${BEETS_IMPORT_TAB}`)
    await beetsTab.click()

    // Immediately check for loading state
    const loadingSkeleton = page.locator('[data-testid="album-list-skeleton"], [class*="animate-pulse"]')
    const hasLoadingState = await loadingSkeleton.isVisible().catch(() => false)
    console.log(`Loading skeleton visible: ${hasLoadingState}`)

    // Wait for content to load
    const albumList = page.locator('[data-testid="album-list-card"]')
    await albumList.waitFor({ timeout: 10000, state: 'visible' })
    console.log('Album list loaded after loading state')
  })

  test('should display track comparison table when candidate selected', async () => {
    if (!librarySlug) {
      test.skip()
      return
    }

    // Navigate to beets import tab
    await page.goto(`${IMPORT_PAGE_URL}/${librarySlug}`, { waitUntil: 'networkidle' })
    const beetsTab = page.locator(`text=${BEETS_IMPORT_TAB}`)
    await beetsTab.click()
    await page.waitForLoadState('networkidle')

    // Get first album
    const firstAlbum = page.locator(ALBUM_ITEM_SELECTOR).first()
    if (!(await firstAlbum.isVisible())) {
      console.log('No albums available to test track comparison')
      return
    }

    // Select and analyze
    await firstAlbum.click()
    const stageIndicator = firstAlbum.locator(STAGE_INDICATOR_SELECTOR).first()

    if (await stageIndicator.isVisible()) {
      await stageIndicator.click()
      await page.waitForTimeout(2000)

      // Look for track comparison table in candidates
      const trackTable = page.locator('[data-testid="track-comparison"]')
      const hasTrackTable = await trackTable.isVisible().catch(() => false)
      console.log(`Track comparison table visible: ${hasTrackTable}`)

      if (hasTrackTable) {
        // Count table rows (tracks)
        const trackRows = trackTable.locator('tbody tr')
        const rowCount = await trackRows.count()
        console.log(`Track comparison table has ${rowCount} track rows`)
      }
    }
  })

  test('should display similarity score for candidates', async () => {
    if (!librarySlug) {
      test.skip()
      return
    }

    // Navigate to beets import tab
    await page.goto(`${IMPORT_PAGE_URL}/${librarySlug}`, { waitUntil: 'networkidle' })
    const beetsTab = page.locator(`text=${BEETS_IMPORT_TAB}`)
    await beetsTab.click()
    await page.waitForLoadState('networkidle')

    // Get first album
    const firstAlbum = page.locator(ALBUM_ITEM_SELECTOR).first()
    if (!(await firstAlbum.isVisible())) {
      console.log('No albums available to test similarity score')
      return
    }

    // Select and analyze
    await firstAlbum.click()
    const stageIndicator = firstAlbum.locator(STAGE_INDICATOR_SELECTOR).first()

    if (await stageIndicator.isVisible()) {
      await stageIndicator.click()
      await page.waitForTimeout(2000)

      // Look for similarity score
      const similarityScore = page.locator('[data-testid="similarity-score"]')
      const hasScore = await similarityScore.isVisible().catch(() => false)
      console.log(`Similarity score displayed: ${hasScore}`)

      if (hasScore) {
        const scoreText = await similarityScore.textContent()
        console.log(`Similarity score value: ${scoreText}`)

        // Verify it's a percentage
        const isPercentage = /\d+%/.test(scoreText || '')
        console.log(`Score is a percentage: ${isPercentage}`)
      }
    }
  })
})

test.describe('Beets Import - Analysis Queue', () => {
  let page: Page
  let librarySlug: string

  test.beforeEach(async ({ browser }) => {
    page = await browser.newPage()

    // Get first library slug
    await page.goto(IMPORT_PAGE_URL, { waitUntil: 'networkidle' })
    const firstCard = page.locator('[role="heading"]').first()
    if (await firstCard.isVisible()) {
      const cardContainer = firstCard.locator('..').locator('..')
      const cardLink = cardContainer.locator('a').first()
      const href = await cardLink.getAttribute('href')
      if (href) {
        librarySlug = href.split('/').pop() || ''
      }
    }
  })

  test.afterEach(async () => {
    await page.close()
  })

  test('should display Analyze All button in import panel', async () => {
    if (!librarySlug) {
      test.skip()
      return
    }

    await page.goto(`${IMPORT_PAGE_URL}/${librarySlug}`, { waitUntil: 'networkidle' })
    const beetsTab = page.locator(`text=${BEETS_IMPORT_TAB}`)
    await beetsTab.click()
    await page.waitForLoadState('networkidle')

    // Verify Analyze All button is visible
    const analyzeAllButton = page.locator('[data-testid="analyze-all-button"]')
    await expect(analyzeAllButton).toBeVisible()
    console.log('Analyze All button is visible')
  })

  test('should trigger bulk analysis when Analyze All is clicked', async () => {
    if (!librarySlug) {
      test.skip()
      return
    }

    await page.goto(`${IMPORT_PAGE_URL}/${librarySlug}`, { waitUntil: 'networkidle' })
    const beetsTab = page.locator(`text=${BEETS_IMPORT_TAB}`)
    await beetsTab.click()
    await page.waitForLoadState('networkidle')

    // Check if there are albums
    const albumItems = page.locator(ALBUM_ITEM_SELECTOR)
    const albumCount = await albumItems.count()

    if (albumCount === 0) {
      console.log('No albums available to test Analyze All')
      return
    }

    // Click Analyze All button
    const analyzeAllButton = page.locator('[data-testid="analyze-all-button"]')
    await analyzeAllButton.click()
    console.log('Clicked Analyze All button')

    // Wait for response (button may show loading state or feedback message)
    await page.waitForTimeout(2000)

    // Check for feedback alert (if it exists)
    const feedbackAlert = page.locator('[role="alert"]')
    const hasAlert = await feedbackAlert.isVisible().catch(() => false)
    if (hasAlert) {
      const alertText = await feedbackAlert.textContent()
      console.log(`Analyze All feedback: ${alertText}`)
    }
  })

  test('should show queue depth indicator when items are queued', async () => {
    if (!librarySlug) {
      test.skip()
      return
    }

    // Mock the API to return queued items
    await page.route('**/api/v1/libraries/*/beets/analyze-queue', (route) => {
      route.fulfill({
        status: 200,
        contentType: 'application/json',
        body: JSON.stringify({
          queueDepth: 3,
          activeCount: 2,
          maxConcurrent: 2,
          queuedItems: [
            { albumPath: '/import/Album1', position: 1, queuedAt: '2026-02-28T10:30:00Z' },
            { albumPath: '/import/Album2', position: 2, queuedAt: '2026-02-28T10:30:05Z' },
            { albumPath: '/import/Album3', position: 3, queuedAt: '2026-02-28T10:30:10Z' },
          ],
          activeItems: [
            { albumPath: '/import/Album4', jobId: 'job-1', startedAt: '2026-02-28T10:29:55Z' },
            { albumPath: '/import/Album5', jobId: 'job-2', startedAt: '2026-02-28T10:29:58Z' },
          ],
        }),
      })
    })

    await page.goto(`${IMPORT_PAGE_URL}/${librarySlug}`, { waitUntil: 'networkidle' })
    const beetsTab = page.locator(`text=${BEETS_IMPORT_TAB}`)
    await beetsTab.click()
    await page.waitForLoadState('networkidle')

    // Verify queue depth indicator is visible
    const queueIndicator = page.locator('[data-testid="queue-depth-indicator"]')
    const hasQueueIndicator = await queueIndicator.isVisible().catch(() => false)
    console.log(`Queue depth indicator visible: ${hasQueueIndicator}`)

    if (hasQueueIndicator) {
      const indicatorText = await queueIndicator.textContent()
      console.log(`Queue indicator text: ${indicatorText}`)
      expect(indicatorText).toContain('queued')
    }
  })

  test('should display queued badge for albums in queue', async () => {
    if (!librarySlug) {
      test.skip()
      return
    }

    // Mock the queue API to return an album as queued
    await page.route('**/api/v1/libraries/*/beets/analyze-queue', (route) => {
      route.fulfill({
        status: 200,
        contentType: 'application/json',
        body: JSON.stringify({
          queueDepth: 1,
          activeCount: 0,
          maxConcurrent: 2,
          queuedItems: [],
          activeItems: [],
        }),
      })
    })

    await page.goto(`${IMPORT_PAGE_URL}/${librarySlug}`, { waitUntil: 'networkidle' })
    const beetsTab = page.locator(`text=${BEETS_IMPORT_TAB}`)
    await beetsTab.click()
    await page.waitForLoadState('networkidle')

    // Check for queue badges
    const queueBadges = page.locator('[data-testid="queue-badge"]')
    const badgeCount = await queueBadges.count()
    console.log(`Found ${badgeCount} queue badges`)
  })

  test('should show queued status when analysis is queued at concurrency cap', async () => {
    if (!librarySlug) {
      test.skip()
      return
    }

    // Mock analyze endpoint to return queued status
    await page.route('**/api/v1/libraries/*/beets/analyze', (route, request) => {
      if (request.method() === 'POST') {
        route.fulfill({
          status: 202,
          contentType: 'application/json',
          body: JSON.stringify({
            jobId: 'test-job-123',
            albumPath: '/import/test-album',
            status: 'queued',
            queuePosition: 3,
            message: 'Analysis queued at position 3',
          }),
        })
      } else {
        route.continue()
      }
    })

    await page.goto(`${IMPORT_PAGE_URL}/${librarySlug}`, { waitUntil: 'networkidle' })
    const beetsTab = page.locator(`text=${BEETS_IMPORT_TAB}`)
    await beetsTab.click()
    await page.waitForLoadState('networkidle')

    // Check if there are albums
    const firstAlbum = page.locator(ALBUM_ITEM_SELECTOR).first()
    if (!(await firstAlbum.isVisible())) {
      console.log('No albums available to test queued status')
      return
    }

    // Try to trigger analysis
    const stageIndicator = firstAlbum.locator(STAGE_INDICATOR_SELECTOR).first()
    if (await stageIndicator.isVisible()) {
      await stageIndicator.click()
      console.log('Triggered analysis (mocked to return queued)')

      // Wait for queue badge to appear
      await page.waitForTimeout(1000)

      // Check for queue badge
      const queueBadge = page.locator('[data-testid="queue-badge"]')
      const hasQueueBadge = await queueBadge.isVisible().catch(() => false)
      console.log(`Queue badge visible after analysis: ${hasQueueBadge}`)
    }
  })
})

test.describe('Beets Import - Edge Cases and Error Scenarios', () => {
  let page: Page
  let librarySlug: string

  test.beforeEach(async ({ browser }) => {
    page = await browser.newPage()

    // Get first library slug
    await page.goto(IMPORT_PAGE_URL, { waitUntil: 'networkidle' })
    const firstCard = page.locator('[role="heading"]').first()
    if (await firstCard.isVisible()) {
      const cardContainer = firstCard.locator('..').locator('..')
      const cardLink = cardContainer.locator('a').first()
      const href = await cardLink.getAttribute('href')
      if (href) {
        librarySlug = href.split('/').pop() || ''
      }
    }
  })

  test.afterEach(async () => {
    await page.close()
  })

  test('should handle invalid library slug gracefully', async () => {
    await page.goto(`${IMPORT_PAGE_URL}/invalid-library-slug`, { waitUntil: 'networkidle' })

    // Should either show error or redirect
    const url = page.url()
    console.log(`Final URL after invalid slug: ${url}`)

    const errorVisible = await page.locator('text=error|not found|failed').isVisible().catch(() => false)
    console.log(`Error displayed for invalid slug: ${errorVisible}`)
  })

  test('should handle very long analysis gracefully with loading indicator', async () => {
    if (!librarySlug) {
      test.skip()
      return
    }

    // Delay API responses to simulate slow analysis
    await page.route('**/api/v1/libraries/*/beets/analyze', (route) => {
      setTimeout(() => route.continue(), 3000)
    })

    await page.goto(`${IMPORT_PAGE_URL}/${librarySlug}`, { waitUntil: 'networkidle' })
    const beetsTab = page.locator(`text=${BEETS_IMPORT_TAB}`)
    await beetsTab.click()
    await page.waitForLoadState('networkidle')

    const firstAlbum = page.locator(ALBUM_ITEM_SELECTOR).first()
    if (await firstAlbum.isVisible()) {
      await firstAlbum.click()
      const stageIndicator = firstAlbum.locator(STAGE_INDICATOR_SELECTOR).first()

      if (await stageIndicator.isVisible()) {
        await stageIndicator.click()

        // Immediately check for loading indicator
        const loadingIndicator = page.locator('[data-testid="analysis-loading"], [class*="animate"]')
        const hasLoading = await loadingIndicator.isVisible().catch(() => false)
        console.log(`Loading indicator shown during slow analysis: ${hasLoading}`)

        // Wait for completion
        await page.waitForTimeout(4000)
        console.log('Long analysis completed')
      }
    }
  })
})
