from __future__ import annotations

from typing import Any

from crispy_forms.helper import FormHelper
from django import forms

from moderation.models import ModerationActionType

# Queue status filter values.
QUEUE_STATUS_ALL_VALUE = ""
QUEUE_STATUS_RECEIVED_VALUE = "received"
QUEUE_STATUS_RESOLVED_VALUE = "resolved"

# Queue target-type filter values.
QUEUE_TYPE_ALL_VALUE = ""
QUEUE_TYPE_LISTING_VALUE = "listing"
QUEUE_TYPE_CONVERSATION_VALUE = "conversation"

# Queue sort values.
QUEUE_SORT_OLDEST_OPEN_VALUE = "oldest_open"
QUEUE_SORT_MOST_RECENT_VALUE = "most_recent"

DISPOSITION_ACTION_NONE_VALUE = ""
FREEZE_LISTING_ACTION_NAME = "FreezeListing"
BAN_USER_ACTION_NAME = "BanUser"


class ModerationQueueFilterForm(forms.Form):
    search_email = forms.CharField(
        label="Search by email",
        required=False,
        widget=forms.TextInput(
            attrs={
                "class": "form-control",
                "placeholder": "Reporter or target email",
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
        label="Target Type",
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

    def __init__(self, *args: Any, **kwargs: Any) -> None:
        super().__init__(*args, **kwargs)
        self.helper = FormHelper()
        self.helper.form_method = "get"
        self.helper.form_tag = False

        if not self.is_bound:
            self.initial.setdefault("report_status", QUEUE_STATUS_RECEIVED_VALUE)
            self.initial.setdefault("sort_by", QUEUE_SORT_OLDEST_OPEN_VALUE)

    def clean(self) -> dict[str, Any]:
        cleaned_data = super().clean()

        # Preserve the queue's default workflow when callers submit only a subset
        # of query-string controls, such as changing sort order without explicitly
        # sending the report-status field.
        if "report_status" not in self.data:
            cleaned_data["report_status"] = QUEUE_STATUS_RECEIVED_VALUE
        if "sort_by" not in self.data:
            cleaned_data["sort_by"] = QUEUE_SORT_OLDEST_OPEN_VALUE

        return cleaned_data


class ReportDispositionForm(forms.Form):
    action_type = forms.ChoiceField(
        label="Action to record",
        required=False,
        widget=forms.Select(attrs={"class": "form-select"}),
    )

    notes = forms.CharField(
        label="Notes",
        required=False,
        widget=forms.Textarea(
            attrs={
                "class": "form-control",
                "rows": 4,
                "placeholder": "Notes visible only to staff.",
            }
        ),
    )

    def __init__(
        self,
        *args: Any,
        allowed_action_names: list[str] | tuple[str, ...] | None = None,
        **kwargs: Any,
    ) -> None:
        super().__init__(*args, **kwargs)

        self.allowed_action_names = tuple(allowed_action_names or ())
        self.helper = FormHelper(self)
        self.helper.form_tag = False
        self.fields["action_type"].choices = self._build_action_choices()

    def _build_action_choices(self) -> tuple[tuple[str, str], ...]:
        choices: list[tuple[str, str]] = [(DISPOSITION_ACTION_NONE_VALUE, "Select an action...")]
        queryset = ModerationActionType.objects.all().order_by("action_type_id")
        if self.allowed_action_names:
            queryset = queryset.filter(action_type_name__in=self.allowed_action_names)
        for action_type in queryset:
            choices.append((str(action_type.action_type_id), str(action_type.action_type_name)))
        return tuple(choices)

    def clean(self) -> dict[str, Any]:
        cleaned_data = super().clean()
        action_type_value = str(cleaned_data.get("action_type") or "").strip()
        if not action_type_value:
            raise forms.ValidationError("Choose a moderation action to record, or use Dismiss Report.")
        return cleaned_data
