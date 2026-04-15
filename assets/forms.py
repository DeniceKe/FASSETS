from django import forms
from django.utils import timezone


class AssetRequestForm(forms.Form):
    message = forms.CharField(
        label="Reason for request",
        widget=forms.Textarea(attrs={"rows": 3}),
    )
    requested_start_at = forms.DateTimeField(
        label="When you need it",
        input_formats=["%Y-%m-%dT%H:%M"],
        widget=forms.DateTimeInput(attrs={"type": "datetime-local"}),
    )
    requested_end_at = forms.DateTimeField(
        label="When you will return it",
        input_formats=["%Y-%m-%dT%H:%M"],
        widget=forms.DateTimeInput(attrs={"type": "datetime-local"}),
    )
    usage_location = forms.CharField(
        label="Place of use",
        max_length=200,
    )

    def clean(self):
        cleaned_data = super().clean()
        requested_start_at = cleaned_data.get("requested_start_at")
        requested_end_at = cleaned_data.get("requested_end_at")

        if requested_start_at and requested_start_at < timezone.now():
            self.add_error("requested_start_at", "Start time must be in the future.")

        if requested_start_at and requested_end_at and requested_end_at <= requested_start_at:
            self.add_error("requested_end_at", "Return time must be later than the requested start time.")

        return cleaned_data


class AssetIssueReportForm(forms.Form):
    description = forms.CharField(
        label="Issue or maintenance request",
        widget=forms.Textarea(attrs={"rows": 3}),
    )
