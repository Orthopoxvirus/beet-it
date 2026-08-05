# E2E Tests for Import Folder Watchers

This directory contains end-to-end tests for the scan flow feature using Playwright.

## Overview

The E2E tests verify the complete workflow for scanning import folders:

1. **Navigating to the Import Page** - Verify library cards are displayed
2. **Triggering a Scan** - Click the "Scan Now" button and confirm the action is initiated
3. **Monitoring Progress** - Verify progress updates are displayed in real-time via SSE
4. **Handling Status Changes** - Test scanning, extracting metadata, queued, blocked, and error states
5. **Scan Completion** - Verify the scan completes successfully and displays final results
6. **Error Handling** - Test graceful error handling for various failure scenarios

## Test Files

- **scan-flow.spec.ts** - Main E2E test suite for the complete scan workflow
- **beets-import.spec.ts** - E2E test suite for the Beets Import UI and candidate analysis workflow

## Setup Instructions

### 1. Install Playwright

```bash
cd frontend
npm install --save-dev @playwright/test
```

### 2. Update package.json scripts

Add these scripts to `frontend/package.json`:

```json
{
  "scripts": {
    "test:e2e": "playwright test",
    "test:e2e:ui": "playwright test --ui",
    "test:e2e:debug": "playwright test --debug",
    "test:e2e:report": "playwright show-report"
  }
}
```

### 3. Prerequisites for Running Tests

Before running E2E tests, ensure:

- **Backend is running**: `http://localhost:8000`
- **Frontend dev server is running**: `http://localhost:3000`
- **At least one library is created** in the system
- **Import folder path is accessible** and contains music files
- **Watchers are enabled**: `ENABLE_IMPORT_WATCHERS=true` in backend `.env`

### 4. Running Tests

#### Run all E2E tests

```bash
npm run test:e2e
```

#### Run tests in UI mode (interactive)

```bash
npm run test:e2e:ui
```

This opens an interactive browser where you can:
- Watch tests run in real-time
- Step through individual tests
- Inspect DOM at each step
- View network requests

#### Run tests in debug mode

```bash
npm run test:e2e:debug
```

This opens Playwright Inspector for detailed debugging.

#### Run specific test file

```bash
npx playwright test e2e/scan-flow.spec.ts
```

#### Run specific test file - Beets Import

```bash
npx playwright test e2e/beets-import.spec.ts
```

#### Run specific test - Beets Import workflow

```bash
npx playwright test e2e/beets-import.spec.ts -g "should navigate to Beets Import tab"
```

#### Run specific test

```bash
npx playwright test e2e/scan-flow.spec.ts -g "should navigate to import page"
```

#### View test report

```bash
npm run test:e2e:report
```

## Test Coverage

### Beets Import Workflow Tests

These tests verify the complete beets import UI workflow:

- **Main Workflow (10.1)**: Navigate to Beets Import tab → Select album → Trigger analysis → Verify results
- **Responsive Layout Tests**:
  - Mobile viewport (375x667): Components stack vertically
  - Desktop viewport (1280x800): Components display side-by-side
- **Error Handling Tests**:
  - Network failure during analysis
  - API errors and error state display
- **Re-analysis Flow**: Clicking disc icon on already-analyzed albums
- **Edge Cases**:
  - Empty state when no albums found
  - Loading state while fetching albums
  - Track comparison table display
  - Similarity score calculation and display
  - Invalid library slug handling
  - Long-running analysis with loading indicators

### Basic Navigation Tests

- Navigate to import page
- Verify library cards are displayed
- Verify library cards are clickable

### Progress Monitoring Tests

- Scan starts and progress bar appears
- Progress percentage updates correctly (25%, 50%, 75%, 100%)
- Progress text changes (Scanning → Extracting metadata)
- Current file being processed is displayed
- Elapsed time is calculated and displayed
- Item count updates (e.g., "50 / 100 items")

### Status State Tests

- **Scanning State** - Progress bar with percentage
- **Queued State** - Shows "Scan queued" or position in queue
- **Blocked State** - Shows blocking operations
- **Error State** - Shows error message
- **Completed State** - Progress bar disappears, completion info shown

### Multi-Library Tests

- Multiple libraries can have different scan states
- Library cards show correct progress for their respective scans
- Progress for one library doesn't affect others

### Library Detail Page Tests

- Scan progress section appears at top
- "Scan Now" button visible when no scan active
- Button disabled during scan
- Watcher status displayed
- Last completed scan info shown

### Error Handling Tests

- Permission denied errors displayed
- Invalid import paths handled gracefully
- API errors handled gracefully
- SSE reconnection on connection drop
- Connection errors don't crash the app

## Configuration

### Timeouts

The tests use reasonable timeouts:

- **Navigation**: 5 seconds
- **Element visibility**: 5 seconds
- **Scan completion**: 1 hour (for actual scans with large libraries)
- **SSE connection**: 5 seconds

### Environment Variables

If needed, you can override the base URL in `playwright.config.ts`:

```typescript
use: {
  baseURL: 'http://localhost:3000',
}
```

## Debugging Failed Tests

### Check HTML Report

```bash
npm run test:e2e:report
```

This shows detailed information about each test including:
- Screenshots at each step
- Network requests
- Console logs
- Video recordings (if configured)

### Enable Video Recording

Add to `playwright.config.ts`:

```typescript
use: {
  video: 'retain-on-failure',
}
```

### Enable Screenshots

```typescript
use: {
  screenshot: 'only-on-failure',
}
```

### View Browser Logs

Tests log important events to console:

```
PAGE LOG: [useScanProgress] Connected
PAGE LOG: [useScanProgress] Scan started: {...}
PAGE LOG: [useScanProgress] Scan progress: {...}
```

## Known Limitations

1. **Scan Duration**: Real scans can take a long time depending on library size. The test waits up to 1 hour.
2. **File System**: Tests require actual music files in the import directory to produce meaningful progress.
3. **Backend Availability**: Tests require both backend and frontend to be running.
4. **Library Data**: Tests need at least one library with a valid import path.

## Tips for Reliable Tests

1. **Use UI mode during development**: `npm run test:e2e:ui`
2. **Test against known library**: Create a test library with known music files
3. **Check backend logs**: Backend logs can help understand what's happening
4. **Use small library first**: Start with 10-50 files to test quickly
5. **Network issues**: Ensure localhost is accessible without VPN/proxy

## Extending Tests

To add new tests:

1. Create a new `test()` block in `scan-flow.spec.ts`
2. Use descriptive names and comments
3. Add console.log() statements for debugging
4. Use `page.locator()` with clear selectors
5. Handle cases where elements might not be present

Example:

```typescript
test('should verify new feature behavior', async () => {
  await page.goto('http://localhost:3000/import')

  // Your test code here
  const element = page.locator('selector')
  await expect(element).toBeVisible()
  console.log('Feature works as expected')
})
```

## CI/CD Integration

To run tests in CI:

```bash
# Install dependencies
npm install

# Run tests (no UI mode)
npm run test:e2e

# Generate report
npm run test:e2e:report
```

Add to your CI workflow (e.g., GitHub Actions):

```yaml
- name: Run E2E tests
  run: npm run test:e2e

- name: Upload test results
  uses: actions/upload-artifact@v2
  if: always()
  with:
    name: playwright-report
    path: frontend/playwright-report/
```

## Troubleshooting

### Tests hang or timeout

- Check if backend is running: `curl http://localhost:8000/`
- Check if frontend is running: `curl http://localhost:3000/`
- Verify library exists in database
- Check backend logs for errors

### Progress bar not appearing

- Verify SSE endpoint is accessible: `curl http://localhost:8000/api/libraries/{slug}/scan/progress`
- Check browser console for connection errors
- Ensure backend has scan service running

### Scan doesn't trigger

- Check that library has valid import path
- Verify path exists and is readable
- Check backend logs for permission errors
- Ensure watchers are enabled

### Tests pass locally but fail in CI

- Check environment variables in CI
- Verify database is initialized
- Ensure music files exist in test library
- Check network connectivity in CI

## References

- [Playwright Documentation](https://playwright.dev/)
- [Playwright Test API](https://playwright.dev/docs/api/class-test)
- [Selectors Documentation](https://playwright.dev/docs/selectors)
