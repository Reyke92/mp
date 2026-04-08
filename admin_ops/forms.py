from __future__ import annotations

from typing import Any

from django import forms
from crispy_forms.helper import FormHelper

from catalog.models import Category


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
