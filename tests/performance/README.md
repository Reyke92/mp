# Manual Playwright Performance Tests

This folder contains the manual browser-driven performance timing runner for the Marketplace Website performance cases **TC-PERF-001 through TC-PERF-009**.

The Testing Document defines these performance checks as separate from the main pytest/Django automated suites. They are intended to be run manually against a local development server with representative data using **Playwright for Python** and **Chromium**.

## Covered test cases

| Test case | Coverage |
| --- | --- |
| TC-PERF-001 | Standard page loads: homepage, category/search results, listing detail, inbox, moderation queue |
| TC-PERF-002 | Search and filtering first-page response time |
| TC-PERF-003 | Listing create/edit submit response time |
| TC-PERF-004 | Message submit response time |
| TC-PERF-005 | Listing and conversation report submit response time |
| TC-PERF-006 | Moderation queue load time |
| TC-PERF-007 | Report-detail review page load time |
| TC-PERF-008 | Administrator dashboard, user management, and listing management page loads |
| TC-PERF-009 | Search/browse pagination timing and inspection |

## Install Playwright

```bash
pip install -r requirements.txt
python -m playwright install chromium
```

## Prepare the local site

Start the Django development server in a separate terminal:

```bash
python manage.py runserver
```

Use a representative performance-test database. The state-changing cases create listings, messages, and reports, so run them against disposable or intentionally prepared data.

## Configure the run

Copy the example configuration and replace the placeholder users, IDs, and form values with records that exist in the local database:

```bash
cp tests/performance/playwright_performance_config.example.json tests/performance/playwright_performance_config.local.json
```

By default, authenticated browser contexts are created by posting the real `/login/` form through Playwright’s shared browser request context. This avoids direct Django/MySQL imports, avoids a fragile visible-click login setup step, and keeps authentication setup outside the measured timings. To force visible browser-form login instead, add `--auth-strategy ui-login`. To create sessions by importing Django and querying the local database, add `--auth-strategy django-session`. To try form-post login, visible UI login, and then Django session auth, add `--auth-strategy auto`.

The runner also accepts credential overrides through environment variables, for example:

```bash
MP_PERF_ADMIN_EMAIL=admin@example.com
MP_PERF_ADMIN_PASSWORD=password123
MP_PERF_MODERATOR_EMAIL=moderator@example.com
MP_PERF_MODERATOR_PASSWORD=password123
MP_PERF_SELLER_EMAIL=seller@example.com
MP_PERF_SELLER_PASSWORD=password123
MP_PERF_BUYER_EMAIL=buyer@example.com
MP_PERF_BUYER_PASSWORD=password123
MP_PERF_REPORTER_EMAIL=reporter@example.com
MP_PERF_REPORTER_PASSWORD=password123
```

## Run read-only page/search/moderation/admin timing checks

```bash
python tests/performance/playwright_manual_performance.py --config tests/performance/playwright_performance_config.local.json
```

By default, the runner skips state-changing workflows so it can be used safely for page-load and search timing.

## Run all performance checks, including state-changing workflows

Use `--headful` while validating the local configuration so you can see exactly which page Playwright is on. The write tests use the configured seller/report/message accounts and create real local listings, messages, and reports with `PERF TEST` prefixes.

```bash
python tests/performance/playwright_manual_performance.py --config tests/performance/playwright_performance_config.local.json --include-write-tests --headful
```

## Run one test case

```bash
python tests/performance/playwright_manual_performance.py --config tests/performance/playwright_performance_config.local.json --only TC-PERF-002
```

For the listing create/edit workflow only:

```bash
python tests/performance/playwright_manual_performance.py --config tests/performance/playwright_performance_config.local.json --include-write-tests --only TC-PERF-003 --headful
```

## Output

The runner writes JSON, CSV, and Markdown summaries to `performance_results/`. Each result includes the tested page/action, timing distribution, p95 value, worst-case value, threshold, browser mode, host platform, Python version, dataset description, and tested build commit where available.

## Measurement method

The runner follows the Testing Document method: 3 warm-up runs are discarded, then 10 measured runs are recorded by default. A target passes when its measured p95 meets the documented threshold. Standard page-load checks also enforce the documented 5-second p99/worst-case expectation.

## Troubleshooting BLOCKED results

`BLOCKED` means the timing target was not measured because the configured local instance did not meet the workflow preconditions. The result notes include the current URL, page title, first heading, and a body preview when a browser page was reached. For the default form-post login, a BLOCKED authentication note usually means the configured email/password was rejected, no `sessionid` cookie was created, the account is inactive, or the account lacks permission for the validation page. If `--auth-strategy django-session` is used, it can also mean the database is not reachable from the script.

The write-operation timers intentionally exclude manual data-entry time. For create/edit listing, message send, and report submit cases, Playwright first opens and fills the form, then starts the timer immediately before pressing the submit button.
