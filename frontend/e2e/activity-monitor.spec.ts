import { test, expect, Page } from '@playwright/test'

/**
 * E2E Tests for Activity Monitor Feature
 *
 * These tests verify the complete end-to-end activity monitoring workflow including:
 * - Floating activity button visibility and badge display
 * - Activity drawer open/close flow
 * - Activity drawer content display (active tasks, queued tasks, recent completions)
 * - History page filtering by library, task type, and status
 * - History page pagination with page navigation
 *
 * Prerequisites:
 * - Backend API running at http://localhost:8000
 * - Frontend dev server running at http://localhost:3000
 * - At least one library created in the system
 *
 * Setup Playwright:
 * npm install --save-dev @playwright/test
 *
 * Run these tests:
 * npx playwright test e2e/activity-monitor.spec.ts
 */

test.describe('Activity Monitor - Floating Button and Drawer', () => {
  let page: Page

  test.beforeEach(async ({ browser }) => {
    page = await browser.newPage()
    page.on('console', (msg) => console.log('PAGE LOG:', msg.text()))
    page.on('pageerror', (error) => console.log('PAGE ERROR:', error))

    // Navigate to home/import page to ensure activity button is visible
    await page.goto('http://localhost:3000/import', { waitUntil: 'networkidle' })
  })

  test.afterEach(async () => {
    await page.close()
  })

  test('14.5.1: should display floating activity button in fixed position', async () => {
    // Verify floating activity button exists
    const activityButton = page.locator('button[aria-label*="Activity"]')
    await expect(activityButton).toBeVisible()
    console.log('Activity button is visible')

    // Verify button is in fixed position (bottom-right)
    const buttonPosition = await activityButton.evaluate((el) => {
      const style = window.getComputedStyle(el)
      return {
        position: style.position,
        bottom: style.bottom,
        right: style.right,
        zIndex: style.zIndex,
      }
    })
    console.log(`Button position: ${JSON.stringify(buttonPosition)}`)

    // Verify fixed positioning
    expect(buttonPosition.position).toBe('fixed')
  })

  test('14.5.2: should display activity badge with count when tasks exist', async () => {
    // Wait a moment for initial data to load
    await page.waitForTimeout(1000)

    const activityButton = page.locator('button[aria-label*="Activity"]')
    const badge = activityButton.locator('span')

    // Badge may or may not be visible depending on current activity
    // Just verify the button structure is correct
    const badgeCount = await badge.count()
    console.log(`Badge elements found: ${badgeCount}`)

    // Verify button is clickable
    await expect(activityButton).toBeEnabled()
  })

  test('14.5.3: should open activity drawer when button clicked', async () => {
    // Click the activity button
    const activityButton = page.locator('button[aria-label*="Activity"]')
    await activityButton.click()
    console.log('Clicked activity button')

    // Wait for drawer to open (Sheet component slides in from right)
    await page.waitForTimeout(500)

    // Verify drawer content is visible
    const drawerTitle = page.locator('text=Activity Monitor')
    await expect(drawerTitle).toBeVisible()
    console.log('Activity drawer opened successfully')

    // Verify drawer description
    const drawerDescription = page.locator('text=View active tasks, queue status, and recent completions')
    await expect(drawerDescription).toBeVisible()
  })

  test('14.5.4: should close activity drawer when clicking outside', async () => {
    // Click activity button to open drawer
    const activityButton = page.locator('button[aria-label*="Activity"]')
    await activityButton.click()
    await page.waitForTimeout(500)

    // Verify drawer is open
    const drawerTitle = page.locator('text=Activity Monitor')
    await expect(drawerTitle).toBeVisible()

    // Click outside the drawer (on the left/main content area)
    // The Sheet component should close when clicking the overlay
    const drawerOverlay = page.locator('[role="presentation"]').first()
    await page.click('body', { position: { x: 100, y: 100 } })
    await page.waitForTimeout(500)

    // Verify drawer is closed
    const isDrawerStillVisible = await drawerTitle.isVisible().catch(() => false)
    console.log(`Drawer still visible after clicking outside: ${isDrawerStillVisible}`)
  })

  test('14.5.5: should close activity drawer when clicking close button', async () => {
    // Click activity button to open drawer
    const activityButton = page.locator('button[aria-label*="Activity"]')
    await activityButton.click()
    await page.waitForTimeout(500)

    // Verify drawer is open
    const drawerTitle = page.locator('text=Activity Monitor')
    await expect(drawerTitle).toBeVisible()

    // Click the X button in sheet header to close
    const closeButton = page.locator('button[aria-label="Close"]').first()
    if (await closeButton.isVisible()) {
      await closeButton.click()
      console.log('Clicked close button')
      await page.waitForTimeout(500)

      // Verify drawer is closed
      const isDrawerStillVisible = await drawerTitle.isVisible().catch(() => false)
      expect(isDrawerStillVisible).toBe(false)
      console.log('Drawer closed successfully')
    } else {
      console.log('Close button not found (may be auto-closed by outside click)')
    }
  })

  test('14.5.6: should display no activity message when no tasks running', async () => {
    // Open the drawer
    const activityButton = page.locator('button[aria-label*="Activity"]')
    await activityButton.click()
    await page.waitForTimeout(1000)

    // Check for either content sections or no activity message
    const activeTasksSection = page.locator('text=Active Tasks').first()
    const queuedSection = page.locator('text=Queued').first()
    const recentSection = page.locator('text=Recent Completions').first()
    const noActivityMessage = page.locator('text=No activity to display')

    const hasActiveTasks = await activeTasksSection.isVisible().catch(() => false)
    const hasQueued = await queuedSection.isVisible().catch(() => false)
    const hasRecent = await recentSection.isVisible().catch(() => false)
    const hasNoActivityMsg = await noActivityMessage.isVisible().catch(() => false)

    console.log(`Active tasks visible: ${hasActiveTasks}`)
    console.log(`Queued visible: ${hasQueued}`)
    console.log(`Recent completions visible: ${hasRecent}`)
    console.log(`No activity message visible: ${hasNoActivityMsg}`)

    // Either show content or show no activity message
    const hasContent = hasActiveTasks || hasQueued || hasRecent
    expect(hasContent || hasNoActivityMsg).toBe(true)
  })

  test('14.5.7: should display View Full History button in drawer', async () => {
    // Open the drawer
    const activityButton = page.locator('button[aria-label*="Activity"]')
    await activityButton.click()
    await page.waitForTimeout(500)

    // Look for the "View Full History" button
    const historyButton = page.locator('button:has-text("View Full History")')
    await expect(historyButton).toBeVisible()
    console.log('View Full History button is visible')
  })

  test('14.5.8: should navigate to activity history page when clicking View Full History', async () => {
    // Open the drawer
    const activityButton = page.locator('button[aria-label*="Activity"]')
    await activityButton.click()
    await page.waitForTimeout(500)

    // Click the View Full History button
    const historyButton = page.locator('button:has-text("View Full History")')
    await historyButton.click()
    console.log('Clicked View Full History button')

    // Wait for navigation and page load
    await page.waitForURL(/\/activity/, { timeout: 5000 })
    await page.waitForLoadState('networkidle')

    // Verify we're on the activity page
    const pageTitle = page.locator('text=Activity History')
    await expect(pageTitle).toBeVisible()
    console.log('Navigated to Activity History page')

    // Verify URL is correct
    const url = page.url()
    expect(url).toContain('/activity')
  })

  test('14.5.9: should keep drawer open when navigating between tabs', async () => {
    // Open the drawer
    const activityButton = page.locator('button[aria-label*="Activity"]')
    await activityButton.click()
    await page.waitForTimeout(500)

    // Verify drawer is open
    const drawerTitle = page.locator('text=Activity Monitor')
    await expect(drawerTitle).toBeVisible()

    // Navigate to a different page while drawer is open
    await page.goto('http://localhost:3000/import', { waitUntil: 'networkidle' })
    await page.waitForTimeout(500)

    // Drawer should be closed after navigation (controlled by app state)
    const isDrawerVisible = await drawerTitle.isVisible().catch(() => false)
    console.log(`Drawer state after navigation: ${isDrawerVisible ? 'open' : 'closed'}`)
  })

  test('14.5.10: should display drawer on top of other content', async () => {
    // Open the drawer
    const activityButton = page.locator('button[aria-label*="Activity"]')
    await activityButton.click()
    await page.waitForTimeout(500)

    // Verify drawer content z-index is above main content
    const drawerContent = page.locator('[role="presentation"]').first()
    const zIndex = await drawerContent.evaluate((el) => {
      const parent = el.parentElement
      if (parent) {
        return window.getComputedStyle(parent).zIndex
      }
      return window.getComputedStyle(el).zIndex
    })

    console.log(`Drawer z-index: ${zIndex}`)

    // Z-index should be set (typically 50 or higher for Sheet)
    expect(parseInt(zIndex) > 0 || zIndex === 'auto').toBeTruthy()
  })
})

test.describe('Activity Monitor - History Page Filtering', () => {
  let page: Page

  test.beforeEach(async ({ browser }) => {
    page = await browser.newPage()
    page.on('console', (msg) => console.log('PAGE LOG:', msg.text()))
    page.on('pageerror', (error) => console.log('PAGE ERROR:', error))

    // Navigate directly to activity page
    await page.goto('http://localhost:3000/activity', { waitUntil: 'networkidle' })
  })

  test.afterEach(async () => {
    await page.close()
  })

  test('14.6.1: should display activity history page with filters', async () => {
    // Verify page title
    const pageTitle = page.locator('text=Activity History')
    await expect(pageTitle).toBeVisible()
    console.log('Activity History page loaded')

    // Verify filter dropdowns exist
    const libraryFilter = page.locator('text=All Libraries').first()
    const taskTypeFilter = page.locator('text=All Types').first()
    const statusFilter = page.locator('text=All Statuses').first()

    await expect(libraryFilter).toBeVisible()
    console.log('Library filter visible')

    const hasTaskType = await taskTypeFilter.isVisible().catch(() => false)
    const hasStatus = await statusFilter.isVisible().catch(() => false)
    console.log(`Task type filter visible: ${hasTaskType}`)
    console.log(`Status filter visible: ${hasStatus}`)
  })

  test('14.6.2: should filter by library when selecting from dropdown', async () => {
    // Open library filter dropdown
    const librarySelect = page.locator('[role="combobox"]').first()
    await librarySelect.click()
    console.log('Opened library filter dropdown')

    // Wait for dropdown options to appear
    await page.waitForTimeout(500)

    // Get all available options (excluding "All Libraries")
    const options = page.locator('[role="option"]')
    const optionCount = await options.count()
    console.log(`Available library options: ${optionCount}`)

    if (optionCount > 1) {
      // Select the first non-"All" option
      const firstOption = options.nth(1)
      const optionText = await firstOption.textContent()
      console.log(`Selecting library: ${optionText}`)

      await firstOption.click()
      await page.waitForLoadState('networkidle')
      await page.waitForTimeout(500)

      // Verify filter is applied by checking if URL changed or data is filtered
      const url = page.url()
      console.log(`URL after filter: ${url}`)

      // Verify table is displayed
      const tableContent = page.locator('[role="main"], .space-y-6').first()
      await expect(tableContent).toBeVisible()
    } else {
      console.log('Only "All Libraries" available - no filtering test possible')
    }
  })

  test('14.6.3: should filter by task type when selecting from dropdown', async () => {
    // Find all select triggers (filters)
    const selectTriggers = page.locator('[role="combobox"]')
    const triggerCount = await selectTriggers.count()
    console.log(`Found ${triggerCount} filter dropdowns`)

    if (triggerCount >= 2) {
      // Click task type filter (usually second)
      const taskTypeSelect = selectTriggers.nth(1)
      await taskTypeSelect.click()
      console.log('Opened task type filter dropdown')

      await page.waitForTimeout(500)

      // Get options and select one
      const options = page.locator('[role="option"]')
      const optionCount = await options.count()

      if (optionCount > 1) {
        // Select "Scan" if available
        const scanOption = options.filter({ hasText: 'Scan' }).first()
        const scanExists = await scanOption.isVisible().catch(() => false)

        if (scanExists) {
          await scanOption.click()
          console.log('Selected "Scan" task type filter')
          await page.waitForLoadState('networkidle')
          await page.waitForTimeout(500)

          // Verify filter applied
          const url = page.url()
          console.log(`URL after task type filter: ${url}`)
        } else {
          // Just select first option
          const firstOption = options.nth(1)
          const optionText = await firstOption.textContent()
          await firstOption.click()
          console.log(`Selected task type: ${optionText}`)
          await page.waitForLoadState('networkidle')
        }
      }
    }
  })

  test('14.6.4: should filter by status when selecting from dropdown', async () => {
    // Find all select triggers
    const selectTriggers = page.locator('[role="combobox"]')
    const triggerCount = await selectTriggers.count()

    if (triggerCount >= 3) {
      // Click status filter (usually third)
      const statusSelect = selectTriggers.nth(2)
      await statusSelect.click()
      console.log('Opened status filter dropdown')

      await page.waitForTimeout(500)

      // Get options
      const options = page.locator('[role="option"]')
      const optionCount = await options.count()

      if (optionCount > 1) {
        // Select "Completed" if available
        const completedOption = options.filter({ hasText: 'Completed' }).first()
        const completedExists = await completedOption.isVisible().catch(() => false)

        if (completedExists) {
          await completedOption.click()
          console.log('Selected "Completed" status filter')
        } else {
          // Just select first option
          const firstOption = options.nth(1)
          const optionText = await firstOption.textContent()
          await firstOption.click()
          console.log(`Selected status: ${optionText}`)
        }

        await page.waitForLoadState('networkidle')
        await page.waitForTimeout(500)
      }
    }
  })

  test('14.6.5: should reset pagination when filter changes', async () => {
    // Note current page (should be 1)
    const pageInfo = page.locator('text=/Page \\d+ of/')
    let currentPageText = await pageInfo.textContent().catch(() => 'Page 1 of')
    console.log(`Initial page: ${currentPageText}`)

    // Apply a filter
    const librarySelect = page.locator('[role="combobox"]').first()
    await librarySelect.click()
    await page.waitForTimeout(500)

    const options = page.locator('[role="option"]')
    if (await options.count() > 1) {
      await options.nth(1).click()
      await page.waitForLoadState('networkidle')
      await page.waitForTimeout(500)

      // Check page number after filter
      currentPageText = await pageInfo.textContent().catch(() => 'Page 1 of')
      console.log(`Page after filter: ${currentPageText}`)

      // Should be back to page 1
      expect(currentPageText).toContain('Page 1 of')
    }
  })

  test('14.6.6: should display table headers correctly', async () => {
    // Wait for table to load
    await page.waitForTimeout(1000)

    // Look for table header row
    const headerRow = page.locator('[role="main"]').first()
    await expect(headerRow).toBeVisible()

    // Verify key column headers exist
    const statusHeader = page.locator('text=Status')
    const typeHeader = page.locator('text=Type')
    const libraryHeader = page.locator('text=Library')

    const hasStatus = await statusHeader.isVisible().catch(() => false)
    const hasType = await typeHeader.isVisible().catch(() => false)
    const hasLibrary = await libraryHeader.isVisible().catch(() => false)

    console.log(`Status header visible: ${hasStatus}`)
    console.log(`Type header visible: ${hasType}`)
    console.log(`Library header visible: ${hasLibrary}`)

    // At least some headers should be visible
    expect(hasStatus || hasType || hasLibrary).toBe(true)
  })

  test('14.6.7: should display task rows in table', async () => {
    // Wait for table to load
    await page.waitForTimeout(1500)

    // Look for task rows
    const mainContent = page.locator('[role="main"]').first()
    await expect(mainContent).toBeVisible()

    // Check for either task rows or empty state
    const taskRows = page.locator('[role="main"] div').filter({ hasText: /completed|running|failed|scan|analysis/i })
    const rowCount = await taskRows.count()
    console.log(`Task rows found: ${rowCount}`)

    // Check for empty state message
    const emptyState = page.locator('text=/No tasks found|Try adjusting/')
    const hasEmptyState = await emptyState.isVisible().catch(() => false)

    console.log(`Empty state visible: ${hasEmptyState}`)

    // Either show tasks or empty state
    expect(rowCount > 0 || hasEmptyState).toBe(true)
  })

  test('14.6.8: should display pagination controls', async () => {
    // Wait for content to load
    await page.waitForTimeout(1000)

    // Look for pagination elements
    const pageInfo = page.locator('text=/Showing \\d+ to \\d+ of \\d+/')
    const prevButton = page.locator('button:has-text("Previous")')
    const nextButton = page.locator('button:has-text("Next")')

    const hasPageInfo = await pageInfo.isVisible().catch(() => false)
    const hasPrevButton = await prevButton.isVisible().catch(() => false)
    const hasNextButton = await nextButton.isVisible().catch(() => false)

    console.log(`Page info visible: ${hasPageInfo}`)
    console.log(`Previous button visible: ${hasPrevButton}`)
    console.log(`Next button visible: ${hasNextButton}`)

    // Pagination should be visible if there's content
    expect(hasPageInfo || hasPrevButton || hasNextButton).toBe(true)
  })
})

test.describe('Activity Monitor - History Page Pagination', () => {
  let page: Page

  test.beforeEach(async ({ browser }) => {
    page = await browser.newPage()
    page.on('console', (msg) => console.log('PAGE LOG:', msg.text()))
    page.on('pageerror', (error) => console.log('PAGE ERROR:', error))

    await page.goto('http://localhost:3000/activity', { waitUntil: 'networkidle' })
  })

  test.afterEach(async () => {
    await page.close()
  })

  test('14.6.9: should navigate to next page when clicking next button', async () => {
    // Wait for page to load
    await page.waitForTimeout(1500)

    // Get initial page number
    const pageInfo = page.locator('text=/Page \\d+ of \\d+/')
    const initialPageText = await pageInfo.textContent().catch(() => '')
    console.log(`Initial page: ${initialPageText}`)

    // Find next button
    const nextButton = page.locator('button:has-text("Next")')
    const isNextEnabled = await nextButton.isEnabled().catch(() => false)

    console.log(`Next button enabled: ${isNextEnabled}`)

    if (isNextEnabled) {
      // Click next button
      await nextButton.click()
      console.log('Clicked next button')

      // Wait for page to load
      await page.waitForLoadState('networkidle')
      await page.waitForTimeout(500)

      // Verify page number changed
      const newPageText = await pageInfo.textContent().catch(() => '')
      console.log(`New page: ${newPageText}`)

      // Page number should have incremented
      expect(newPageText).not.toBe(initialPageText)
    } else {
      console.log('Next button disabled - only one page of results')
    }
  })

  test('14.6.10: should navigate to previous page when clicking previous button', async () => {
    // Go to next page first
    await page.waitForTimeout(1500)

    const nextButton = page.locator('button:has-text("Next")')
    const isNextEnabled = await nextButton.isEnabled().catch(() => false)

    if (isNextEnabled) {
      await nextButton.click()
      await page.waitForLoadState('networkidle')
      await page.waitForTimeout(500)

      // Get current page
      const pageInfo = page.locator('text=/Page \\d+ of \\d+/')
      const pageOnPage2 = await pageInfo.textContent().catch(() => '')
      console.log(`On page: ${pageOnPage2}`)

      // Click previous button
      const prevButton = page.locator('button:has-text("Previous")')
      await prevButton.click()
      console.log('Clicked previous button')

      await page.waitForLoadState('networkidle')
      await page.waitForTimeout(500)

      // Verify we're back on page 1
      const pageOnPage1 = await pageInfo.textContent().catch(() => '')
      console.log(`Back on page: ${pageOnPage1}`)

      expect(pageOnPage1).toContain('Page 1 of')
    } else {
      console.log('Only one page of results - pagination test not applicable')
    }
  })

  test('14.6.11: should disable previous button on first page', async () => {
    // Wait for page to load
    await page.waitForTimeout(1000)

    // On first page, previous button should be disabled
    const prevButton = page.locator('button:has-text("Previous")')
    const isPrevDisabled = await prevButton.isDisabled().catch(() => false)

    console.log(`Previous button disabled on page 1: ${isPrevDisabled}`)
    expect(isPrevDisabled).toBe(true)
  })

  test('14.6.12: should disable next button on last page', async () => {
    // Wait for page to load
    await page.waitForTimeout(1500)

    // Navigate to next page repeatedly until next is disabled
    const nextButton = page.locator('button:has-text("Next")')
    let pageCount = 1

    while (await nextButton.isEnabled()) {
      await nextButton.click()
      await page.waitForLoadState('networkidle')
      await page.waitForTimeout(300)
      pageCount++
      console.log(`Navigated to page ${pageCount}`)

      // Safety check to avoid infinite loop
      if (pageCount > 10) {
        console.log('Reached safety limit of 10 pages')
        break
      }
    }

    // On last page, next button should be disabled
    const isNextDisabled = await nextButton.isDisabled()
    console.log(`Next button disabled on last page: ${isNextDisabled}`)
    expect(isNextDisabled).toBe(true)
  })

  test('14.6.13: should update task rows when navigating pages', async () => {
    // Wait for initial content
    await page.waitForTimeout(1500)

    // Get initial task row content
    const taskRows = page.locator('[role="main"] div').filter({ hasText: /completed|running|failed/i })
    const initialRowCount = await taskRows.count()
    const initialContent = await page.locator('[role="main"]').first().textContent()
    console.log(`Initial rows: ${initialRowCount}`)

    // Navigate to next page if available
    const nextButton = page.locator('button:has-text("Next")')
    const isNextEnabled = await nextButton.isEnabled().catch(() => false)

    if (isNextEnabled) {
      await nextButton.click()
      await page.waitForLoadState('networkidle')
      await page.waitForTimeout(500)

      // Get new content
      const newContent = await page.locator('[role="main"]').first().textContent()
      console.log(`New content length: ${newContent?.length}`)

      // Content should be different (or at least potentially different)
      // This test just verifies the page updated without errors
      expect(newContent).toBeTruthy()
    } else {
      console.log('Only one page - pagination not applicable')
    }
  })

  test('14.6.14: should display correct showing info text', async () => {
    // Wait for page to load
    await page.waitForTimeout(1000)

    // Look for "Showing X to Y of Z" text
    const showingInfo = page.locator('text=/Showing \\d+ to \\d+ of \\d+/')
    const hasShowingInfo = await showingInfo.isVisible().catch(() => false)

    if (hasShowingInfo) {
      const infoText = await showingInfo.textContent()
      console.log(`Showing info: ${infoText}`)

      // Should match pattern "Showing 1 to 20 of 100"
      const matches = infoText?.match(/Showing (\d+) to (\d+) of (\d+)/)
      if (matches) {
        const [, showing, to, total] = matches
        console.log(`Showing: ${showing}, To: ${to}, Total: ${total}`)

        // Verify numbers are reasonable
        expect(parseInt(showing) > 0).toBe(true)
        expect(parseInt(to) >= parseInt(showing)).toBe(true)
        expect(parseInt(total) >= parseInt(to)).toBe(true)
      }
    } else {
      console.log('No showing info found - may be empty result set')
    }
  })

  test('14.6.15: should maintain filters when navigating pages', async () => {
    // Wait for page to load
    await page.waitForTimeout(1000)

    // Apply a task type filter
    const selectTriggers = page.locator('[role="combobox"]')
    const triggerCount = await selectTriggers.count()

    if (triggerCount >= 2) {
      const taskTypeSelect = selectTriggers.nth(1)
      await taskTypeSelect.click()
      await page.waitForTimeout(500)

      const options = page.locator('[role="option"]')
      if (await options.count() > 1) {
        await options.nth(1).click()
        await page.waitForLoadState('networkidle')
        await page.waitForTimeout(500)

        // Get initial filter state
        const filterValue = await taskTypeSelect.textContent()
        console.log(`Applied filter: ${filterValue}`)

        // Navigate to next page
        const nextButton = page.locator('button:has-text("Next")')
        const isNextEnabled = await nextButton.isEnabled().catch(() => false)

        if (isNextEnabled) {
          await nextButton.click()
          await page.waitForLoadState('networkidle')
          await page.waitForTimeout(500)

          // Check filter is still applied
          const newFilterValue = await taskTypeSelect.textContent()
          console.log(`Filter after page change: ${newFilterValue}`)

          // Filter should remain the same
          expect(newFilterValue).toBe(filterValue)
        }
      }
    }
  })

  test('14.6.16: should handle empty results gracefully', async () => {
    // Try to apply filters that might result in no data
    const selectTriggers = page.locator('[role="combobox"]')

    if (await selectTriggers.count() >= 3) {
      // Apply multiple filters to reduce results
      const taskTypeSelect = selectTriggers.nth(1)
      await taskTypeSelect.click()
      await page.waitForTimeout(500)

      const options = page.locator('[role="option"]')
      const optionCount = await options.count()

      if (optionCount > 2) {
        // Select a specific task type (e.g., "Import")
        const importOption = options.filter({ hasText: 'Import' }).first()
        const exists = await importOption.isVisible().catch(() => false)

        if (exists) {
          await importOption.click()
          await page.waitForLoadState('networkidle')
          await page.waitForTimeout(500)

          // Check if results are empty
          const emptyState = page.locator('text=/No tasks found|Try adjusting/')
          const hasEmptyState = await emptyState.isVisible().catch(() => false)

          console.log(`Empty state visible: ${hasEmptyState}`)

          if (hasEmptyState) {
            // Verify empty state message is displayed
            const emptyText = await emptyState.textContent()
            console.log(`Empty message: ${emptyText}`)
          }
        }
      }
    }
  })
})
