from __future__ import annotations

from crispy_forms.helper import FormHelper
from django import forms
from moderation.models import ModerationActionType
from reports.models import ReportStatus
from typing import Any

# Status filter values
QUEUE_STATUS_ALL_VALUE = ""
QUEUE_STATUS_RECEIVED_VALUE = "received"
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
            (QUEUE_STATUS_RECEIVED_VALUE, "Received"),
            (QUEUE_STATUS_RESOLVED_VALUE, "Resolved"),
        ),
        initial=QUEUE_STATUS_RECEIVED_VALUE,
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
            self.initial.setdefault("report_status", QUEUE_STATUS_RECEIVED_VALUE)
            self.initial.setdefault("sort_by", QUEUE_SORT_OLDEST_OPEN_VALUE)

DISPOSITION_ACTION_NONE_VALUE = ""

class ReportDispositionForm(forms.Form):
    report_status = forms.ChoiceField(
        label="Report Status",
        required=True,
        widget=forms.Select(attrs={"class": "form-select"})
    )

    action_type = forms.ChoiceField(
        label="Moderation Action Type",
        required=False,
        widget=forms.Select(attrs={"class": "form-select"})
    )

    notes = forms.CharField(
        label="Notes",
        required=False,
        widget=forms.Textarea(
            attrs={
                "class": "form-control",
                "rows": 4,
                "placeholder": "Notes (visible only to staff)"
            }
        )
    )

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        
        self.helper = FormHelper(self)
        self.helper.form_tag = False
        self.fields["report_status"].choices = self.build_status_choices()
        self.fields["action_type"].choices = self.build_action_choices()

    @staticmethod
    def build_status_choices():
        choices = [("", "Select...")]
        terminal_statuses = ReportStatus.objects.exclude(status_name="Received").order_by("status_id")
        for status in terminal_statuses:
            choices.append((str(status.status_id), str(status.status_name)))
        return tuple(choices)
    
    @staticmethod
    def build_action_choices():
        choices = [(DISPOSITION_ACTION_NONE_VALUE, "No Action (dismiss)")]
        for action_type in ModerationActionType.objects.all().order_by("action_type_id"):
            choices.append((str(action_type.action_type_id), str(action_type.action_type_name)))
        return tuple(choices)
