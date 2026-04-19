from __future__ import annotations

from typing import Any

from django import forms
from crispy_forms.helper import FormHelper

from catalog.models import Category


DASHBOARD_DEFAULT_RANGE_WEEKS: int = 12


class AdminDashboardDateRangeForm(forms.Form):
    start_date: forms.DateField = forms.DateField(
        label="Start date",
        required=True,
        widget=forms.DateInput(
            attrs={
                "class": "form-control",
                "type": "date",
            }
        ),
    )
    end_date: forms.DateField = forms.DateField(
        label="End date",
        required=True,
        widget=forms.DateInput(
            attrs={
                "class": "form-control",
                "type": "date",
            }
        ),
    )

    def __init__(self, *args: Any, **kwargs: Any) -> None:
        from admin_ops.utils.dashboard_analytics import (
            get_default_dashboard_end_date,
            get_default_dashboard_start_date,
        )

        super().__init__(*args, **kwargs)

        self.helper = FormHelper(self)
        self.helper.form_method = "get"
        self.helper.form_tag = False

        if not self.is_bound:
            self.initial.setdefault("start_date", get_default_dashboard_start_date())
            self.initial.setdefault("end_date", get_default_dashboard_end_date())

    def clean(self) -> dict[str, Any]:
        cleaned_data: dict[str, Any] = super().clean()
        start_date = cleaned_data.get("start_date")
        end_date = cleaned_data.get("end_date")

        if start_date is not None and end_date is not None and end_date < start_date:
            raise forms.ValidationError("The end date must be on or after the start date.")

        return cleaned_data


USER_STATUS_ALL_VALUE: str = ""
USER_STATUS_ACTIVE_VALUE: str = "active"
USER_STATUS_BANNED_VALUE: str = "banned"

USER_ROLE_ALL_VALUE: str = ""
USER_ROLE_NONE_VALUE: str = "none"
USER_ROLE_MODERATOR_VALUE: str = "moderator"
USER_ROLE_ADMINISTRATOR_VALUE: str = "administrator"

USER_SORT_NEWEST_VALUE: str = "newest"
USER_SORT_OLDEST_VALUE: str = "oldest"
USER_SORT_NAME_ASC_VALUE: str = "name_asc"
USER_SORT_NAME_DESC_VALUE: str = "name_desc"
USER_SORT_EMAIL_ASC_VALUE: str = "email_asc"
USER_SORT_EMAIL_DESC_VALUE: str = "email_desc"
USER_SORT_ROLE_ASC_VALUE: str = "role_asc"
USER_SORT_ROLE_DESC_VALUE: str = "role_desc"
USER_SORT_STATUS_ASC_VALUE: str = "status_asc"
USER_SORT_STATUS_DESC_VALUE: str = "status_desc"


class UserManagementFilterForm(forms.Form):
    search_email: forms.CharField = forms.CharField(
        label="Search by email",
        required=False,
        widget=forms.TextInput(
            attrs={
                "class": "form-control",
                "placeholder": "Search by email",
                "autocomplete": "off",
            }
        ),
    )
    account_status: forms.ChoiceField = forms.ChoiceField(
        label="Account status",
        required=False,
        choices=(
            (USER_STATUS_ALL_VALUE, "All statuses"),
            (USER_STATUS_ACTIVE_VALUE, "Active"),
            (USER_STATUS_BANNED_VALUE, "Banned"),
        ),
        widget=forms.Select(attrs={"class": "form-select"}),
    )
    user_role: forms.ChoiceField = forms.ChoiceField(
        label="User role",
        required=False,
        choices=(
            (USER_ROLE_ALL_VALUE, "All roles"),
            (USER_ROLE_NONE_VALUE, "No role"),
            (USER_ROLE_MODERATOR_VALUE, "Moderator"),
            (USER_ROLE_ADMINISTRATOR_VALUE, "Administrator"),
        ),
        widget=forms.Select(attrs={"class": "form-select"}),
    )
    sort_by: forms.ChoiceField = forms.ChoiceField(
        label="Sort by",
        required=False,
        choices=(
            (USER_SORT_NEWEST_VALUE, "Newest accounts"),
            (USER_SORT_OLDEST_VALUE, "Oldest accounts"),
            (USER_SORT_NAME_ASC_VALUE, "Name (A to Z)"),
            (USER_SORT_NAME_DESC_VALUE, "Name (Z to A)"),
            (USER_SORT_EMAIL_ASC_VALUE, "Email (A to Z)"),
            (USER_SORT_EMAIL_DESC_VALUE, "Email (Z to A)"),
            (USER_SORT_ROLE_ASC_VALUE, "Role (A to Z)"),
            (USER_SORT_ROLE_DESC_VALUE, "Role (Z to A)"),
            (USER_SORT_STATUS_ASC_VALUE, "Status (Active first)"),
            (USER_SORT_STATUS_DESC_VALUE, "Status (Banned first)"),
        ),
        initial=USER_SORT_NEWEST_VALUE,
        widget=forms.Select(attrs={"class": "form-select"}),
    )

    def __init__(self, *args: Any, **kwargs: Any) -> None:
        super().__init__(*args, **kwargs)

        self.helper = FormHelper(self)
        self.helper.form_method = "get"
        self.helper.form_tag = False

        if not self.is_bound:
            self.initial.setdefault("sort_by", USER_SORT_NEWEST_VALUE)


LISTING_STATUS_ALL_VALUE: str = ""
LISTING_STATUS_ACTIVE_VALUE: str = "active"
LISTING_STATUS_FROZEN_VALUE: str = "frozen"
LISTING_STATUS_DELETED_VALUE: str = "deleted"

LISTING_CATEGORY_ALL_VALUE: str = ""

LISTING_SORT_NEWEST_VALUE: str = "newest"
LISTING_SORT_OLDEST_VALUE: str = "oldest"
LISTING_SORT_TITLE_ASC_VALUE: str = "title_asc"
LISTING_SORT_TITLE_DESC_VALUE: str = "title_desc"
LISTING_SORT_SELLER_ASC_VALUE: str = "seller_asc"
LISTING_SORT_SELLER_DESC_VALUE: str = "seller_desc"
LISTING_SORT_STATUS_ASC_VALUE: str = "status_asc"
LISTING_SORT_STATUS_DESC_VALUE: str = "status_desc"
LISTING_SORT_VIEWS_DESC_VALUE: str = "views_desc"
LISTING_SORT_VIEWS_ASC_VALUE: str = "views_asc"


class ListingManagementFilterForm(forms.Form):
    search_query: forms.CharField = forms.CharField(
        label="Search by seller email or keywords",
        required=False,
        widget=forms.TextInput(
            attrs={
                "class": "form-control",
                "placeholder": "Search by seller email, title, or description",
                "autocomplete": "off",
            }
        ),
    )
    listing_status: forms.ChoiceField = forms.ChoiceField(
        label="Listing status",
        required=False,
        choices=(
            (LISTING_STATUS_ALL_VALUE, "All statuses"),
            (LISTING_STATUS_ACTIVE_VALUE, "Active"),
            (LISTING_STATUS_FROZEN_VALUE, "Frozen"),
            (LISTING_STATUS_DELETED_VALUE, "Deleted"),
        ),
        widget=forms.Select(attrs={"class": "form-select"}),
    )
    category_id: forms.ChoiceField = forms.ChoiceField(
        label="Listing category",
        required=False,
        choices=((LISTING_CATEGORY_ALL_VALUE, "All child categories"),),
        widget=forms.Select(attrs={"class": "form-select"}),
    )
    sort_by: forms.ChoiceField = forms.ChoiceField(
        label="Sort by",
        required=False,
        choices=(
            (LISTING_SORT_NEWEST_VALUE, "Newest listings"),
            (LISTING_SORT_OLDEST_VALUE, "Oldest listings"),
            (LISTING_SORT_TITLE_ASC_VALUE, "Title (A to Z)"),
            (LISTING_SORT_TITLE_DESC_VALUE, "Title (Z to A)"),
            (LISTING_SORT_SELLER_ASC_VALUE, "Seller email (A to Z)"),
            (LISTING_SORT_SELLER_DESC_VALUE, "Seller email (Z to A)"),
            (LISTING_SORT_STATUS_ASC_VALUE, "Status (A to Z)"),
            (LISTING_SORT_STATUS_DESC_VALUE, "Status (Z to A)"),
            (LISTING_SORT_VIEWS_DESC_VALUE, "Views (highest first)"),
            (LISTING_SORT_VIEWS_ASC_VALUE, "Views (lowest first)"),
        ),
        initial=LISTING_SORT_NEWEST_VALUE,
        widget=forms.Select(attrs={"class": "form-select"}),
    )

    def __init__(self, *args: Any, **kwargs: Any) -> None:
        super().__init__(*args, **kwargs)

        self.helper = FormHelper(self)
        self.helper.form_method = "get"
        self.helper.form_tag = False

        self.fields["category_id"].choices = self._build_category_choices()

        if not self.is_bound:
            self.initial.setdefault("sort_by", LISTING_SORT_NEWEST_VALUE)

    @staticmethod
    def _build_category_choices() -> tuple[tuple[str, str], ...]:
        category_choices: list[tuple[str, str]] = [
            (LISTING_CATEGORY_ALL_VALUE, "All child categories"),
        ]

        categories = (
            Category.objects.select_related("parent_category")
            .filter(parent_category__isnull=False)
            .order_by("parent_category__name", "name")
        )

        for category in categories:
            parent_name: str = str(category.parent_category.name).strip()
            category_name: str = str(category.name).strip()
            category_choices.append((str(category.category_id), f"{parent_name} / {category_name}"))

        return tuple(category_choices)


MODERATION_LOG_ACTION_TYPE_ALL_VALUE: str = ""
MODERATION_LOG_ACTION_TYPE_BAN_USER_VALUE: str = "ban_user"
MODERATION_LOG_ACTION_TYPE_FREEZE_LISTING_VALUE: str = "freeze_listing"

MODERATION_LOG_TARGET_TYPE_ALL_VALUE: str = ""
MODERATION_LOG_TARGET_TYPE_USER_VALUE: str = "user"
MODERATION_LOG_TARGET_TYPE_LISTING_VALUE: str = "listing"

MODERATION_LOG_SORT_MOST_RECENT_VALUE: str = "most_recent"
MODERATION_LOG_SORT_OLDEST_VALUE: str = "oldest"
MODERATION_LOG_SORT_ACTOR_ASC_VALUE: str = "actor_asc"
MODERATION_LOG_SORT_ACTOR_DESC_VALUE: str = "actor_desc"
MODERATION_LOG_SORT_ACTION_ASC_VALUE: str = "action_asc"
MODERATION_LOG_SORT_ACTION_DESC_VALUE: str = "action_desc"
MODERATION_LOG_SORT_TARGET_ASC_VALUE: str = "target_asc"
MODERATION_LOG_SORT_TARGET_DESC_VALUE: str = "target_desc"


class ModerationLogFilterForm(forms.Form):
    search_email: forms.CharField = forms.CharField(
        label="Search by email",
        required=False,
        widget=forms.TextInput(
            attrs={
                "class": "form-control",
                "placeholder": "Search actor, reporter, or target email",
                "autocomplete": "off",
            }
        ),
    )
    moderation_action_type: forms.ChoiceField = forms.ChoiceField(
        label="Moderation action",
        required=False,
        choices=(
            (MODERATION_LOG_ACTION_TYPE_ALL_VALUE, "All actions"),
            (MODERATION_LOG_ACTION_TYPE_BAN_USER_VALUE, "Ban User"),
            (MODERATION_LOG_ACTION_TYPE_FREEZE_LISTING_VALUE, "Freeze Listing"),
        ),
        widget=forms.Select(attrs={"class": "form-select"}),
    )
    report_target_type: forms.ChoiceField = forms.ChoiceField(
        label="Report target type",
        required=False,
        choices=(
            (MODERATION_LOG_TARGET_TYPE_ALL_VALUE, "All target types"),
            (MODERATION_LOG_TARGET_TYPE_USER_VALUE, "User"),
            (MODERATION_LOG_TARGET_TYPE_LISTING_VALUE, "Listing"),
        ),
        widget=forms.Select(attrs={"class": "form-select"}),
    )
    sort_by: forms.ChoiceField = forms.ChoiceField(
        label="Sort by",
        required=False,
        choices=(
            (MODERATION_LOG_SORT_MOST_RECENT_VALUE, "Most Recent"),
            (MODERATION_LOG_SORT_OLDEST_VALUE, "Oldest"),
            (MODERATION_LOG_SORT_ACTOR_ASC_VALUE, "Actor (A to Z)"),
            (MODERATION_LOG_SORT_ACTOR_DESC_VALUE, "Actor (Z to A)"),
            (MODERATION_LOG_SORT_ACTION_ASC_VALUE, "Action (A to Z)"),
            (MODERATION_LOG_SORT_ACTION_DESC_VALUE, "Action (Z to A)"),
            (MODERATION_LOG_SORT_TARGET_ASC_VALUE, "Target (A to Z)"),
            (MODERATION_LOG_SORT_TARGET_DESC_VALUE, "Target (Z to A)"),
        ),
        initial=MODERATION_LOG_SORT_MOST_RECENT_VALUE,
        widget=forms.Select(attrs={"class": "form-select"}),
    )

    def __init__(self, *args: Any, **kwargs: Any) -> None:
        super().__init__(*args, **kwargs)

        self.helper = FormHelper(self)
        self.helper.form_method = "get"
        self.helper.form_tag = False

        if not self.is_bound:
            self.initial.setdefault("sort_by", MODERATION_LOG_SORT_MOST_RECENT_VALUE)


ADMINISTRATION_LOG_ACTION_TYPE_ALL_VALUE: str = ""
ADMINISTRATION_LOG_ACTION_TYPE_ADD_ROLE_VALUE: str = "add_role"
ADMINISTRATION_LOG_ACTION_TYPE_REMOVE_ROLE_VALUE: str = "remove_role"
ADMINISTRATION_LOG_ACTION_TYPE_BAN_USER_VALUE: str = "ban_user"
ADMINISTRATION_LOG_ACTION_TYPE_UNBAN_USER_VALUE: str = "unban_user"
ADMINISTRATION_LOG_ACTION_TYPE_FREEZE_LISTING_VALUE: str = "freeze_listing"
ADMINISTRATION_LOG_ACTION_TYPE_UNFREEZE_LISTING_VALUE: str = "unfreeze_listing"

ADMINISTRATION_LOG_TARGET_TYPE_ALL_VALUE: str = ""
ADMINISTRATION_LOG_TARGET_TYPE_USER_VALUE: str = "user"
ADMINISTRATION_LOG_TARGET_TYPE_LISTING_VALUE: str = "listing"

ADMINISTRATION_LOG_SORT_MOST_RECENT_VALUE: str = "most_recent"
ADMINISTRATION_LOG_SORT_OLDEST_VALUE: str = "oldest"
ADMINISTRATION_LOG_SORT_ACTOR_ASC_VALUE: str = "actor_asc"
ADMINISTRATION_LOG_SORT_ACTOR_DESC_VALUE: str = "actor_desc"
ADMINISTRATION_LOG_SORT_ACTION_ASC_VALUE: str = "action_asc"
ADMINISTRATION_LOG_SORT_ACTION_DESC_VALUE: str = "action_desc"
ADMINISTRATION_LOG_SORT_TARGET_ASC_VALUE: str = "target_asc"
ADMINISTRATION_LOG_SORT_TARGET_DESC_VALUE: str = "target_desc"


class AdministrationLogFilterForm(forms.Form):
    search_email: forms.CharField = forms.CharField(
        label="Search by email",
        required=False,
        widget=forms.TextInput(
            attrs={
                "class": "form-control",
                "placeholder": "Search actor or target email",
                "autocomplete": "off",
            }
        ),
    )
    administration_action_type: forms.ChoiceField = forms.ChoiceField(
        label="Administration action",
        required=False,
        choices=(
            (ADMINISTRATION_LOG_ACTION_TYPE_ALL_VALUE, "All actions"),
            (ADMINISTRATION_LOG_ACTION_TYPE_ADD_ROLE_VALUE, "Add Role"),
            (ADMINISTRATION_LOG_ACTION_TYPE_REMOVE_ROLE_VALUE, "Remove Role"),
            (ADMINISTRATION_LOG_ACTION_TYPE_BAN_USER_VALUE, "Ban User"),
            (ADMINISTRATION_LOG_ACTION_TYPE_UNBAN_USER_VALUE, "Unban User"),
            (ADMINISTRATION_LOG_ACTION_TYPE_FREEZE_LISTING_VALUE, "Freeze Listing"),
            (ADMINISTRATION_LOG_ACTION_TYPE_UNFREEZE_LISTING_VALUE, "Unfreeze Listing"),
        ),
        widget=forms.Select(attrs={"class": "form-select"}),
    )
    target_type: forms.ChoiceField = forms.ChoiceField(
        label="Target type",
        required=False,
        choices=(
            (ADMINISTRATION_LOG_TARGET_TYPE_ALL_VALUE, "All target types"),
            (ADMINISTRATION_LOG_TARGET_TYPE_USER_VALUE, "User"),
            (ADMINISTRATION_LOG_TARGET_TYPE_LISTING_VALUE, "Listing"),
        ),
        widget=forms.Select(attrs={"class": "form-select"}),
    )
    sort_by: forms.ChoiceField = forms.ChoiceField(
        label="Sort by",
        required=False,
        choices=(
            (ADMINISTRATION_LOG_SORT_MOST_RECENT_VALUE, "Most Recent"),
            (ADMINISTRATION_LOG_SORT_OLDEST_VALUE, "Oldest"),
            (ADMINISTRATION_LOG_SORT_ACTOR_ASC_VALUE, "Actor (A to Z)"),
            (ADMINISTRATION_LOG_SORT_ACTOR_DESC_VALUE, "Actor (Z to A)"),
            (ADMINISTRATION_LOG_SORT_ACTION_ASC_VALUE, "Action (A to Z)"),
            (ADMINISTRATION_LOG_SORT_ACTION_DESC_VALUE, "Action (Z to A)"),
            (ADMINISTRATION_LOG_SORT_TARGET_ASC_VALUE, "Target (A to Z)"),
            (ADMINISTRATION_LOG_SORT_TARGET_DESC_VALUE, "Target (Z to A)"),
        ),
        initial=ADMINISTRATION_LOG_SORT_MOST_RECENT_VALUE,
        widget=forms.Select(attrs={"class": "form-select"}),
    )

    def __init__(self, *args: Any, **kwargs: Any) -> None:
        super().__init__(*args, **kwargs)

        self.helper = FormHelper(self)
        self.helper.form_method = "get"
        self.helper.form_tag = False

        if not self.is_bound:
            self.initial.setdefault("sort_by", ADMINISTRATION_LOG_SORT_MOST_RECENT_VALUE)
