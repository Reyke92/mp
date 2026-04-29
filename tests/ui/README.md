# Manual Playwright UI tests

This folder contains the browser-driven UI verification runner for the Marketplace Website UI test cases **TC-UI-001 through TC-UI-008** from the Software Testing Document.

These are manual/non-functional UI checks executed through Playwright with Chromium. They inspect real rendered pages for layout consistency, labels, visible actions, keyboard focus behavior, accessibility-oriented structure, and Bootstrap-based component consistency.

## Install Playwright

```bash
pip install playwright
python -m playwright install chromium
```

## Start the local website

In another terminal, start the Django development server against your local database:

```bash
python manage.py runserver
```

## Configure the tests

The runner will automatically look for configuration in this order:

1. `tests/ui/playwright_ui_config.local.json`
2. `tests/performance/playwright_performance_config.local.json`
3. `tests/ui/playwright_ui_config.example.json`
4. `tests/performance/playwright_performance_config.example.json`

The easiest option is to reuse the existing local performance config if it already contains working users, IDs, and paths. To make a UI-specific copy instead:

```bash
copy tests\ui\playwright_ui_config.example.json tests\ui\playwright_ui_config.local.json
```

Then update the local file with real test-only account credentials and record IDs. Do not commit local credential files.

## Run all UI tests

```bash
python tests/ui/playwright_manual_ui.py
```

The browser is visible by default so the manual UI behavior can be observed. Use `--headless` for headless execution:

```bash
python tests/ui/playwright_manual_ui.py --headless
```

## Run one UI test case

```bash
python tests/ui/playwright_manual_ui.py --only TC-UI-003
```

## Output

Results are written to `ui_results/` as JSON, CSV, and Markdown. The runner returns:

- `0` when all selected UI checks pass
- `1` when one or more checks fail
- `2` when one or more checks are blocked by missing local preconditions, such as credentials or missing records
