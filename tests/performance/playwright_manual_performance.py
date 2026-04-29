from __future__ import annotations

import argparse
import csv
import json
import math
import os
import platform
import re
import subprocess
import sys
import time
from dataclasses import dataclass, field
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Callable, Iterable
from urllib.parse import urljoin, urlparse

try:
    from playwright.sync_api import Browser, BrowserContext, Page, Playwright, TimeoutError as PlaywrightTimeoutError, sync_playwright
except ImportError:  # pragma: no cover - this script is intentionally optional/manual.
    Browser = Any  # type: ignore[misc,assignment]
    BrowserContext = Any  # type: ignore[misc,assignment]
    Page = Any  # type: ignore[misc,assignment]
    Playwright = Any  # type: ignore[misc,assignment]
    PlaywrightTimeoutError = TimeoutError  # type: ignore[assignment]
    sync_playwright = None  # type: ignore[assignment]


DEFAULT_WARMUP_RUNS: int = 3
DEFAULT_MEASURED_RUNS: int = 10
DEFAULT_TIMEOUT_MILLISECONDS: int = 15_000
DEFAULT_CONFIG_PATH: Path = Path(__file__).with_name("playwright_performance_config.example.json")
DEFAULT_RESULTS_DIR: Path = Path(__file__).resolve().parents[2] / "performance_results"

STANDARD_PAGE_THRESHOLD_SECONDS: float = 2.0
STANDARD_PAGE_P99_THRESHOLD_SECONDS: float = 5.0
SEARCH_THRESHOLD_SECONDS: float = 3.0
WRITE_OPERATION_THRESHOLD_SECONDS: float = 3.0
MODERATION_THRESHOLD_SECONDS: float = 2.0

Action = Callable[[int, bool], None]
PreparedAction = Callable[[int, bool], None]
SubmitAction = Callable[[int, bool], None]


class PerformancePreconditionError(RuntimeError):
    """Raised when the local dataset, credentials, URL, or page shape does not match a scenario."""


@dataclass(slots=True)
class TimingSummary:
    timings_seconds: list[float]
    average_seconds: float
    median_seconds: float
    p95_seconds: float
    p99_seconds: float
    worst_seconds: float


@dataclass(slots=True)
class ScenarioResult:
    test_case_id: str
    scenario_name: str
    target_name: str
    target: str
    threshold_seconds: float
    p99_threshold_seconds: float | None
    status: str
    passed: bool | None
    timings_seconds: list[float] = field(default_factory=list)
    average_seconds: float | None = None
    median_seconds: float | None = None
    p95_seconds: float | None = None
    p99_seconds: float | None = None
    worst_seconds: float | None = None
    notes: str = ""

    def as_dict(self) -> dict[str, Any]:
        return {
            "test_case_id": self.test_case_id,
            "scenario_name": self.scenario_name,
            "target_name": self.target_name,
            "target": self.target,
            "threshold_seconds": self.threshold_seconds,
            "p99_threshold_seconds": self.p99_threshold_seconds,
            "status": self.status,
            "passed": self.passed,
            "average_seconds": self.average_seconds,
            "median_seconds": self.median_seconds,
            "p95_seconds": self.p95_seconds,
            "p99_seconds": self.p99_seconds,
            "worst_seconds": self.worst_seconds,
            "timings_seconds": self.timings_seconds,
            "notes": self.notes,
        }


@dataclass(slots=True)
class LoggedInSession:
    role_name: str
    context: BrowserContext
    page: Page


class ManualPerformanceRunner:
    def __init__(
        self,
        *,
        playwright: Playwright,
        config: dict[str, Any],
        base_url: str,
        headless: bool,
        warmups: int,
        runs: int,
        timeout_milliseconds: int,
        include_write_tests: bool,
        only_test_case_ids: set[str],
        auth_strategy: str,
    ) -> None:
        self.playwright: Playwright = playwright
        self.config: dict[str, Any] = config
        self.base_url: str = _normalize_base_url(base_url)
        self.headless: bool = headless
        self.warmups: int = warmups
        self.runs: int = runs
        self.timeout_milliseconds: int = timeout_milliseconds
        self.include_write_tests: bool = include_write_tests
        self.only_test_case_ids: set[str] = only_test_case_ids
        self.auth_strategy: str = auth_strategy
        self.browser: Browser | None = None
        self.sessions: dict[str, LoggedInSession] = {}
        self.login_errors: dict[str, str] = {}
        self.results: list[ScenarioResult] = []

    def run(self) -> list[ScenarioResult]:
        self.browser = self.playwright.chromium.launch(headless=self.headless)
        try:
            self._run_tc_perf_001_standard_page_loads()
            self._run_tc_perf_002_search_and_filtering()
            self._run_tc_perf_003_listing_create_edit()
            self._run_tc_perf_004_message_submission()
            self._run_tc_perf_005_report_submission()
            self._run_tc_perf_006_moderation_queue()
            self._run_tc_perf_007_report_detail()
            self._run_tc_perf_008_admin_reporting_pages()
            self._run_tc_perf_009_pagination()
        finally:
            for session in self.sessions.values():
                try:
                    session.context.close()
                except Exception:  # noqa: BLE001 - do not mask the measured run results on shutdown.
                    pass
            if self.browser is not None:
                try:
                    self.browser.close()
                except Exception:  # noqa: BLE001
                    pass
        return self.results

    def _should_run(self, test_case_id: str) -> bool:
        return not self.only_test_case_ids or test_case_id in self.only_test_case_ids

    def _new_context(self) -> BrowserContext:
        if self.browser is None:
            raise RuntimeError("Browser was not initialized.")
        context: BrowserContext = self.browser.new_context(ignore_https_errors=True)
        context.set_default_timeout(self.timeout_milliseconds)
        context.set_default_navigation_timeout(self.timeout_milliseconds)
        return context

    def _session_for_role(self, role_name: str) -> LoggedInSession | None:
        role_name = str(role_name or "guest").strip().lower()
        if role_name in self.sessions:
            return self.sessions[role_name]

        if role_name == "guest":
            context: BrowserContext = self._new_context()
            page: Page = context.new_page()
            session = LoggedInSession(role_name=role_name, context=context, page=page)
            self.sessions[role_name] = session
            return session

        credentials: dict[str, str] | None = _get_credentials(self.config, role_name)
        if credentials is None and role_name == "staff":
            credentials = _get_credentials(self.config, "moderator") or _get_credentials(self.config, "admin")
        if credentials is None:
            return None

        context = self._new_context()
        page = context.new_page()
        try:
            if self.auth_strategy == "django-session":
                _install_django_session_cookie(
                    config=self.config,
                    context=context,
                    base_url=self.base_url,
                    credentials=credentials,
                    role_name=role_name,
                )
            elif self.auth_strategy == "ui-login":
                self._login(page=page, email=credentials["email"], password=credentials["password"], role_name=role_name)
            elif self.auth_strategy == "auto":
                try:
                    self._login_by_form_post(page=page, email=credentials["email"], password=credentials["password"], role_name=role_name)
                except Exception as form_post_exc:  # noqa: BLE001
                    try:
                        self._login(page=page, email=credentials["email"], password=credentials["password"], role_name=role_name)
                    except Exception as ui_login_exc:  # noqa: BLE001
                        self.login_errors[role_name] = (
                            f"Form-post login failed: {form_post_exc}; UI login failed: {ui_login_exc}; "
                            "falling back to Django session auth."
                        )
                        _install_django_session_cookie(
                            config=self.config,
                            context=context,
                            base_url=self.base_url,
                            credentials=credentials,
                            role_name=role_name,
                        )
            else:
                self._login_by_form_post(page=page, email=credentials["email"], password=credentials["password"], role_name=role_name)
        except Exception as exc:  # noqa: BLE001 - manual runner should record role setup failures and continue.
            try:
                context.close()
            except Exception:  # noqa: BLE001
                pass
            self.login_errors[role_name] = str(exc)
            return None

        session = LoggedInSession(role_name=role_name, context=context, page=page)
        self.sessions[role_name] = session
        return session

    def _session_for_first_role(self, role_names: list[str]) -> LoggedInSession | None:
        for role_name in role_names:
            session = self._session_for_role(role_name)
            if session is not None:
                return session
        return None

    def _login(self, *, page: Page, email: str, password: str, role_name: str) -> None:
        """Authenticate through the real login page.

        This is the most portable strategy for the manual performance runner because it uses
        the same local server, database connection, session middleware, and authentication
        view that browser users use. It avoids requiring the performance script process
        itself to import Django or connect to MySQL directly.
        """
        login_path = str(_config_value(self.config, "paths.login") or "/login/")
        login_url = _absolute_url(self.base_url, login_path)
        page.goto(login_url, wait_until="networkidle", timeout=self.timeout_milliseconds)

        email_field = page.locator('#id_email, input[name="email"]').first
        password_field = page.locator('#id_password, input[name="password"]').first
        try:
            email_field.wait_for(state="visible", timeout=self.timeout_milliseconds)
            password_field.wait_for(state="visible", timeout=self.timeout_milliseconds)
        except Exception as exc:  # noqa: BLE001
            raise PerformancePreconditionError(
                f"Login form was not visible for role '{role_name}'. {_diagnostic_context(page)}"
            ) from exc

        email_field.fill(email)
        password_field.fill(password)

        submit_locator = page.locator('#submit-id-submit, input[type="submit"][value="Log In"], button[type="submit"]').first
        try:
            submit_locator.wait_for(state="visible", timeout=self.timeout_milliseconds)
            with page.expect_navigation(wait_until="networkidle", timeout=self.timeout_milliseconds):
                submit_locator.click()
        except PlaywrightTimeoutError:
            # Some redirects can complete before Playwright arms the navigation watcher.
            # Let the page settle, then validate below.
            try:
                page.wait_for_load_state("networkidle", timeout=self.timeout_milliseconds)
            except Exception:  # noqa: BLE001
                pass
        except Exception as exc:  # noqa: BLE001
            raise PerformancePreconditionError(
                f"Could not submit the login form for role '{role_name}'. {_diagnostic_context(page)}"
            ) from exc

        try:
            page.wait_for_load_state("networkidle", timeout=self.timeout_milliseconds)
        except Exception:  # noqa: BLE001
            pass

        _assert_not_login_page(page=page, role_name=role_name)

    def _login_by_form_post(self, *, page: Page, email: str, password: str, role_name: str) -> None:
        """Authenticate by posting the real login form through Playwright's browser context.

        This keeps authentication setup out of the measured timings, avoids direct MySQL/Django
        imports, and avoids a flaky UI-click path. The API request context shares cookies with
        the browser context, so any session cookie set by Django is available to later page.goto()
        calls in the same Playwright context.
        """
        login_path = str(_config_value(self.config, "paths.login") or "/login/")
        login_url = _absolute_url(self.base_url, login_path)
        page.goto(login_url, wait_until="networkidle", timeout=self.timeout_milliseconds)

        try:
            csrf_token = page.locator('input[name="csrfmiddlewaretoken"]').first.input_value(timeout=self.timeout_milliseconds)
        except Exception as exc:  # noqa: BLE001
            raise PerformancePreconditionError(
                f"Could not read the CSRF token from the login form for role '{role_name}'. "
                f"{_diagnostic_context(page)}"
            ) from exc

        try:
            response = page.context.request.post(
                login_url,
                form={
                    "csrfmiddlewaretoken": csrf_token,
                    "email": email,
                    "password": password,
                    "submit": "Log In",
                },
                headers={"Referer": login_url},
                max_redirects=5,
                timeout=self.timeout_milliseconds,
            )
        except Exception as exc:  # noqa: BLE001
            raise PerformancePreconditionError(
                f"Could not post the login form for role '{role_name}'. {_diagnostic_context(page)}"
            ) from exc

        if not response.ok:
            raise PerformancePreconditionError(
                f"Login POST returned HTTP {response.status} for role '{role_name}'. {_diagnostic_context(page)}"
            )

        cookie_names = _cookie_names_for_context(page.context, self.base_url)
        if "sessionid" not in cookie_names:
            page.goto(login_url, wait_until="networkidle", timeout=self.timeout_milliseconds)
            error_text = _safe_inner_text(page, ".alert, .invalid-feedback, .text-danger, .errorlist, [role='alert']")
            extra = f" Login error text: {error_text!r}." if error_text else ""
            raise PerformancePreconditionError(
                f"Login did not create a sessionid cookie for role '{role_name}'. "
                f"Check the configured email/password and account status.{extra} "
                f"Cookies present: {cookie_names}. {_diagnostic_context(page)}"
            )

        validation_path = self._validation_path_for_role(role_name)
        validation_url = _absolute_url(self.base_url, validation_path)
        page.goto(validation_url, wait_until="networkidle", timeout=self.timeout_milliseconds)
        _assert_not_login_page(page=page, role_name=role_name)

    def _validation_path_for_role(self, role_name: str) -> str:
        role = str(role_name or "").strip().lower()
        if role == "seller":
            return str(_config_value(self.config, "paths.create_listing") or "/listings/create/")
        if role == "message_sender":
            conversation_id = _config_value(self.config, "ids.conversation_id") or 1
            return str(_config_value(self.config, "paths.conversation_detail") or f"/messaging/conversation/{conversation_id}/")
        if role == "reporter":
            listing_id = _config_value(self.config, "ids.reportable_listing_id") or _config_value(self.config, "ids.listing_id") or 1
            return str(_config_value(self.config, "paths.listing_report") or f"/report/?listing_id={listing_id}")
        if role == "conversation_reporter":
            conversation_id = _config_value(self.config, "ids.reportable_conversation_id") or _config_value(self.config, "ids.conversation_id") or 1
            return str(_config_value(self.config, "paths.conversation_report") or f"/report/?conversation_id={conversation_id}")
        if role in {"moderator", "staff"}:
            return str(_config_value(self.config, "paths.moderation_queue") or "/moderation/queue/")
        if role == "admin":
            admin_pages = _config_list(self.config, "admin_reporting_pages")
            if admin_pages and isinstance(admin_pages[0], dict):
                return str(admin_pages[0].get("path") or "/admin/dashboard/")
            return "/admin/dashboard/"
        if role == "buyer":
            return str(_config_value(self.config, "paths.messages_inbox") or "/messaging/inbox/")
        return "/"

    def _measure_page_load(
        self,
        *,
        test_case_id: str,
        scenario_name: str,
        target_name: str,
        path: str,
        role_name: str,
        threshold_seconds: float,
        p99_threshold_seconds: float | None,
        require_pagination: bool = False,
        required_selector: str | None = None,
    ) -> None:
        if not self._should_run(test_case_id):
            return

        session = self._session_for_role(role_name)
        if session is None:
            self.results.append(
                ScenarioResult(
                    test_case_id=test_case_id,
                    scenario_name=scenario_name,
                    target_name=target_name,
                    target=path,
                    threshold_seconds=threshold_seconds,
                    p99_threshold_seconds=p99_threshold_seconds,
                    status="SKIPPED",
                    passed=None,
                    notes=self.login_errors.get(role_name, f"Missing credentials for role '{role_name}'."),
                )
            )
            return

        url = _absolute_url(self.base_url, path)

        def action(_iteration: int, _is_warmup: bool) -> None:
            response = session.page.goto(url, wait_until="networkidle", timeout=self.timeout_milliseconds)
            status = response.status if response is not None else 0
            if status >= 400:
                raise RuntimeError(f"HTTP {status} while loading {url}. {_diagnostic_context(session.page)}")
            if role_name.strip().lower() != "guest":
                _assert_not_login_page(page=session.page, role_name=role_name)
            if required_selector:
                _require_visible(page=session.page, selector=required_selector, description=f"required selector for {target_name}")
            if require_pagination and not _page_has_pagination(session.page):
                raise PerformancePreconditionError(
                    "Pagination controls were not detected. Confirm the dataset is large enough "
                    f"to satisfy TC-PERF-009 preconditions. {_diagnostic_context(session.page)}"
                )

        self._measure_action(
            test_case_id=test_case_id,
            scenario_name=scenario_name,
            target_name=target_name,
            target=path,
            threshold_seconds=threshold_seconds,
            p99_threshold_seconds=p99_threshold_seconds,
            action=action,
        )

    def _measure_action(
        self,
        *,
        test_case_id: str,
        scenario_name: str,
        target_name: str,
        target: str,
        threshold_seconds: float,
        p99_threshold_seconds: float | None,
        action: Action,
    ) -> None:
        try:
            for iteration in range(1, self.warmups + 1):
                action(iteration, True)

            timings: list[float] = []
            for iteration in range(1, self.runs + 1):
                start_time = time.perf_counter()
                action(iteration, False)
                timings.append(time.perf_counter() - start_time)

            self._append_timing_summary(
                test_case_id=test_case_id,
                scenario_name=scenario_name,
                target_name=target_name,
                target=target,
                threshold_seconds=threshold_seconds,
                p99_threshold_seconds=p99_threshold_seconds,
                timings=timings,
            )
        except Exception as exc:  # noqa: BLE001 - manual runner should record failures and continue.
            self._append_exception_result(
                test_case_id=test_case_id,
                scenario_name=scenario_name,
                target_name=target_name,
                target=target,
                threshold_seconds=threshold_seconds,
                p99_threshold_seconds=p99_threshold_seconds,
                exc=exc,
            )

    def _measure_prepared_submit(
        self,
        *,
        test_case_id: str,
        scenario_name: str,
        target_name: str,
        target: str,
        threshold_seconds: float,
        p99_threshold_seconds: float | None,
        prepare: PreparedAction,
        submit: SubmitAction,
    ) -> None:
        """Measure submit/response time while excluding navigation to the form and data entry time."""
        try:
            for iteration in range(1, self.warmups + 1):
                prepare(iteration, True)
                submit(iteration, True)

            timings: list[float] = []
            for iteration in range(1, self.runs + 1):
                prepare(iteration, False)
                start_time = time.perf_counter()
                submit(iteration, False)
                timings.append(time.perf_counter() - start_time)

            self._append_timing_summary(
                test_case_id=test_case_id,
                scenario_name=scenario_name,
                target_name=target_name,
                target=target,
                threshold_seconds=threshold_seconds,
                p99_threshold_seconds=p99_threshold_seconds,
                timings=timings,
            )
        except Exception as exc:  # noqa: BLE001
            self._append_exception_result(
                test_case_id=test_case_id,
                scenario_name=scenario_name,
                target_name=target_name,
                target=target,
                threshold_seconds=threshold_seconds,
                p99_threshold_seconds=p99_threshold_seconds,
                exc=exc,
            )

    def _append_timing_summary(
        self,
        *,
        test_case_id: str,
        scenario_name: str,
        target_name: str,
        target: str,
        threshold_seconds: float,
        p99_threshold_seconds: float | None,
        timings: list[float],
    ) -> None:
        summary = _summarize_timings(timings)
        passed = bool(summary.p95_seconds <= threshold_seconds)
        if p99_threshold_seconds is not None:
            passed = bool(passed and summary.p99_seconds <= p99_threshold_seconds)

        self.results.append(
            ScenarioResult(
                test_case_id=test_case_id,
                scenario_name=scenario_name,
                target_name=target_name,
                target=target,
                threshold_seconds=threshold_seconds,
                p99_threshold_seconds=p99_threshold_seconds,
                status="PASS" if passed else "FAIL",
                passed=passed,
                timings_seconds=[round(value, 6) for value in summary.timings_seconds],
                average_seconds=round(summary.average_seconds, 6),
                median_seconds=round(summary.median_seconds, 6),
                p95_seconds=round(summary.p95_seconds, 6),
                p99_seconds=round(summary.p99_seconds, 6),
                worst_seconds=round(summary.worst_seconds, 6),
            )
        )

    def _append_exception_result(
        self,
        *,
        test_case_id: str,
        scenario_name: str,
        target_name: str,
        target: str,
        threshold_seconds: float,
        p99_threshold_seconds: float | None,
        exc: Exception,
    ) -> None:
        status = "BLOCKED" if isinstance(exc, PerformancePreconditionError) else "ERROR"
        self.results.append(
            ScenarioResult(
                test_case_id=test_case_id,
                scenario_name=scenario_name,
                target_name=target_name,
                target=target,
                threshold_seconds=threshold_seconds,
                p99_threshold_seconds=p99_threshold_seconds,
                status=status,
                passed=False if status == "ERROR" else None,
                notes=str(exc),
            )
        )

    def _run_tc_perf_001_standard_page_loads(self) -> None:
        test_case_id = "TC-PERF-001"
        if not self._should_run(test_case_id):
            return

        targets = _config_list(self.config, "standard_page_loads")
        if not targets:
            targets = _default_standard_page_loads(self.config)

        for target in targets:
            self._measure_page_load(
                test_case_id=test_case_id,
                scenario_name="Standard page loads",
                target_name=str(target.get("name", "standard_page")),
                path=str(target.get("path", "/")),
                role_name=str(target.get("role", "guest")),
                threshold_seconds=STANDARD_PAGE_THRESHOLD_SECONDS,
                p99_threshold_seconds=STANDARD_PAGE_P99_THRESHOLD_SECONDS,
                required_selector=_optional_string(target.get("required_selector")),
            )

    def _run_tc_perf_002_search_and_filtering(self) -> None:
        test_case_id = "TC-PERF-002"
        if not self._should_run(test_case_id):
            return

        targets = _config_list(self.config, "search_requests")
        if not targets:
            targets = _default_search_requests(self.config)

        for target in targets:
            self._measure_page_load(
                test_case_id=test_case_id,
                scenario_name="Search and filtering",
                target_name=str(target.get("name", "search_request")),
                path=str(target.get("path", "/search/")),
                role_name=str(target.get("role", "guest")),
                threshold_seconds=SEARCH_THRESHOLD_SECONDS,
                p99_threshold_seconds=None,
                required_selector=_optional_string(target.get("required_selector")),
            )

    def _run_tc_perf_003_listing_create_edit(self) -> None:
        test_case_id = "TC-PERF-003"
        if not self._should_run(test_case_id):
            return
        if not self.include_write_tests:
            self._append_write_skip(test_case_id, "Listing create/edit", "Create and edit form submissions")
            return

        seller_session = self._session_for_role("seller")
        if seller_session is None:
            self._append_skip(test_case_id, "Listing create/edit", "seller", self.login_errors.get("seller", "Missing seller credentials."))
            return

        create_form_values = _form_values(self.config, "create_listing")
        if create_form_values:
            self._measure_listing_create(session=seller_session, form_values=create_form_values)
        else:
            self._append_skip(test_case_id, "Listing create/edit", "/listings/create/", "Missing form_values.create_listing in config.")

        edit_listing_id = _config_value(self.config, "ids.edit_listing_id") or _config_value(self.config, "ids.listing_id")
        edit_form_values = _form_values(self.config, "edit_listing") or create_form_values
        if edit_listing_id and edit_form_values:
            self._measure_listing_edit(session=seller_session, listing_id=str(edit_listing_id), form_values=edit_form_values)
        else:
            self._append_skip(test_case_id, "Listing create/edit", "/listings/<id>/edit/", "Missing ids.edit_listing_id or form values.")

    def _measure_listing_create(self, *, session: LoggedInSession, form_values: dict[str, Any]) -> None:
        path = str(_config_value(self.config, "paths.create_listing") or "/listings/create/")
        submitted_title = ""

        def prepare(iteration: int, is_warmup: bool) -> None:
            nonlocal submitted_title
            session.page.goto(_absolute_url(self.base_url, path), wait_until="networkidle", timeout=self.timeout_milliseconds)
            _assert_not_login_page(page=session.page, role_name=session.role_name)
            _require_listing_editor(page=session.page)
            values = dict(form_values)
            submitted_title = f"{values.get('title', 'PERF TEST Listing')} {'warmup' if is_warmup else 'run'} {iteration} {int(time.time())}"
            values["title"] = submitted_title
            _fill_listing_form(page=session.page, values=values)

        def submit(_iteration: int, _is_warmup: bool) -> None:
            _click_submit_and_wait(page=session.page, name_pattern=re.compile(r"save\s+listing", re.IGNORECASE), timeout_milliseconds=self.timeout_milliseconds)
            _assert_not_login_page(page=session.page, role_name=session.role_name)
            if _is_current_path(session.page, path) or session.page.locator("form#listing-editor-form").count() > 0:
                raise PerformancePreconditionError(
                    "Create listing did not redirect away from the editor. The form likely failed validation. "
                    f"Submitted title: {submitted_title}. {_diagnostic_context(session.page)}"
                )

        self._measure_prepared_submit(
            test_case_id="TC-PERF-003",
            scenario_name="Listing create/edit",
            target_name="create_listing_submit",
            target=path,
            threshold_seconds=WRITE_OPERATION_THRESHOLD_SECONDS,
            p99_threshold_seconds=None,
            prepare=prepare,
            submit=submit,
        )

    def _measure_listing_edit(self, *, session: LoggedInSession, listing_id: str, form_values: dict[str, Any]) -> None:
        path = str(_config_value(self.config, "paths.edit_listing") or f"/listings/{listing_id}/edit/")
        submitted_title = ""

        def prepare(iteration: int, is_warmup: bool) -> None:
            nonlocal submitted_title
            session.page.goto(_absolute_url(self.base_url, path), wait_until="networkidle", timeout=self.timeout_milliseconds)
            _assert_not_login_page(page=session.page, role_name=session.role_name)
            _require_listing_editor(page=session.page)
            values = dict(form_values)
            submitted_title = f"{values.get('title', 'PERF TEST Edited Listing')} {'warmup' if is_warmup else 'run'} {iteration} {int(time.time())}"
            values["title"] = submitted_title
            _fill_listing_form(page=session.page, values=values)

        def submit(_iteration: int, _is_warmup: bool) -> None:
            _click_submit_and_wait(page=session.page, name_pattern=re.compile(r"save\s+changes", re.IGNORECASE), timeout_milliseconds=self.timeout_milliseconds)
            _assert_not_login_page(page=session.page, role_name=session.role_name)
            if _is_current_path(session.page, path) or session.page.locator("form#listing-editor-form").count() > 0:
                raise PerformancePreconditionError(
                    "Edit listing did not redirect away from the editor. The form likely failed validation. "
                    f"Submitted title: {submitted_title}. {_diagnostic_context(session.page)}"
                )

        self._measure_prepared_submit(
            test_case_id="TC-PERF-003",
            scenario_name="Listing create/edit",
            target_name="edit_listing_submit",
            target=path,
            threshold_seconds=WRITE_OPERATION_THRESHOLD_SECONDS,
            p99_threshold_seconds=None,
            prepare=prepare,
            submit=submit,
        )

    def _run_tc_perf_004_message_submission(self) -> None:
        test_case_id = "TC-PERF-004"
        if not self._should_run(test_case_id):
            return
        if not self.include_write_tests:
            self._append_write_skip(test_case_id, "Message submission", "Conversation message submit")
            return

        session = self._session_for_first_role(["message_sender", "buyer", "admin", "seller"])
        conversation_id = _config_value(self.config, "ids.conversation_id")
        if session is None or not conversation_id:
            notes = self.login_errors.get("message_sender") or self.login_errors.get("buyer") or self.login_errors.get("admin") or self.login_errors.get("seller") or "Missing message_sender/buyer/admin/seller credentials or ids.conversation_id."
            self._append_skip(test_case_id, "Message submission", "/messaging/conversation/<id>/", notes)
            return

        path = str(_config_value(self.config, "paths.conversation_detail") or f"/messaging/conversation/{conversation_id}/")
        submitted_text = ""

        def prepare(iteration: int, is_warmup: bool) -> None:
            nonlocal submitted_text
            session.page.goto(_absolute_url(self.base_url, path), wait_until="networkidle", timeout=self.timeout_milliseconds)
            _assert_not_login_page(page=session.page, role_name=session.role_name)
            _require_visible(page=session.page, selector='input[name="message_text"]', description="message text field")
            submitted_text = f"PERF TEST {'warmup' if is_warmup else 'run'} message {iteration} at {int(time.time())}"
            session.page.locator('input[name="message_text"]').fill(submitted_text)

        def submit(_iteration: int, _is_warmup: bool) -> None:
            _click_submit_and_wait(page=session.page, name_pattern=re.compile(r"send", re.IGNORECASE), timeout_milliseconds=self.timeout_milliseconds)
            _assert_not_login_page(page=session.page, role_name=session.role_name)
            body_text = _safe_inner_text(session.page, "body")
            if submitted_text not in body_text:
                raise PerformancePreconditionError(
                    "Message submission did not render the submitted message after redirect. "
                    f"Submitted text: {submitted_text}. {_diagnostic_context(session.page)}"
                )

        self._measure_prepared_submit(
            test_case_id=test_case_id,
            scenario_name="Message submission",
            target_name="send_message_submit",
            target=path,
            threshold_seconds=WRITE_OPERATION_THRESHOLD_SECONDS,
            p99_threshold_seconds=None,
            prepare=prepare,
            submit=submit,
        )

    def _run_tc_perf_005_report_submission(self) -> None:
        test_case_id = "TC-PERF-005"
        if not self._should_run(test_case_id):
            return
        if not self.include_write_tests:
            self._append_write_skip(test_case_id, "Report submission", "Listing/conversation report submit")
            return

        listing_reporter = self._session_for_first_role(["listing_reporter", "reporter", "buyer", "admin"])
        conversation_reporter = self._session_for_first_role(["conversation_reporter", "reporter", "buyer", "admin"])
        listing_id = _config_value(self.config, "ids.reportable_listing_id") or _config_value(self.config, "ids.listing_id")
        conversation_id = _config_value(self.config, "ids.reportable_conversation_id") or _config_value(self.config, "ids.conversation_id")

        if listing_id and listing_reporter is not None:
            path = str(_config_value(self.config, "paths.listing_report") or f"/report/?listing_id={listing_id}")
            self._measure_report_submission(
                session=listing_reporter,
                target_name="listing_report_submit",
                path=path,
                base_reason="PERF TEST listing report",
            )
        else:
            notes = self.login_errors.get("listing_reporter") or self.login_errors.get("reporter") or self.login_errors.get("buyer") or self.login_errors.get("admin") or "Missing listing reporter credentials or ids.reportable_listing_id/ids.listing_id."
            self._append_skip(test_case_id, "Report submission", "listing report", notes)

        if conversation_id and conversation_reporter is not None:
            path = str(_config_value(self.config, "paths.conversation_report") or f"/report/?conversation_id={conversation_id}")
            self._measure_report_submission(
                session=conversation_reporter,
                target_name="conversation_report_submit",
                path=path,
                base_reason="PERF TEST conversation report",
            )
        else:
            notes = self.login_errors.get("conversation_reporter") or self.login_errors.get("reporter") or self.login_errors.get("buyer") or self.login_errors.get("admin") or "Missing conversation reporter credentials or ids.reportable_conversation_id/ids.conversation_id."
            self._append_skip(test_case_id, "Report submission", "conversation report", notes)

    def _measure_report_submission(self, *, session: LoggedInSession, target_name: str, path: str, base_reason: str) -> None:
        submitted_reason = ""

        def prepare(iteration: int, is_warmup: bool) -> None:
            nonlocal submitted_reason
            session.page.goto(_absolute_url(self.base_url, path), wait_until="networkidle", timeout=self.timeout_milliseconds)
            _assert_not_login_page(page=session.page, role_name=session.role_name)
            _require_visible(page=session.page, selector='textarea[name="reason"]', description="report reason field")
            submitted_reason = f"{base_reason} {'warmup' if is_warmup else 'run'} {iteration} at {int(time.time())}"
            session.page.locator('textarea[name="reason"]').fill(submitted_reason)

        def submit(_iteration: int, _is_warmup: bool) -> None:
            _click_submit_and_wait(page=session.page, name_pattern=re.compile(r"submit\s+report", re.IGNORECASE), timeout_milliseconds=self.timeout_milliseconds)
            _assert_not_login_page(page=session.page, role_name=session.role_name)
            if _path_starts_with(session.page, "/report/") or session.page.locator('textarea[name="reason"]').count() > 0:
                raise PerformancePreconditionError(
                    "Report submission did not redirect away from the report form. The report likely failed validation. "
                    f"Submitted reason: {submitted_reason}. {_diagnostic_context(session.page)}"
                )

        self._measure_prepared_submit(
            test_case_id="TC-PERF-005",
            scenario_name="Report submission",
            target_name=target_name,
            target=path,
            threshold_seconds=WRITE_OPERATION_THRESHOLD_SECONDS,
            p99_threshold_seconds=None,
            prepare=prepare,
            submit=submit,
        )

    def _run_tc_perf_006_moderation_queue(self) -> None:
        test_case_id = "TC-PERF-006"
        if not self._should_run(test_case_id):
            return
        self._measure_page_load(
            test_case_id=test_case_id,
            scenario_name="Moderation queue",
            target_name="moderation_queue",
            path=str(_config_value(self.config, "paths.moderation_queue") or "/moderation/queue/"),
            role_name="staff",
            threshold_seconds=MODERATION_THRESHOLD_SECONDS,
            p99_threshold_seconds=None,
        )

    def _run_tc_perf_007_report_detail(self) -> None:
        test_case_id = "TC-PERF-007"
        if not self._should_run(test_case_id):
            return

        report_ids = _config_list(self.config, "report_detail_ids")
        if not report_ids:
            report_id = _config_value(self.config, "ids.report_id")
            if report_id:
                report_ids = [report_id]

        if not report_ids:
            self._append_skip(test_case_id, "Report detail", "/moderation/reports/<id>/", "Missing report_detail_ids or ids.report_id.")
            return

        for report_id in report_ids:
            self._measure_page_load(
                test_case_id=test_case_id,
                scenario_name="Report detail",
                target_name=f"report_detail_{report_id}",
                path=f"/moderation/reports/{report_id}/",
                role_name="staff",
                threshold_seconds=MODERATION_THRESHOLD_SECONDS,
                p99_threshold_seconds=None,
            )

    def _run_tc_perf_008_admin_reporting_pages(self) -> None:
        test_case_id = "TC-PERF-008"
        if not self._should_run(test_case_id):
            return

        targets = _config_list(self.config, "admin_reporting_pages")
        if not targets:
            targets = [
                {"name": "admin_dashboard", "path": "/admin/dashboard/", "role": "admin"},
                {"name": "user_management", "path": "/admin/user_management/", "role": "admin"},
                {"name": "listing_management", "path": "/admin/listing_management/", "role": "admin"},
            ]

        for target in targets:
            self._measure_page_load(
                test_case_id=test_case_id,
                scenario_name="Administrator reporting and management pages",
                target_name=str(target.get("name", "admin_page")),
                path=str(target.get("path", "/admin/dashboard/")),
                role_name=str(target.get("role", "admin")),
                threshold_seconds=STANDARD_PAGE_THRESHOLD_SECONDS,
                p99_threshold_seconds=STANDARD_PAGE_P99_THRESHOLD_SECONDS,
                required_selector=_optional_string(target.get("required_selector")),
            )

    def _run_tc_perf_009_pagination(self) -> None:
        test_case_id = "TC-PERF-009"
        if not self._should_run(test_case_id):
            return

        targets = _config_list(self.config, "pagination_checks")
        if not targets:
            targets = [{"name": "broad_search_first_page", "path": str(_config_value(self.config, "broad_search_path") or "/search/?sort=newest"), "role": "guest"}]

        for target in targets:
            self._measure_page_load(
                test_case_id=test_case_id,
                scenario_name="Search pagination",
                target_name=str(target.get("name", "pagination_check")),
                path=str(target.get("path", "/search/?sort=newest")),
                role_name=str(target.get("role", "guest")),
                threshold_seconds=SEARCH_THRESHOLD_SECONDS,
                p99_threshold_seconds=None,
                require_pagination=True,
                required_selector=_optional_string(target.get("required_selector")),
            )

    def _append_write_skip(self, test_case_id: str, scenario_name: str, target_name: str) -> None:
        self.results.append(
            ScenarioResult(
                test_case_id=test_case_id,
                scenario_name=scenario_name,
                target_name=target_name,
                target="state-changing workflow",
                threshold_seconds=WRITE_OPERATION_THRESHOLD_SECONDS,
                p99_threshold_seconds=None,
                status="SKIPPED",
                passed=None,
                notes="State-changing performance workflow was skipped. Re-run with --include-write-tests to execute it against a disposable performance-test dataset.",
            )
        )

    def _append_skip(self, test_case_id: str, scenario_name: str, target: str, notes: str) -> None:
        self.results.append(
            ScenarioResult(
                test_case_id=test_case_id,
                scenario_name=scenario_name,
                target_name=target,
                target=target,
                threshold_seconds=_threshold_for_test_case(test_case_id),
                p99_threshold_seconds=_p99_threshold_for_test_case(test_case_id),
                status="SKIPPED",
                passed=None,
                notes=notes,
            )
        )


def _require_listing_editor(*, page: Page) -> None:
    _require_visible(page=page, selector="form#listing-editor-form", description="listing editor form")
    _require_visible(page=page, selector='input[name="title"]', description="listing title field")
    _require_visible(page=page, selector='input[name="price_amount"]', description="listing price field")
    _require_visible(page=page, selector='select[name="category"]', description="listing category field")
    _require_visible(page=page, selector='select[name="condition"]', description="listing condition field")
    _require_visible(page=page, selector='select[name="state"]', description="listing state field")
    _require_visible(page=page, selector='input[name="city_name"]', description="listing city field")
    _require_visible(page=page, selector='textarea[name="description"]', description="listing description field")


def _fill_listing_form(*, page: Page, values: dict[str, Any]) -> None:
    # Set category and state before city/attribute handling so Django/JS-dependent fields are in the expected state.
    ordered_fields: list[tuple[str, str, str]] = [
        ("category", 'select[name="category"]', "select"),
        ("condition", 'select[name="condition"]', "select"),
        ("state", 'select[name="state"]', "select"),
        ("title", 'input[name="title"]', "text"),
        ("price_amount", 'input[name="price_amount"]', "text"),
        ("city_name", 'input[name="city_name"]', "text"),
        ("description", 'textarea[name="description"]', "text"),
    ]

    for field_name, selector, kind in ordered_fields:
        if field_name not in values or values[field_name] is None:
            continue
        _require_visible(page=page, selector=selector, description=f"listing field '{field_name}'")
        try:
            if kind == "select":
                page.locator(selector).select_option(value=str(values[field_name]))
                if field_name in {"category", "state"}:
                    page.wait_for_timeout(150)
            else:
                page.locator(selector).fill(str(values[field_name]))
        except Exception as exc:  # noqa: BLE001
            raise PerformancePreconditionError(
                f"Could not fill listing field '{field_name}' with value '{values[field_name]}'. "
                f"{_diagnostic_context(page)}"
            ) from exc

    extra_fields = values.get("extra_fields") or {}
    if isinstance(extra_fields, dict):
        for field_name, field_value in extra_fields.items():
            if field_value is None:
                continue
            selector = f'[name="{field_name}"]'
            locator = page.locator(selector)
            if locator.count() == 0:
                continue
            tag_name = str(locator.first.evaluate("element => element.tagName.toLowerCase()"))
            input_type = str(locator.first.get_attribute("type") or "").lower()
            try:
                if tag_name == "select":
                    locator.first.select_option(value=str(field_value))
                elif input_type in {"radio", "checkbox"}:
                    page.locator(f'{selector}[value="{field_value}"]').check()
                else:
                    locator.first.fill(str(field_value))
            except Exception as exc:  # noqa: BLE001
                raise PerformancePreconditionError(
                    f"Could not fill extra listing field '{field_name}' with value '{field_value}'. "
                    f"{_diagnostic_context(page)}"
                ) from exc


def _require_visible(*, page: Page, selector: str, description: str) -> None:
    try:
        page.locator(selector).first.wait_for(state="visible", timeout=DEFAULT_TIMEOUT_MILLISECONDS)
    except Exception as exc:  # noqa: BLE001
        raise PerformancePreconditionError(f"Missing or hidden {description} ({selector}). {_diagnostic_context(page)}") from exc


def _click_submit_and_wait(*, page: Page, name_pattern: re.Pattern[str], timeout_milliseconds: int) -> None:
    def click() -> None:
        candidate = page.get_by_role("button", name=name_pattern)
        if candidate.count() > 0:
            candidate.first.click()
            return
        page.locator('button[type="submit"], input[type="submit"]').first.click()

    try:
        with page.expect_navigation(wait_until="networkidle", timeout=timeout_milliseconds):
            click()
    except PlaywrightTimeoutError:
        # Some submit actions can complete without Playwright seeing a top-level navigation event.
        # Give the page a chance to settle, then let the caller validate success from page state.
        try:
            page.wait_for_load_state("networkidle", timeout=timeout_milliseconds)
        except PlaywrightTimeoutError:
            pass


def _cookie_names_for_context(context: BrowserContext, base_url: str) -> list[str]:
    try:
        cookies = context.cookies([base_url])
    except Exception:  # noqa: BLE001
        try:
            cookies = context.cookies()
        except Exception:  # noqa: BLE001
            return []
    names: list[str] = []
    for cookie in cookies:
        name = str(cookie.get("name") or "")
        if name:
            names.append(name)
    return sorted(set(names))


def _assert_not_login_page(*, page: Page, role_name: str) -> None:
    role = role_name.strip().lower()
    if role == "guest":
        return
    current_path = urlparse(page.url).path.lower()
    has_visible_login_form = False
    try:
        has_visible_login_form = (
            page.locator('#id_email, input[name="email"]').first.is_visible(timeout=500)
            and page.locator('#id_password, input[name="password"]').first.is_visible(timeout=500)
        )
    except Exception:  # noqa: BLE001
        has_visible_login_form = False
    if "login" in current_path or has_visible_login_form:
        error_text = _safe_inner_text(page, ".alert, .invalid-feedback, .text-danger, .errorlist, [role='alert']")
        extra = f" Login error text: {error_text!r}." if error_text else ""
        raise PerformancePreconditionError(
            f"Role '{role_name}' appears to be unauthenticated or was redirected to the login page. "
            f"Check the configured email/password and account status.{extra} {_diagnostic_context(page)}"
        )


def _page_has_pagination(page: Page) -> bool:
    selectors = [
        ".pagination",
        'nav[aria-label*="pagination" i]',
        'a[href*="page="]',
        '[data-pagination]',
    ]
    return any(page.locator(selector).count() > 0 for selector in selectors)


def _diagnostic_context(page: Page) -> str:
    title = ""
    heading = ""
    body_preview = ""
    try:
        title = page.title()
    except Exception:  # noqa: BLE001
        pass
    try:
        heading_locator = page.locator("h1, h2").first
        if heading_locator.count() > 0:
            heading = heading_locator.inner_text(timeout=500).strip()
    except Exception:  # noqa: BLE001
        pass
    try:
        body_preview = _safe_inner_text(page, "body")[:500].replace("\n", " ").strip()
    except Exception:  # noqa: BLE001
        pass
    return f"Current URL: {page.url}; title: {title!r}; heading: {heading!r}; body preview: {body_preview!r}"


def _safe_inner_text(page: Page, selector: str) -> str:
    try:
        if page.locator(selector).count() == 0:
            return ""
        return page.locator(selector).inner_text(timeout=1_000)
    except Exception:  # noqa: BLE001
        return ""


def _is_current_path(page: Page, expected_path: str) -> bool:
    return urlparse(page.url).path.rstrip("/") == urlparse(expected_path).path.rstrip("/")


def _path_starts_with(page: Page, prefix: str) -> bool:
    return urlparse(page.url).path.lower().startswith(prefix.lower())


def _summarize_timings(timings: list[float]) -> TimingSummary:
    if not timings:
        raise ValueError("No timings were recorded.")
    sorted_values = sorted(timings)
    return TimingSummary(
        timings_seconds=timings,
        average_seconds=sum(timings) / len(timings),
        median_seconds=_median(sorted_values),
        p95_seconds=_percentile(sorted_values, 95),
        p99_seconds=_percentile(sorted_values, 99),
        worst_seconds=max(timings),
    )


def _median(sorted_values: list[float]) -> float:
    count = len(sorted_values)
    midpoint = count // 2
    if count % 2 == 1:
        return sorted_values[midpoint]
    return (sorted_values[midpoint - 1] + sorted_values[midpoint]) / 2


def _percentile(sorted_values: list[float], percentile: int) -> float:
    if not sorted_values:
        raise ValueError("Cannot compute a percentile for an empty list.")
    rank = math.ceil((percentile / 100) * len(sorted_values)) - 1
    rank = max(0, min(rank, len(sorted_values) - 1))
    return sorted_values[rank]


def _normalize_base_url(base_url: str) -> str:
    value = str(base_url or "http://127.0.0.1:8000").strip()
    return value if value.endswith("/") else f"{value}/"


def _absolute_url(base_url: str, path: str) -> str:
    return urljoin(base_url, str(path).lstrip("/"))


def _load_config(path: Path) -> dict[str, Any]:
    if not path.exists():
        return {}
    with path.open("r", encoding="utf-8") as file_obj:
        loaded = json.load(file_obj)
    if not isinstance(loaded, dict):
        raise ValueError("The performance config root must be a JSON object.")
    return loaded


def _config_value(config: dict[str, Any], dotted_path: str) -> Any:
    current: Any = config
    for part in dotted_path.split("."):
        if not isinstance(current, dict):
            return None
        current = current.get(part)
    return current


def _config_list(config: dict[str, Any], key: str) -> list[Any]:
    value = config.get(key)
    if value is None:
        return []
    if isinstance(value, list):
        return value
    raise ValueError(f"Config key '{key}' must be a list when provided.")


def _form_values(config: dict[str, Any], form_name: str) -> dict[str, Any]:
    value = _config_value(config, f"form_values.{form_name}")
    return dict(value) if isinstance(value, dict) else {}


def _get_credentials(config: dict[str, Any], role_name: str) -> dict[str, str] | None:
    role_key = str(role_name).strip().lower()
    env_prefix = f"MP_PERF_{role_key.upper()}"
    email = os.environ.get(f"{env_prefix}_EMAIL")
    password = os.environ.get(f"{env_prefix}_PASSWORD")
    if email and password:
        return {"email": email, "password": password}

    users = config.get("users", {})
    if not isinstance(users, dict):
        return None
    raw_credentials = users.get(role_key)
    if not isinstance(raw_credentials, dict):
        return None
    email = str(raw_credentials.get("email") or "").strip()
    password = str(raw_credentials.get("password") or "").strip()
    if not email or not password:
        return None
    return {"email": email, "password": password}



def _install_django_session_cookie(
    *,
    config: dict[str, Any],
    context: BrowserContext,
    base_url: str,
    credentials: dict[str, str],
    role_name: str,
) -> None:
    """
    Create a real Django authenticated session and place its session cookie in the
    Playwright browser context. This is more reliable for performance timing than
    submitting the login form, and it keeps authentication setup outside the
    measured page/action timing.
    """
    project_root = Path(__file__).resolve().parents[2]
    project_root_text = str(project_root)
    if project_root_text not in sys.path:
        sys.path.insert(0, project_root_text)

    os.environ.setdefault("DJANGO_SETTINGS_MODULE", str(config.get("django_settings_module") or "marketplace.settings"))

    try:
        import importlib
        import django
        from django.conf import settings
        from django.contrib.auth import BACKEND_SESSION_KEY, HASH_SESSION_KEY, SESSION_KEY, get_user_model
    except Exception as exc:  # noqa: BLE001
        raise PerformancePreconditionError(
            "Could not import Django for direct session authentication. "
            "Run this script from the project environment, or use --auth-strategy ui-login."
        ) from exc

    try:
        django.setup()
    except Exception as exc:  # noqa: BLE001
        raise PerformancePreconditionError(
            "Could not initialize Django for direct session authentication. "
            "Confirm DJANGO_SETTINGS_MODULE and the local database settings are valid, or use --auth-strategy ui-login."
        ) from exc

    user_model = get_user_model()
    login_identifier = str(credentials.get("email") or credentials.get("username") or "").strip()
    if not login_identifier:
        raise PerformancePreconditionError(f"No email/username was configured for role '{role_name}'.")

    try:
        user = user_model.objects.filter(email__iexact=login_identifier).first()
        if user is None:
            user = user_model.objects.filter(username__iexact=login_identifier).first()
    except Exception as exc:  # noqa: BLE001
        raise PerformancePreconditionError(
            f"Could not query the local Django database for role '{role_name}'. "
            "Confirm the database server is running and the settings point to your local instance."
        ) from exc

    if user is None:
        raise PerformancePreconditionError(
            f"No Django user exists for role '{role_name}' with email/username '{login_identifier}'."
        )
    if hasattr(user, "is_active") and not bool(user.is_active):
        raise PerformancePreconditionError(
            f"The Django user for role '{role_name}' exists but is inactive/banned: '{login_identifier}'."
        )

    try:
        session_engine = importlib.import_module(settings.SESSION_ENGINE)
        session = session_engine.SessionStore()
        session[SESSION_KEY] = str(user.pk)
        session[BACKEND_SESSION_KEY] = settings.AUTHENTICATION_BACKENDS[0]
        session[HASH_SESSION_KEY] = user.get_session_auth_hash()
        session.save()
    except Exception as exc:  # noqa: BLE001
        raise PerformancePreconditionError(
            f"Could not create a Django session for role '{role_name}' ({login_identifier})."
        ) from exc

    cookie_name = getattr(settings, "SESSION_COOKIE_NAME", "sessionid")
    same_site = str(getattr(settings, "SESSION_COOKIE_SAMESITE", "Lax") or "Lax")
    same_site_by_lower = {"strict": "Strict", "lax": "Lax", "none": "None"}
    same_site = same_site_by_lower.get(same_site.lower(), "Lax")

    parsed_base = urlparse(base_url)
    secure_cookie = bool(getattr(settings, "SESSION_COOKIE_SECURE", False)) and parsed_base.scheme == "https"
    try:
        context.add_cookies(
            [
                {
                    "name": cookie_name,
                    "value": str(session.session_key),
                    "url": base_url,
                    "path": str(getattr(settings, "SESSION_COOKIE_PATH", "/") or "/"),
                    "httpOnly": bool(getattr(settings, "SESSION_COOKIE_HTTPONLY", True)),
                    "secure": secure_cookie,
                    "sameSite": same_site,
                }
            ]
        )
    except Exception as exc:  # noqa: BLE001
        raise PerformancePreconditionError(
            f"Could not install Django session cookie for role '{role_name}' into Playwright."
        ) from exc


def _optional_string(value: Any) -> str | None:
    if value is None:
        return None
    text = str(value).strip()
    return text or None


def _default_standard_page_loads(config: dict[str, Any]) -> list[dict[str, str]]:
    targets: list[dict[str, str]] = [{"name": "homepage", "path": "/", "role": "guest"}]
    category_id = _config_value(config, "ids.category_id")
    listing_id = _config_value(config, "ids.listing_id")

    if category_id:
        targets.append({"name": "category_filtered_results", "path": f"/search/?category={category_id}&sort=newest", "role": "guest"})
    else:
        targets.append({"name": "search_results", "path": "/search/?sort=newest", "role": "guest"})
    if listing_id:
        targets.append({"name": "listing_detail", "path": f"/listings/{listing_id}/", "role": "guest"})
    targets.append({"name": "messages_inbox", "path": "/messaging/inbox/", "role": "buyer"})
    targets.append({"name": "moderation_queue", "path": "/moderation/queue/", "role": "staff"})
    return targets


def _default_search_requests(config: dict[str, Any]) -> list[dict[str, str]]:
    keyword = str(_config_value(config, "search.keyword") or "table")
    category_id = _config_value(config, "ids.category_id")
    condition_id = _config_value(config, "ids.condition_id")
    city_name = _config_value(config, "search.city_name")
    attribute_search_path = _config_value(config, "search.attribute_search_path")

    targets: list[dict[str, str]] = [
        {"name": "keyword_only", "path": f"/search/?q={keyword}&sort=most_relevant", "role": "guest"},
        {"name": "no_results", "path": "/search/?q=zzzz_no_results_perf_probe_999999&sort=most_relevant", "role": "guest"},
    ]

    mixed_filter_path = "/search/?sort=newest"
    if category_id:
        mixed_filter_path += f"&category={category_id}"
    if condition_id:
        mixed_filter_path += f"&condition={condition_id}"
    if city_name:
        mixed_filter_path += f"&q={city_name}"
    targets.insert(1, {"name": "mixed_filters", "path": mixed_filter_path, "role": "guest"})

    if attribute_search_path:
        targets.insert(2, {"name": "category_attribute_filters", "path": str(attribute_search_path), "role": "guest"})

    return targets


def _threshold_for_test_case(test_case_id: str) -> float:
    if test_case_id in {"TC-PERF-006", "TC-PERF-007"}:
        return MODERATION_THRESHOLD_SECONDS
    if test_case_id in {"TC-PERF-002", "TC-PERF-009"}:
        return SEARCH_THRESHOLD_SECONDS
    if test_case_id in {"TC-PERF-003", "TC-PERF-004", "TC-PERF-005"}:
        return WRITE_OPERATION_THRESHOLD_SECONDS
    return STANDARD_PAGE_THRESHOLD_SECONDS


def _p99_threshold_for_test_case(test_case_id: str) -> float | None:
    if test_case_id in {"TC-PERF-001", "TC-PERF-008"}:
        return STANDARD_PAGE_P99_THRESHOLD_SECONDS
    return None


def _git_commit_hash(project_root: Path) -> str:
    configured = os.environ.get("MP_PERF_BUILD_COMMIT", "").strip()
    if configured:
        return configured
    try:
        completed = subprocess.run(
            ["git", "rev-parse", "--short", "HEAD"],
            cwd=str(project_root),
            check=False,
            capture_output=True,
            text=True,
        )
    except OSError:
        return "unknown"
    value = completed.stdout.strip()
    return value if completed.returncode == 0 and value else "unknown"


def _build_environment_metadata(*, config: dict[str, Any], base_url: str, headless: bool, warmups: int, runs: int) -> dict[str, Any]:
    project_root = Path(__file__).resolve().parents[2]
    return {
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "base_url": base_url,
        "host_platform": platform.platform(),
        "python_version": sys.version.replace("\n", " "),
        "browser": "Chromium through Playwright for Python",
        "browser_mode": "headless" if headless else "visible/headful",
        "warmup_runs": warmups,
        "measured_runs": runs,
        "dataset_description": config.get("dataset_description", "Not recorded"),
        "dataset_size": config.get("dataset_size", "Not recorded"),
        "build_commit": str(config.get("build_commit") or _git_commit_hash(project_root)),
    }


def _write_results(*, output_dir: Path, metadata: dict[str, Any], results: list[ScenarioResult]) -> tuple[Path, Path, Path]:
    output_dir.mkdir(parents=True, exist_ok=True)
    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    json_path = output_dir / f"marketplace_performance_results_{timestamp}.json"
    csv_path = output_dir / f"marketplace_performance_results_{timestamp}.csv"
    markdown_path = output_dir / f"marketplace_performance_results_{timestamp}.md"

    result_dicts = [result.as_dict() for result in results]
    with json_path.open("w", encoding="utf-8") as file_obj:
        json.dump({"metadata": metadata, "results": result_dicts}, file_obj, indent=2)

    csv_fields = [
        "test_case_id",
        "scenario_name",
        "target_name",
        "target",
        "status",
        "passed",
        "threshold_seconds",
        "p99_threshold_seconds",
        "average_seconds",
        "median_seconds",
        "p95_seconds",
        "p99_seconds",
        "worst_seconds",
        "notes",
    ]
    with csv_path.open("w", newline="", encoding="utf-8") as file_obj:
        writer = csv.DictWriter(file_obj, fieldnames=csv_fields)
        writer.writeheader()
        for result_dict in result_dicts:
            writer.writerow({field: result_dict.get(field) for field in csv_fields})

    with markdown_path.open("w", encoding="utf-8") as file_obj:
        file_obj.write("# Marketplace Website Manual Performance Results\n\n")
        file_obj.write("## Environment\n\n")
        for key, value in metadata.items():
            label = key.replace("_", " ").title()
            file_obj.write(f"- **{label}:** {value}\n")
        file_obj.write("\n## Results\n\n")
        file_obj.write("| Test Case | Target | Status | p95 (s) | p99 (s) | Worst (s) | Threshold (s) | Notes |\n")
        file_obj.write("| --- | --- | ---: | ---: | ---: | ---: | ---: | --- |\n")
        for result in results:
            p95 = "" if result.p95_seconds is None else f"{result.p95_seconds:.3f}"
            p99 = "" if result.p99_seconds is None else f"{result.p99_seconds:.3f}"
            worst = "" if result.worst_seconds is None else f"{result.worst_seconds:.3f}"
            notes = str(result.notes or "").replace("\n", "<br>")
            file_obj.write(
                f"| {result.test_case_id} | {result.target_name} | {result.status} | {p95} | {p99} | {worst} | {result.threshold_seconds:.1f} | {notes} |\n"
            )

    return json_path, csv_path, markdown_path


def parse_args(argv: Iterable[str]) -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description=(
            "Run the Marketplace Website manual Playwright performance timing checks "
            "defined by TC-PERF-001 through TC-PERF-009."
        )
    )
    parser.add_argument("--config", type=Path, default=DEFAULT_CONFIG_PATH, help="Path to the JSON performance-test configuration file.")
    parser.add_argument("--base-url", default=os.environ.get("MP_PERF_BASE_URL"), help="Base URL for the running Django site, such as http://localhost:8000/.")
    parser.add_argument("--headful", action="store_true", help="Run Chromium visibly instead of headless.")
    parser.add_argument("--warmups", type=int, default=DEFAULT_WARMUP_RUNS, help="Warm-up runs to discard before measurement.")
    parser.add_argument("--runs", type=int, default=DEFAULT_MEASURED_RUNS, help="Measured runs to record for each target.")
    parser.add_argument("--timeout-ms", type=int, default=DEFAULT_TIMEOUT_MILLISECONDS, help="Playwright navigation/action timeout in milliseconds.")
    parser.add_argument("--include-write-tests", action="store_true", help="Execute state-changing submit workflows for TC-PERF-003 through TC-PERF-005.")
    parser.add_argument("--auth-strategy", choices=["form-post", "ui-login", "django-session", "auto"], default="form-post", help="How authenticated Playwright contexts are created. form-post posts the real login form through Playwright's shared browser request context and is the default for local performance runs; ui-login clicks through the visible login page; django-session creates a session cookie by importing Django and querying the local database; auto tries form-post, then UI login, then Django session auth.")
    parser.add_argument("--only", nargs="*", default=[], help="Optional list of TC-PERF IDs to run, such as TC-PERF-001 TC-PERF-002.")
    parser.add_argument("--output-dir", type=Path, default=DEFAULT_RESULTS_DIR, help="Directory where JSON/CSV/Markdown results will be written.")
    return parser.parse_args(list(argv))


def main(argv: Iterable[str] | None = None) -> int:
    args = parse_args(sys.argv[1:] if argv is None else argv)
    if sync_playwright is None:
        print(
            "Playwright for Python is not installed. Install it with:\n"
            "  pip install playwright\n"
            "  python -m playwright install chromium",
            file=sys.stderr,
        )
        return 2

    config = _load_config(args.config)
    base_url = args.base_url or str(config.get("base_url") or "http://localhost:8000/")
    only_test_case_ids = {str(value).strip().upper() for value in args.only if str(value).strip()}

    with sync_playwright() as playwright:
        runner = ManualPerformanceRunner(
            playwright=playwright,
            config=config,
            base_url=base_url,
            headless=not args.headful,
            warmups=int(args.warmups),
            runs=int(args.runs),
            timeout_milliseconds=int(args.timeout_ms),
            include_write_tests=bool(args.include_write_tests),
            only_test_case_ids=only_test_case_ids,
            auth_strategy=str(args.auth_strategy),
        )
        results = runner.run()

    metadata = _build_environment_metadata(
        config=config,
        base_url=_normalize_base_url(base_url),
        headless=not args.headful,
        warmups=int(args.warmups),
        runs=int(args.runs),
    )
    json_path, csv_path, markdown_path = _write_results(output_dir=args.output_dir, metadata=metadata, results=results)

    print(f"Wrote JSON results: {json_path}")
    print(f"Wrote CSV results: {csv_path}")
    print(f"Wrote Markdown summary: {markdown_path}")

    failed_results = [result for result in results if result.passed is False]
    return 1 if failed_results else 0


if __name__ == "__main__":
    raise SystemExit(main())
