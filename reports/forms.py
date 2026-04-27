from __future__ import annotations

from typing import Any

from django import forms
from django.core.exceptions import ValidationError
from crispy_forms.helper import FormHelper
from crispy_forms.layout import Layout, Submit

from .models import Report


class ReportForm(forms.Form):
    reason: forms.CharField = forms.CharField(
        label="Reason for reporting",
        max_length=500,
        widget=forms.Textarea(attrs={"rows": 5}),
    )

    def __init__(
        self,
        *args: Any,
        listing: Any = None,
        conversation: Any = None,
        **kwargs: Any,
    ) -> None:
        super().__init__(*args, **kwargs)

        self.listing = listing
        self.conversation = conversation

        self.helper = FormHelper(self)
        self.helper.form_method = "post"
        self.helper.layout = Layout(
            "reason",
            Submit("submit", "Submit Report", css_class="btn btn-danger w-100 mt-3"),
        )

    def clean_reason(self) -> str:
        reason = self.cleaned_data["reason"].strip()
        if not reason:
            raise forms.ValidationError("Please provide a reason for reporting.")
        return reason

    def clean(self) -> dict[str, Any]:
        cleaned_data = super().clean()

        if self.listing and self.conversation:
            raise ValidationError("A report may only target one item at a time.")

        if not self.listing and not self.conversation:
            raise ValidationError("A report must target either a listing or a conversation.")

        return cleaned_data

    def save(self, reporter: Any, status: Any) -> Report:
        report = Report(
            reporter_user=reporter,
            details=self.cleaned_data["reason"],
            status=status,
            listing=self.listing,
            conversation=self.conversation,
        )
        report.save()
        return report
