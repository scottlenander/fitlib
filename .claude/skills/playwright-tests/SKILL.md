---
name: playwright-tests
description: Write, change or debug the Playwright end-to-end tests in tests/e2e/ for fitlib's web app. Use when asked to add a browser/e2e/Playwright test, cover a new page or feature in e2e, update tests after a UI change, add or change a page object or component, or work out why a Playwright test fails or is flaky (locally or in the GitHub "Playwright (Chromium)" check).
---

# Playwright tests (tests/e2e/)

The suite tests fitlib's web app in a real browser, the way a person uses it. New and changed tests must look like the existing ones: **steps**, **page objects**, and **components** for the smaller parts of a page. Read one or two nearby specs before writing anything; they are the style guide.

All commands run from `tests/e2e/` unless noted.

## Layout

| Path | What's there |
|---|---|
| `tests/smoke/` | Quick end-to-end paths through the main pages. |
| `tests/regression/` | One spec per page or flow (`library`, `rideDetail`, `import`...). |
| `tests/accessibility/pages.spec.ts` | axe WCAG 2.2 AA scans of every page, in light and dark mode. Add a step here when you add a page. |
| `pageObjects/*Page.ts` | One class per page, named `<Name>Page` in `<name>Page.ts` (`RidePage` in `ridePage.ts`). |
| `pageObjects/components/` | Parts used on more than one page (`Header`, `Stats`). No `Page` suffix. |
| `libs/constants.ts` | `RIDES` (the fixture rides, with who uses them) and `UPLOADS` (fixture files that are never in the library). |
| `libs/testData.ts` | `TestData`: ride ids and set-up shortcuts through the `/e2e/...` routes. |

The app side: React pages in `web/src/pages/`, components in `web/src/components/`; e2e-only routes in `src/fitlib/api/routers/e2e.py`; the fixture rides are generated from `tests/fixtures/specs.py`.

## Writing or changing a test

1. **Read the feature first.** Open the page and components under test so locators match the real markup and wording. Read the closest existing spec and its page objects.
2. **Pick the data.** Rides are the fixture rides in `RIDES`; check `usedBy` and `changes`.
   - Reading a ride can be shared. **If the test changes a ride** (edits it, deletes it, re-imports it), claim one nobody else changes: add your spec to its `usedBy`, set `changes: true`, and write a one-line comment saying what happens to it.
   - Ride ids are random each time the server starts. Get them by file name: `await new TestData(request).rideId(RIDES.ZWIFT.file)`.
   - **Counts and paging** must leave out rides that other specs change, because specs run in parallel. Narrow with a date filter (see `SINCE_10_AUG` in `library.spec.ts`).
3. **Add or extend page objects** before writing the spec. A spec should not contain raw locators except for a one-off check built from page object pieces.
4. **Write the spec** with `test.step`s (template in [reference.md](reference.md)).
5. **Run the checks** in "Verify" below.
6. **Update the docs** if you added a spec or changed what's covered: "What's tested" in the README, and the shortcut list there if you added a `TestData` method.

## Rules for specs

- **Steps:** every test body is a sequence of `await test.step('Plain sentence', async () => { ... })`. Name steps after what a person does or sees: `'Switch to metric'`, `'Still metric after a reload, and in the library'`. Set-up is its own first step (`'Start without the 9 Aug ride'`).
- **Test names** describe behaviour: `'a ride without power leaves out power figures'`.
- **Page objects at the top** of the test: `const library = new LibraryPage(page)`, `const ride = new RidePage(page)`. Variables drop the `Page` suffix, except `importPage` (`import` is a keyword).
- **Constants at the top of the file** with a comment on how the data is used: `// Read-only: ...` or `// Deleted, then imported again ...`.
- **Assertions** use web-first `expect(locator).toHaveText/toBeVisible/toHaveCount/...`. Never `waitForTimeout`, never `isVisible()` inside an `expect(true)`.
- **Messages on unclear assertions:** if it isn't obvious from the line what is being checked or why, add a `message` saying what is expected, as a "should" sentence:
  ```ts
  await expect(ride.hrZones, {
    message: 'Heart-rate zones need a max heart rate, which is not set',
  }).toBeHidden()
  ```
  Skip it when the line already says it, e.g. `expect(ride.heading).toHaveText(RIDE.name)`. Typical cases that need one: `toBeHidden`/`not.` checks, `toHaveCount(0)`, `toBeDisabled()`, and `toBeVisible()` on a locator whose name doesn't say why it matters.
- **Wait for the result before moving on.** After an action that loads data (a filter, an import), assert the new rows, count or summary before the next action.
- **Set-up:** use `TestData` to reach a known start. Anything the test is *about* must go through the UI. Each `TestData` shortcut must also be done through the UI in at least one test. The exception is `deleteRide`, until the app can delete rides.
- **Re-runnable:** a test must pass when run twice against the same server without re-importing. Reset what it changes at the start, not only at the end (`import.spec.ts` deletes its ride first if it's there).
- **Browser state:** each test gets a fresh browser context, so the units choice (kept in localStorage) starts from the config's imperial every time.
- **Comments** are short and say *why*: what the data is for, why a wait is needed, what markup a locator relies on.

## Rules for page objects and components

- **Class shape:** `readonly` `Locator` fields assigned in the constructor, a `goto()` for pages with a URL, methods for parameterised locators (`row(name)`, `zone(table, 'Z2')`, `effort('20 min')`) and for multi-step actions used by several tests (`searchFor`, `importFixtures`). Template in [reference.md](reference.md).
- **One class per page.** A part used on more than one page, or big enough to stand alone, becomes a component class in `components/`, exposed as a field: `ride.header.metric`, `ride.summary.value('Distance')`.
- **Scope locators** to a `root` or landmark when the page has several similar areas (`this.filters.getByLabel('Source')`, `this.nav.getByRole('link', ...)`).
- **A comment on the class** says which page or URL it covers and anything unusual (sections that only appear with some data). Comment fields whose text varies.
- **Only page-level actions belong in page objects.** Assertions about what a test expects stay in the spec.

## Finding elements (in this order)

1. **`getByRole`** with the accessible name, `exact: true` when the name could match more. Tables are named by their `<caption>` (`getByRole('table', { name: 'Power zones' })`); row headers (`<th scope="row">`) name rows.
2. **`getByLabel`** for form fields, **`getByPlaceholder`** only when there's no label.
3. **`getByText`** for fixed messages.
4. **`getByTestId`** when none of the above fits (a row, a card, a count, a chart). Add `data-testid="..."` in the React component. Kebab-case, named after what it *is*: `ride-row`, `ride-count`, `trace-chart`, `import-summary`. Repeated items share one id and are narrowed with `.filter({ has: ... })`.
5. **Never CSS classes or page structure** (`.stat`, `tbody tr`, `td.first()`). `npm run lint` rejects class selectors in `.locator(...)`.

If an element has no good accessible name, fix the component (a label, an `aria-label`, a caption) rather than adding a test id; that helps real users too.

**Charts** are canvases. Check that they're drawn and what their `aria-label` says; check the numbers through the tables next to them (zones, best efforts, laps).

## Verify

```bash
cd tests/e2e
npm run lint && npm run typecheck && npm run format:check   # npm run format fixes formatting
npx playwright test tests/regression/<spec>.spec.ts          # the spec you touched
npx playwright test tests/regression/<spec>.spec.ts --repeat-each=3   # catches re-run and timing problems
npm test                                                      # the whole suite before finishing
```

Playwright starts `scripts/e2e-server` itself (a fresh temp library with the fixtures, port 3200), or reuses one already running locally **without re-importing**. The server rebuilds `web/` when its sources are newer than the build, but only when it starts: if you changed web code, Python code or fixtures, stop the old server first. If you changed Python code, run `uv run pytest` from the repo root; if you changed web code, `npm test` and `npm run lint` in `web/`.

**Stop the server when done**, by port:

```bash
lsof -ti tcp:3200 | xargs kill; sleep 1; lsof -ti tcp:3200 || echo "port 3200 free"
```

## Debugging a failure

Work out *which* kind of failure it is before changing anything. Don't "fix" a test by loosening its assertion or adding a timeout without knowing the cause.

1. **Reproduce on its own:** `npx playwright test tests/regression/<spec>.spec.ts -g "<test name>"`. Add `--headed` to watch, `--debug` to step through, or `npm run test:ui`.
2. **Read the evidence:** `npm run report` opens the HTML report with the failing step, screenshot, video and trace. `test-results/<folder>/error-context.md` has the page's accessibility tree at the failure, which usually shows what was really on screen. In CI, download the `playwright-report` artifact from the failed run.
3. **Match the symptom:**

| Symptom | Likely cause | Fix |
|---|---|---|
| Locator not found / times out; the screenshot shows different text | The component's wording or markup changed | Update the page object (one place), not each spec |
| Strict mode violation: "resolved to 2 elements" | The locator matches more than intended | Scope it to a root or landmark, add `exact: true`, or filter |
| A count or page is off by one, only in the full run | It includes a ride another spec deletes or re-imports | Narrow with a date filter that leaves the claimed ride out |
| Passes first run, fails the second | The test doesn't reset what it changes | Reset in the first step |
| An old filter or value comes back after quick changes | The app built a change on stale state | Fix the app; the test found a real bug |
| Fails only in CI | One worker and retries in CI (`CI=1`), slower machine, fresh server every run | Run locally with `CI=1 npx playwright test ...` on a fresh server; look for a missing wait |
| The page shows old behaviour after a web change | A running server serves the old build | Stop the server; the next run rebuilds `web/` |
| 404 from `TestData` ("Is the server running in e2e mode?") | A server started some other way is on port 3200 | Stop it; let Playwright start `scripts/e2e-server` |
| `UnsafeLibrary` when the server starts | e2e mode was pointed at a library outside the temp folder | Use `scripts/e2e-server`, which makes a temp library |
| axe failure | The page broke an accessibility rule; the message names the rule and element | Fix the component, not the test |

4. **Decide whether the test or the app is wrong.** If the app misbehaves, say so and fix the app (or report it) rather than changing the test to match the bug.
5. **After the fix,** rerun the spec with `--repeat-each=3`, then the full suite, then stop the server.

## Before you finish

- [ ] Steps in every test; page objects and components hold the locators.
- [ ] Assertions that aren't obvious have a "should" `message`.
- [ ] New locators follow the order above; any new `data-testid` is in the component.
- [ ] Rides claimed in `libs/constants.ts` if the test changes them; counts leave out claimed rides.
- [ ] Lint, typecheck, format check and the touched specs pass, twice in a row.
- [ ] README "What's tested" updated if coverage changed.
- [ ] Port 3200 is free.
