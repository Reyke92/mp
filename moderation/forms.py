from __future__ import annotations

from crispy_forms.helper import FormHelper
from django import forms
from typing import Any

# Status filter values
QUEUE_STATUS_ALL_VALUE = ""
QUEUE_STATUS_RECIEVED_VALUE = "received"
QUEUE_STATUS_RESOLVED_VALUE = "resolved"

# Type filter values
QUEUE_TYPE_ALL_VALUE = ""
QUEUE_TYPE_LISTING_VALUE = "listing"
QUEUE_TYPE_CONVERSATION_VALUE = "conversation"

# Sort values
QUEUE_SORT_OLDEST_OPEN_VALUE = "oldest_open"
QUEUE_SORT_MOST_RECENT_VALUE = "most_recent"

class ModerationQueueFilterForm(forms.Form):
    search_email = forms.CharField(
        label="Search by reporter's email",
        required=False,
        widget=forms.TextInput(
            attrs={
                "class": "form-control",
                "placeholder": "Search by reporter's email",
            }
        ),
    )

    report_status = forms.ChoiceField(
        label="Report Status",
        required=False,
        choices=(
            (QUEUE_STATUS_ALL_VALUE, "All Statuses"),
            (QUEUE_STATUS_RECIEVED_VALUE, "Received"),
            (QUEUE_STATUS_RESOLVED_VALUE, "Resolved"),
        ),
        initial=QUEUE_STATUS_RECIEVED_VALUE,
        widget=forms.Select(attrs={"class": "form-select"}),
    )

    report_type = forms.ChoiceField(
        label="Report Type",
        required=False,
        choices=(
            (QUEUE_TYPE_ALL_VALUE, "All Types"),
            (QUEUE_TYPE_LISTING_VALUE, "Listing"),
            (QUEUE_TYPE_CONVERSATION_VALUE, "Conversation"),
        ),
        widget=forms.Select(attrs={"class": "form-select"}),
    )

    sort_by = forms.ChoiceField(
        label="Sort By",
        required=False,
        choices=(
            (QUEUE_SORT_OLDEST_OPEN_VALUE, "Oldest Open"),
            (QUEUE_SORT_MOST_RECENT_VALUE, "Most Recent"),
        ),
        initial=QUEUE_SORT_OLDEST_OPEN_VALUE,
        widget=forms.Select(attrs={"class": "form-select"}),
    )

    def __init__(self, *args: Any, **kwargs: Any):
        super().__init__(*args, **kwargs)
        self.helper = FormHelper()
        self.helper.form_method = "get"
        self.helper.form_tag = False

        if not self.is_bound:
            self.initial.setdefault("report_status", QUEUE_STATUS_RECIEVED_VALUE)
            self.initial.setdefault("sort_by", QUEUE_SORT_OLDEST_OPEN_VALUE)
