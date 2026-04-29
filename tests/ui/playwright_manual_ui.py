from __future__ import annotations

import argparse
import csv
import json
import os
import re
import sys
import time
from dataclasses import dataclass, field
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Iterable
from urllib.parse import urljoin

try:
    from playwright.sync_api import Browser, BrowserContext, Page, Playwright, TimeoutError as PlaywrightTimeoutError, sync_playwright
except ImportError:  # pragma: no cover - manual optional test dependency.
    Browser = Any  # type: ignore[misc,assignment]
    BrowserContext = Any  # type: ignore[misc,assignment]
    Page = Any  # type: ignore[misc,assignment]
    Playwright = Any  # type: ignore[misc,assignment]
    PlaywrightTimeoutError = TimeoutError  # type: ignore[assignment]
    sync_playwright = None  # type: ignore[assignment]


DEFAULT_TIMEOUT_MILLISECONDS: int = 15_000
DEFAULT_RESULTS_DIR: Path = Path(__file__).resolve().parents[2] / "ui_results"
DEFAULT_UI_CONFIG_PATH: Path = Path(__file__).with_name("playwright_ui_config.example.json")
DEFAULT_UI_LOCAL_CONFIG_PATH: Path = Path(__file__).with_name("playwright_ui_config.local.json")
DEFAULT_PERFORMANCE_LOCAL_CONFIG_PATH: Path = Path(__file__).resolve().parents[1] / "performance" / "playwright_performance_config.local.json"
DEFAULT_PERFORMANCE_EXAMPLE_CONFIG_PATH: Path = Path(__file__).resolve().parents[1] / "performance" / "playwright_performance_config.example.json"


class UiPreconditionError(RuntimeError):
    """Raised when a local page, credential, role, or configured test datum is missing."""


@dataclass(slots=True)
class UiResult:
    test_case_id: str
    objective: str
    status: str
    passed: bool | None
    pages_checked: list[str] = field(default_factory=list)
    checks: list[str] = field(default_factory=list)
    notes: str = ""

    def as_dict(self) -> dict[str, Any]:
        return {
            "test_case_id": self.test_case_id,
            "objective": self.objective,
            "status": self.status,
            "passed": self.passed,
            "pages_checked": self.pages_checked,
            "checks": self.checks,
            "notes": self.notes,
        }


@dataclass(slots=True)
class LoggedInSession:
    role_name: str
    context: BrowserContext
    page: Page


class ManualUiRunner:
    def __init__(
        self,
        *,
        playwright: Playwright,
        config: dict[str, Any],
        base_url: str,
        headless: bool,
        timeout_milliseconds: int,
        only_test_case_ids: set[str],
    ) -> None:
        self.playwright: Playwright = playwright
        self.config: dict[str, Any] = config
        self.base_url: str = _normalize_base_url(base_url)
        self.headless: bool = headless
        self.timeout_milliseconds: int = timeout_milliseconds
        self.only_test_case_ids: set[str] = only_test_case_ids
        self.browser: Browser | None = None
        self.sessions: dict[str, LoggedInSession] = {}
        self.results: list[UiResult] = []

    def run(self) -> list[UiResult]:
        self.browser = self.playwright.chromium.launch(headless=self.headless)
        try:
            self._run_tc_ui_001_public_browsing()
            self._run_tc_ui_002_authentication_forms()
            self._run_tc_ui_003_seller_workflows()
            self._run_tc_ui_004_restricted_and_forbidden_states()
            self._run_tc_ui_005_messaging_workflow()
            self._run_tc_ui_006_staff_workflows()
            self._run_tc_ui_007_accessibility_basics()
            self._run_tc_ui_008_bootstrap_consistency()
        finally:
            for session in self.sessions.values():
                try:
                    session.context.close()
                except Exception:  # noqa: BLE001 - do not mask test results during cleanup.
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

        context: BrowserContext = self._new_context()
        page: Page = context.new_page()
        if role_name == "guest":
            session = LoggedInSession(role_name=role_name, context=context, page=page)
            self.sessions[role_name] = session
            return session

        credentials = _get_credentials(self.config, role_name)
        if credentials is None and role_name == "staff":
            credentials = _get_credentials(self.config, "moderator") or _get_credentials(self.config, "admin")
        if credentials is None and role_name in {"reporter", "conversation_reporter"}:
            credentials = _get_credentials(self.config, "buyer")
        if credentials is None and role_name == "message_sender":
            credentials = _get_credentials(self.config, "buyer")
        if credentials is None:
            try:
                context.close()
            except Exception:  # noqa: BLE001
                pass
            return None

        try:
            _login_by_form_post(
                page=page,
                config=self.config,
                base_url=self.base_url,
                email=credentials["email"],
                password=credentials["password"],
                role_name=role_name,
                timeout_milliseconds=self.timeout_milliseconds,
            )
        except Exception:  # noqa: BLE001 - fall back to visible login interaction before giving up.
            try:
                _login_by_ui(
                    page=page,
                    config=self.config,
                    base_url=self.base_url,
                    email=credentials["email"],
                    password=credentials["password"],
                    role_name=role_name,
                    timeout_milliseconds=self.timeout_milliseconds,
                )
            except Exception:
                try:
                    context.close()
                except Exception:  # noqa: BLE001
                    pass
                return None

        session = LoggedInSession(role_name=role_name, context=context, page=page)
        self.sessions[role_name] = session
        return session

    def _record_pass(self, test_case_id: str, objective: str, pages: list[str], checks: list[str], notes: str = "") -> None:
        self.results.append(UiResult(test_case_id=test_case_id, objective=objective, status="PASS", passed=True, pages_checked=pages, checks=checks, notes=notes))

    def _record_blocked(self, test_case_id: str, objective: str, notes: str) -> None:
        self.results.append(UiResult(test_case_id=test_case_id, objective=objective, status="BLOCKED", passed=None, notes=notes))

    def _record_failure(self, test_case_id: str, objective: str, pages: list[str], checks: list[str], notes: str) -> None:
        self.results.append(UiResult(test_case_id=test_case_id, objective=objective, status="FAIL", passed=False, pages_checked=pages, checks=checks, notes=notes))

    def _safe_run(self, test_case_id: str, objective: str, test_body: Any) -> None:
        if not self._should_run(test_case_id):
            return
        try:
            pages, checks, notes = test_body()
            self._record_pass(test_case_id, objective, pages, checks, notes)
        except UiPreconditionError as exc:
            self._record_blocked(test_case_id, objective, str(exc))
        except AssertionError as exc:
            self._record_failure(test_case_id, objective, [], [], str(exc))
        except Exception as exc:  # noqa: BLE001 - manual runner records failures instead of aborting the whole run.
            self._record_failure(test_case_id, objective, [], [], f"Unexpected error: {exc}")

    def _run_tc_ui_001_public_browsing(self) -> None:
        objective = "Verify homepage, search results, and listing-detail pages use consistent public browsing layout and readable listing presentation."

        def body() -> tuple[list[str], list[str], str]:
            session = self._require_session("guest", "TC-UI-001")
            page = session.page
            home_path = _path(self.config, "home", "/")
            search_path = _path(self.config, "search", "/search/?q=&category=&min_price=&max_price=&condition=&distance_miles=&sort=most_relevant")
            listing_path = _path_from_id(self.config, "listing_detail", "listing_id", "/listings/{id}/", default_id=1001)
            pages = []
            checks = []

            for name, path in [("homepage", home_path), ("search", search_path), ("listing detail", listing_path)]:
                _goto_or_raise(page, self.base_url, path, self.timeout_milliseconds)
                pages.append(path)
                _assert_not_login_page(page, "guest")
                _assert_visible_count_at_least(page, "nav, .navbar", 1, f"{name} navigation")
                _assert_visible_count_at_least(page, "h1, h2", 1, f"{name} heading hierarchy")
                _assert_visible_count_at_least(page, "a[href], button, input, select, textarea", 2, f"{name} interactive controls")
                _assert_no_body_horizontal_overflow(page, f"{name} horizontal overflow")
                checks.append(f"{name}: navigation, headings, controls, and responsive width checked")

            _assert_visible_count_at_least(page, ".card, .carousel, img, [class*='listing']", 1, "listing detail presentation")
            checks.append("listing detail: listing presentation component checked")
            return pages, checks, ""

        self._safe_run("TC-UI-001", objective, body)

    def _run_tc_ui_002_authentication_forms(self) -> None:
        objective = "Verify registration and login screens are visually clear and provide useful form labels and validation behavior."

        def body() -> tuple[list[str], list[str], str]:
            session = self._require_session("guest", "TC-UI-002")
            page = session.page
            register_path = _path(self.config, "register", "/register/")
            login_path = _path(self.config, "login", "/login/")
            pages = []
            checks = []

            for name, path in [("register", register_path), ("login", login_path)]:
                _goto_or_raise(page, self.base_url, path, self.timeout_milliseconds)
                pages.append(path)
                _assert_visible_count_at_least(page, "form", 1, f"{name} form")
                _assert_form_inputs_have_labels(page, f"{name} form labels")
                _assert_visible_count_at_least(page, "button[type='submit'], input[type='submit']", 1, f"{name} primary action")
                _assert_required_fields_have_names(page, f"{name} required field naming")
                _assert_no_body_horizontal_overflow(page, f"{name} horizontal overflow")
                checks.append(f"{name}: labels, required inputs, primary action, and layout checked")

            _goto_or_raise(page, self.base_url, login_path, self.timeout_milliseconds)
            page.locator("input[name='email']").first.fill("not-a-valid-email")
            page.locator("input[name='password']").first.fill("")
            validity = page.locator("input[name='email']").first.evaluate("el => el.validity.valid === false")
            assert validity is True, "Login email field did not expose browser validation for invalid email input."
            checks.append("login: HTML validation state checked for invalid email input")
            return pages, checks, ""

        self._safe_run("TC-UI-002", objective, body)

    def _run_tc_ui_003_seller_workflows(self) -> None:
        objective = "Verify authenticated seller/profile/listing-management screens use efficient, understandable workflows."

        def body() -> tuple[list[str], list[str], str]:
            session = self._require_session("seller", "TC-UI-003")
            page = session.page
            pages_to_check = [
                ("profile", _path(self.config, "profile", "/profile/")),
                ("my listings", _path(self.config, "my_listings", "/my-listings/")),
                ("create listing", _path(self.config, "create_listing", "/listings/create/")),
                ("edit listing", _path_from_id(self.config, "edit_listing", "edit_listing_id", "/listings/{id}/edit/", default_id=1001)),
            ]
            pages = []
            checks = []

            for name, path in pages_to_check:
                _goto_or_raise(page, self.base_url, path, self.timeout_milliseconds)
                _assert_not_login_page(page, "seller")
                pages.append(path)
                _assert_visible_count_at_least(page, "h1, h2", 1, f"{name} page heading")
                _assert_visible_count_at_least(page, ".card, form, .btn, table, [class*='listing']", 1, f"{name} organized UI components")
                _assert_no_body_horizontal_overflow(page, f"{name} horizontal overflow")
                checks.append(f"{name}: heading, organized UI component, and responsive width checked")

            _goto_or_raise(page, self.base_url, _path(self.config, "create_listing", "/listings/create/"), self.timeout_milliseconds)
            _assert_form_inputs_have_labels(page, "create listing form labels")
            _assert_visible_count_at_least(page, "#listing-editor-form, form[data-listing-editor='true']", 1, "create listing editor form")
            _assert_visible_count_at_least(page, "#save-listing-button, button:has-text('Save Listing')", 1, "create listing save button")
            checks.append("create listing: editor form, labels, and primary save action checked")

            edit_path = _path_from_id(self.config, "edit_listing", "edit_listing_id", "/listings/{id}/edit/", default_id=1001)
            _goto_or_raise(page, self.base_url, edit_path, self.timeout_milliseconds)
            _assert_visible_count_at_least(page, "#listing-editor-form, form[data-listing-editor='true']", 1, "edit listing editor form")
            _assert_visible_count_at_least(page, "#save-listing-button, button:has-text('Save Changes')", 1, "edit listing save button")
            checks.append("edit listing: editor form and save changes action checked")
            return pages, checks, ""

        self._safe_run("TC-UI-003", objective, body)

    def _run_tc_ui_004_restricted_and_forbidden_states(self) -> None:
        objective = "Verify restricted-state and forbidden-access screens communicate state clearly and safely."

        def body() -> tuple[list[str], list[str], str]:
            session = self._require_session("buyer", "TC-UI-004")
            page = session.page
            pages = []
            checks = []
            notes: list[str] = []

            frozen_path = _path(self.config, "frozen_listing_edit", "")
            if frozen_path:
                _goto_or_raise(page, self.base_url, frozen_path, self.timeout_milliseconds, allow_forbidden=True)
                pages.append(frozen_path)
                body_text = _visible_text(page).lower()
                assert any(term in body_text for term in ["frozen", "not editable", "cannot edit", "forbidden", "permission", "access"]), (
                    "Frozen/restricted listing page did not visibly communicate a restricted state."
                )
                checks.append("frozen/restricted listing state message checked")
            else:
                notes.append("No frozen_listing_edit path configured; forbidden-access scenario is used for restricted-state coverage.")

            forbidden_path = _path(self.config, "forbidden_probe", "/admin/dashboard/")
            _goto_or_raise(page, self.base_url, forbidden_path, self.timeout_milliseconds, allow_forbidden=True)
            pages.append(forbidden_path)
            body_text = _visible_text(page).lower()
            assert any(term in body_text for term in ["forbidden", "access", "permission", "not authorized", "login"]), (
                "Forbidden/access-denied condition did not provide a clear explanation."
            )
            _assert_visible_count_at_least(page, "a[href], button", 1, "safe navigation/action from forbidden page")
            checks.append("forbidden/access-denied page message and safe navigation checked")
            return pages, checks, " ".join(notes)

        self._safe_run("TC-UI-004", objective, body)

    def _run_tc_ui_005_messaging_workflow(self) -> None:
        objective = "Verify messaging screens support a clear buyer-seller communication workflow."

        def body() -> tuple[list[str], list[str], str]:
            session = self._require_session("message_sender", "TC-UI-005")
            page = session.page
            listing_path = _path_from_id(self.config, "listing_detail", "listing_id", "/listings/{id}/", default_id=1001)
            inbox_path = _path(self.config, "messages_inbox", "/messaging/inbox/")
            conversation_path = _path_from_id(self.config, "conversation_detail", "conversation_id", "/messaging/conversation/{id}/", default_id=2)
            pages = []
            checks = []

            for name, path in [("listing context", listing_path), ("inbox", inbox_path), ("conversation", conversation_path)]:
                _goto_or_raise(page, self.base_url, path, self.timeout_milliseconds)
                _assert_not_login_page(page, "message_sender")
                pages.append(path)
                _assert_visible_count_at_least(page, "h1, h2, h3", 1, f"{name} heading")
                _assert_visible_count_at_least(page, "a[href], button, input", 1, f"{name} navigation/actions")
                _assert_no_body_horizontal_overflow(page, f"{name} horizontal overflow")
                checks.append(f"{name}: heading, actions, and responsive width checked")

            _goto_or_raise(page, self.base_url, conversation_path, self.timeout_milliseconds)
            _assert_visible_count_at_least(page, "input[name='message_text'], textarea[name='message_text']", 1, "message input")
            _assert_visible_count_at_least(page, "button[type='submit'], input[type='submit']", 1, "message send action")
            _assert_visible_count_at_least(page, ".card, .list-group, [class*='message'], form", 1, "conversation presentation")
            checks.append("conversation: message input, send action, and message presentation checked")
            return pages, checks, ""

        self._safe_run("TC-UI-005", objective, body)

    def _run_tc_ui_006_staff_workflows(self) -> None:
        objective = "Verify moderator and administrator screens present privileged workflows clearly and deliberately."

        def body() -> tuple[list[str], list[str], str]:
            admin_session = self._require_session("admin", "TC-UI-006")
            staff_session = self._require_session("staff", "TC-UI-006")
            admin_page = admin_session.page
            staff_page = staff_session.page
            admin_pages = [
                ("admin dashboard", _path(self.config, "admin_dashboard", "/admin/dashboard/")),
                ("user management", _path(self.config, "admin_user_management", "/admin/user_management/")),
                ("listing management", _path(self.config, "admin_listing_management", "/admin/listing_management/")),
                ("reports hub", _path(self.config, "admin_reports_hub", "/admin/reports_hub/")),
            ]
            staff_pages = [
                ("moderation queue", _path(self.config, "moderation_queue", "/moderation/queue/")),
                ("report detail", _path_from_id(self.config, "report_detail", "report_id", "/moderation/reports/{id}/", default_id=2)),
            ]
            pages = []
            checks = []

            for name, path in admin_pages:
                _goto_or_raise(admin_page, self.base_url, path, self.timeout_milliseconds)
                _assert_not_login_page(admin_page, "admin")
                pages.append(path)
                _assert_visible_count_at_least(admin_page, "h1, h2", 1, f"{name} heading")
                _assert_visible_count_at_least(admin_page, ".card, table, form, .btn, .alert", 1, f"{name} structured staff component")
                _assert_no_body_horizontal_overflow(admin_page, f"{name} horizontal overflow")
                checks.append(f"{name}: heading, structured components, and responsive width checked")

            for name, path in staff_pages:
                _goto_or_raise(staff_page, self.base_url, path, self.timeout_milliseconds)
                _assert_not_login_page(staff_page, "staff")
                pages.append(path)
                _assert_visible_count_at_least(staff_page, "h1, h2", 1, f"{name} heading")
                _assert_visible_count_at_least(staff_page, ".card, table, form, .btn, .alert, [class*='queue'], [class*='report']", 1, f"{name} workflow component")
                _assert_no_body_horizontal_overflow(staff_page, f"{name} horizontal overflow")
                checks.append(f"{name}: heading, workflow component, and responsive width checked")
            return pages, checks, ""

        self._safe_run("TC-UI-006", objective, body)

    def _run_tc_ui_007_accessibility_basics(self) -> None:
        objective = "Verify keyboard usability, visible focus states, meaningful labels/headings, and semantic structure across representative screens."

        def body() -> tuple[list[str], list[str], str]:
            pages_to_check: list[tuple[str, str, str]] = [
                ("guest", "homepage", _path(self.config, "home", "/")),
                ("guest", "login", _path(self.config, "login", "/login/")),
                ("guest", "search", _path(self.config, "search", "/search/?q=&category=&min_price=&max_price=&condition=&distance_miles=&sort=most_relevant")),
                ("seller", "create listing", _path(self.config, "create_listing", "/listings/create/")),
                ("message_sender", "conversation", _path_from_id(self.config, "conversation_detail", "conversation_id", "/messaging/conversation/{id}/", default_id=2)),
                ("staff", "moderation queue", _path(self.config, "moderation_queue", "/moderation/queue/")),
                ("admin", "admin user management", _path(self.config, "admin_user_management", "/admin/user_management/")),
            ]
            pages = []
            checks = []
            blocked: list[str] = []

            for role, name, path in pages_to_check:
                session = self._session_for_role(role)
                if session is None:
                    blocked.append(f"{role}:{path}")
                    continue
                page = session.page
                _goto_or_raise(page, self.base_url, path, self.timeout_milliseconds, allow_forbidden=(role == "guest"))
                if role != "guest":
                    _assert_not_login_page(page, role)
                pages.append(path)
                _assert_visible_count_at_least(page, "h1, h2", 1, f"{name} meaningful heading")
                _assert_visible_count_at_least(page, "main, nav, header, [role='main'], [role='navigation']", 1, f"{name} landmark/semantic region")
                _assert_form_inputs_have_labels(page, f"{name} form labels", allow_no_forms=True)
                _assert_keyboard_focus_visible(page, f"{name} keyboard focus")
                checks.append(f"{name}: headings, labels, landmarks, and keyboard focus checked")

            if blocked:
                raise UiPreconditionError("Could not authenticate or open these representative accessibility pages: " + ", ".join(blocked))
            return pages, checks, ""

        self._safe_run("TC-UI-007", objective, body)

    def _run_tc_ui_008_bootstrap_consistency(self) -> None:
        objective = "Verify representative pages use consistent Bootstrap-based styling rather than ad hoc page-by-page presentation."

        def body() -> tuple[list[str], list[str], str]:
            representative_pages: list[tuple[str, str, str]] = [
                ("guest", "homepage", _path(self.config, "home", "/")),
                ("guest", "search", _path(self.config, "search", "/search/?q=&category=&min_price=&max_price=&condition=&distance_miles=&sort=most_relevant")),
                ("guest", "listing detail", _path_from_id(self.config, "listing_detail", "listing_id", "/listings/{id}/", default_id=1001)),
                ("seller", "create listing", _path(self.config, "create_listing", "/listings/create/")),
                ("message_sender", "conversation", _path_from_id(self.config, "conversation_detail", "conversation_id", "/messaging/conversation/{id}/", default_id=2)),
                ("staff", "moderation queue", _path(self.config, "moderation_queue", "/moderation/queue/")),
                ("admin", "admin dashboard", _path(self.config, "admin_dashboard", "/admin/dashboard/")),
            ]
            pages = []
            checks = []
            blocked: list[str] = []
            page_scores: list[tuple[str, int]] = []

            for role, name, path in representative_pages:
                session = self._session_for_role(role)
                if session is None:
                    blocked.append(f"{role}:{path}")
                    continue
                page = session.page
                _goto_or_raise(page, self.base_url, path, self.timeout_milliseconds)
                if role != "guest":
                    _assert_not_login_page(page, role)
                pages.append(path)
                component_score = int(page.locator(".container, .container-fluid, .row, [class*='col-'], .btn, .card, .form-control, .form-select, .table, .alert, .navbar").count())
                assert component_score >= 2, f"{name} did not expose enough recognizable Bootstrap-oriented components."
                page_scores.append((name, component_score))
                _assert_visible_count_at_least(page, ".btn, a.btn, button, input[type='submit']", 1, f"{name} action styling")
                _assert_no_body_horizontal_overflow(page, f"{name} horizontal overflow")
                checks.append(f"{name}: Bootstrap-oriented component count {component_score}, action styling, and responsive width checked")

            if blocked:
                raise UiPreconditionError("Could not authenticate or open these representative Bootstrap pages: " + ", ".join(blocked))
            return pages, checks, "Component scores: " + "; ".join(f"{name}={score}" for name, score in page_scores)

        self._safe_run("TC-UI-008", objective, body)

    def _require_session(self, role_name: str, test_case_id: str) -> LoggedInSession:
        session = self._session_for_role(role_name)
        if session is None:
            raise UiPreconditionError(f"Could not create an authenticated browser context for role '{role_name}' in {test_case_id}. Check config credentials and account status.")
        return session


def _normalize_base_url(base_url: str) -> str:
    return str(base_url or "http://localhost:8000/").rstrip("/") + "/"


def _absolute_url(base_url: str, path: str) -> str:
    if path.startswith("http://") or path.startswith("https://"):
        return path
    return urljoin(base_url, path.lstrip("/"))


def _config_value(config: dict[str, Any], dotted_key: str, default: Any = None) -> Any:
    current: Any = config
    for part in dotted_key.split("."):
        if not isinstance(current, dict) or part not in current:
            return default
        current = current[part]
    return current


def _path(config: dict[str, Any], key: str, default: str) -> str:
    raw = _config_value(config, f"paths.{key}")
    if raw is None or str(raw).strip() == "":
        return default
    return str(raw).strip()


def _path_from_id(config: dict[str, Any], path_key: str, id_key: str, template: str, default_id: int) -> str:
    configured_path = _config_value(config, f"paths.{path_key}")
    if configured_path:
        return str(configured_path)
    configured_id = _config_value(config, f"ids.{id_key}", default_id)
    return template.format(id=int(configured_id))


def _get_credentials(config: dict[str, Any], role_name: str) -> dict[str, str] | None:
    role_key = str(role_name).strip().lower()
    env_prefixes = [f"MP_UI_{role_key.upper()}", f"MP_PERF_{role_key.upper()}"]
    for env_prefix in env_prefixes:
        email = os.environ.get(f"{env_prefix}_EMAIL")
        password = os.environ.get(f"{env_prefix}_PASSWORD")
        if email and password:
            return {"email": email, "password": password}

    users = config.get("users", {})
    if not isinstance(users, dict):
        return None
    aliases = {
        "staff": ["staff", "moderator", "admin"],
        "message_sender": ["message_sender", "buyer", "admin", "seller"],
        "reporter": ["reporter", "buyer"],
        "conversation_reporter": ["conversation_reporter", "message_sender", "buyer", "admin"],
    }
    for key in aliases.get(role_key, [role_key]):
        raw_credentials = users.get(key)
        if not isinstance(raw_credentials, dict):
            continue
        email = str(raw_credentials.get("email") or "").strip()
        password = str(raw_credentials.get("password") or "").strip()
        if email and password:
            return {"email": email, "password": password}
    return None


def _login_by_form_post(
    *,
    page: Page,
    config: dict[str, Any],
    base_url: str,
    email: str,
    password: str,
    role_name: str,
    timeout_milliseconds: int,
) -> None:
    login_url = _absolute_url(base_url, _path(config, "login", "/login/"))
    page.goto(login_url, wait_until="networkidle", timeout=timeout_milliseconds)
    csrf_token = page.locator('input[name="csrfmiddlewaretoken"]').first.input_value(timeout=timeout_milliseconds)
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
        timeout=timeout_milliseconds,
    )
    if not response.ok:
        raise UiPreconditionError(f"Login POST returned HTTP {response.status} for role '{role_name}'.")
    cookie_names = {str(cookie.get("name", "")) for cookie in page.context.cookies(base_url)}
    if "sessionid" not in cookie_names:
        page.goto(login_url, wait_until="networkidle", timeout=timeout_milliseconds)
        error_text = _safe_inner_text(page, ".alert, .invalid-feedback, .text-danger, .errorlist, [role='alert']")
        raise UiPreconditionError(f"Login did not create a sessionid cookie for role '{role_name}'. Login error text: {error_text!r}.")


def _login_by_ui(
    *,
    page: Page,
    config: dict[str, Any],
    base_url: str,
    email: str,
    password: str,
    role_name: str,
    timeout_milliseconds: int,
) -> None:
    login_url = _absolute_url(base_url, _path(config, "login", "/login/"))
    page.goto(login_url, wait_until="networkidle", timeout=timeout_milliseconds)
    page.locator('#id_email, input[name="email"]').first.fill(email)
    page.locator('#id_password, input[name="password"]').first.fill(password)
    submit = page.locator('#submit-id-submit, input[type="submit"][value="Log In"], button[type="submit"]').first
    try:
        with page.expect_navigation(wait_until="networkidle", timeout=timeout_milliseconds):
            submit.click()
    except PlaywrightTimeoutError:
        submit.click(timeout=timeout_milliseconds)
        page.wait_for_load_state("networkidle", timeout=timeout_milliseconds)
    _assert_not_login_page(page, role_name)


def _goto_or_raise(page: Page, base_url: str, path: str, timeout_milliseconds: int, *, allow_forbidden: bool = False) -> None:
    response = page.goto(_absolute_url(base_url, path), wait_until="networkidle", timeout=timeout_milliseconds)
    status = response.status if response is not None else 200
    if status >= 400 and not (allow_forbidden and status in {401, 403, 404}):
        raise UiPreconditionError(f"{path} returned HTTP {status}. {_diagnostic_context(page)}")


def _assert_not_login_page(page: Page, role_name: str) -> None:
    url = page.url.lower()
    if "/login" in url:
        raise UiPreconditionError(f"Role '{role_name}' was redirected to the login page. {_diagnostic_context(page)}")


def _diagnostic_context(page: Page) -> str:
    try:
        title = page.title()
    except Exception:  # noqa: BLE001
        title = ""
    try:
        body_preview = re.sub(r"\s+", " ", page.locator("body").inner_text(timeout=1000)).strip()[:350]
    except Exception:  # noqa: BLE001
        body_preview = ""
    return f"Current URL: {page.url}; title: {title!r}; body preview: {body_preview!r}"


def _safe_inner_text(page: Page, selector: str) -> str:
    try:
        locator = page.locator(selector).first
        if locator.count() == 0:
            return ""
        return re.sub(r"\s+", " ", locator.inner_text(timeout=1000)).strip()
    except Exception:  # noqa: BLE001
        return ""


def _visible_text(page: Page) -> str:
    return re.sub(r"\s+", " ", page.locator("body").inner_text(timeout=3000)).strip()


def _assert_visible_count_at_least(page: Page, selector: str, minimum: int, description: str) -> None:
    count = page.locator(selector).count()
    visible_count = 0
    for index in range(min(count, 75)):
        try:
            if page.locator(selector).nth(index).is_visible(timeout=250):
                visible_count += 1
        except Exception:  # noqa: BLE001
            continue
    assert visible_count >= minimum, f"Expected at least {minimum} visible {description}; found {visible_count}. {_diagnostic_context(page)}"


def _assert_form_inputs_have_labels(page: Page, description: str, *, allow_no_forms: bool = False) -> None:
    input_count = int(page.locator("form input:not([type='hidden']):not([type='submit']), form select, form textarea").count())
    if input_count == 0:
        if allow_no_forms:
            return
        raise AssertionError(f"Expected at least one visible form input for {description}.")
    unlabeled: list[str] = page.evaluate(
        """
        () => Array.from(document.querySelectorAll("form input:not([type='hidden']):not([type='submit']), form select, form textarea"))
            .filter((el) => {
                const id = el.getAttribute('id');
                const aria = el.getAttribute('aria-label') || el.getAttribute('aria-labelledby');
                const placeholder = el.getAttribute('placeholder');
                const name = el.getAttribute('name') || el.tagName.toLowerCase();
                const label = id ? document.querySelector(`label[for="${CSS.escape(id)}"]`) : null;
                const wrappingLabel = el.closest('label');
                return !aria && !placeholder && !label && !wrappingLabel;
            })
            .map((el) => el.getAttribute('name') || el.getAttribute('id') || el.tagName.toLowerCase())
        """
    )
    assert not unlabeled, f"Unlabeled form controls found for {description}: {unlabeled}. {_diagnostic_context(page)}"


def _assert_required_fields_have_names(page: Page, description: str) -> None:
    unnamed_required: list[str] = page.evaluate(
        """
        () => Array.from(document.querySelectorAll("form input[required], form select[required], form textarea[required]"))
            .filter((el) => !el.getAttribute('name'))
            .map((el) => el.getAttribute('id') || el.tagName.toLowerCase())
        """
    )
    assert not unnamed_required, f"Required controls without names found for {description}: {unnamed_required}."


def _assert_keyboard_focus_visible(page: Page, description: str) -> None:
    focusable_count = page.locator("a[href], button:not([disabled]), input:not([type='hidden']):not([disabled]), select:not([disabled]), textarea:not([disabled])").count()
    assert focusable_count > 0, f"No focusable controls found for {description}."
    page.keyboard.press("Tab")
    page.wait_for_timeout(100)
    focused_summary = page.evaluate(
        """
        () => {
            const el = document.activeElement;
            if (!el || el === document.body) return {ok: false, reason: 'focus remained on body'};
            const style = window.getComputedStyle(el);
            const rect = el.getBoundingClientRect();
            const hasVisibleBox = rect.width > 0 && rect.height > 0;
            const focusStyle = [style.outlineStyle, style.outlineWidth, style.boxShadow, style.borderColor].join(' ');
            const hasVisibleFocus = style.outlineStyle !== 'none' || style.outlineWidth !== '0px' || style.boxShadow !== 'none';
            return {ok: hasVisibleBox && hasVisibleFocus, reason: `${el.tagName.toLowerCase()} focusStyle=${focusStyle}`};
        }
        """
    )
    assert focused_summary.get("ok"), f"Keyboard focus was not visibly indicated for {description}: {focused_summary.get('reason')}"


def _assert_no_body_horizontal_overflow(page: Page, description: str) -> None:
    overflow = page.evaluate("() => document.documentElement.scrollWidth - document.documentElement.clientWidth")
    assert overflow <= 8, f"Detected horizontal overflow of {overflow}px for {description}."


def _load_config(path: Path) -> dict[str, Any]:
    try:
        with path.open("r", encoding="utf-8") as handle:
            data = json.load(handle)
    except FileNotFoundError as exc:
        raise SystemExit(f"Config file not found: {path}") from exc
    if not isinstance(data, dict):
        raise SystemExit(f"Config file must contain a JSON object: {path}")
    return data


def _default_config_path() -> Path:
    for candidate in [DEFAULT_UI_LOCAL_CONFIG_PATH, DEFAULT_PERFORMANCE_LOCAL_CONFIG_PATH, DEFAULT_UI_CONFIG_PATH, DEFAULT_PERFORMANCE_EXAMPLE_CONFIG_PATH]:
        if candidate.exists():
            return candidate
    return DEFAULT_UI_CONFIG_PATH


def _write_results(results: list[UiResult], config: dict[str, Any], output_dir: Path, base_url: str, headless: bool) -> tuple[Path, Path, Path]:
    output_dir.mkdir(parents=True, exist_ok=True)
    timestamp = datetime.now(timezone.utc).strftime("%Y%m%d_%H%M%S")
    json_path = output_dir / f"marketplace_ui_results_{timestamp}.json"
    csv_path = output_dir / f"marketplace_ui_results_{timestamp}.csv"
    md_path = output_dir / f"marketplace_ui_results_{timestamp}.md"
    metadata = {
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "base_url": base_url,
        "browser": "Chromium through Playwright for Python",
        "browser_mode": "headless" if headless else "visible/headful",
        "dataset_description": config.get("dataset_description", "Representative local Marketplace Website dataset."),
        "source": "Manual Playwright UI verification for TC-UI-001 through TC-UI-008.",
    }
    with json_path.open("w", encoding="utf-8") as handle:
        json.dump({"metadata": metadata, "results": [result.as_dict() for result in results]}, handle, indent=2)
    with csv_path.open("w", encoding="utf-8", newline="") as handle:
        writer = csv.writer(handle)
        writer.writerow(["Test Case", "Status", "Passed", "Pages Checked", "Checks", "Notes"])
        for result in results:
            writer.writerow([result.test_case_id, result.status, result.passed, " | ".join(result.pages_checked), " | ".join(result.checks), result.notes])
    with md_path.open("w", encoding="utf-8") as handle:
        handle.write("# Marketplace Website Manual Playwright UI Results\n\n")
        handle.write("## Environment\n\n")
        for key, value in metadata.items():
            handle.write(f"- **{key.replace('_', ' ').title()}:** {value}\n")
        handle.write("\n## Results\n\n")
        handle.write("| Test Case | Status | Pages Checked | Notes |\n")
        handle.write("| --- | ---: | --- | --- |\n")
        for result in results:
            pages = "<br>".join(result.pages_checked)
            notes = result.notes.replace("\n", " ")
            handle.write(f"| {result.test_case_id} | {result.status} | {pages} | {notes} |\n")
        handle.write("\n## Checks\n\n")
        for result in results:
            handle.write(f"### {result.test_case_id} — {result.status}\n\n")
            handle.write(f"{result.objective}\n\n")
            for check in result.checks:
                handle.write(f"- {check}\n")
            if result.notes:
                handle.write(f"\nNotes: {result.notes}\n")
            handle.write("\n")
    return json_path, csv_path, md_path


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Run manual Playwright UI verification for Marketplace Website TC-UI-001 through TC-UI-008.")
    parser.add_argument("--config", type=Path, default=_default_config_path(), help="Path to Playwright UI/performance config JSON. Defaults to UI local config, performance local config, then UI example config.")
    parser.add_argument("--base-url", default=None, help="Override base URL from config, e.g. http://localhost:8000/.")
    parser.add_argument("--headless", action="store_true", help="Run Chromium headlessly. By default the browser is visible for manual UI observation.")
    parser.add_argument("--timeout-ms", type=int, default=DEFAULT_TIMEOUT_MILLISECONDS, help="Playwright timeout in milliseconds.")
    parser.add_argument("--only", action="append", default=[], help="Run only one UI test case ID. May be supplied multiple times, e.g. --only TC-UI-003.")
    parser.add_argument("--output-dir", type=Path, default=DEFAULT_RESULTS_DIR, help="Directory where UI result JSON/CSV/Markdown files are written.")
    args = parser.parse_args(argv)

    if sync_playwright is None:
        print("Playwright is not installed. Install it with: pip install playwright && python -m playwright install chromium", file=sys.stderr)
        return 2

    config = _load_config(args.config)
    base_url = _normalize_base_url(args.base_url or str(config.get("base_url") or "http://localhost:8000/"))
    only = {str(value).strip().upper() for value in args.only if str(value).strip()}

    with sync_playwright() as playwright:
        runner = ManualUiRunner(
            playwright=playwright,
            config=config,
            base_url=base_url,
            headless=args.headless,
            timeout_milliseconds=args.timeout_ms,
            only_test_case_ids=only,
        )
        results = runner.run()

    json_path, csv_path, md_path = _write_results(results, config, args.output_dir, base_url, args.headless)
    print(f"Wrote JSON results: {json_path}")
    print(f"Wrote CSV results: {csv_path}")
    print(f"Wrote Markdown summary: {md_path}")
    failed = [result for result in results if result.status == "FAIL"]
    blocked = [result for result in results if result.status == "BLOCKED"]
    if failed:
        print(f"{len(failed)} UI test(s) failed. Review the Markdown/JSON results.", file=sys.stderr)
        return 1
    if blocked:
        print(f"{len(blocked)} UI test(s) were blocked by missing local preconditions. Review the Markdown/JSON results.", file=sys.stderr)
        return 2
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
