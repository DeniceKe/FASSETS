from django import forms
from django.contrib.auth import get_user_model
from django.contrib.auth.forms import UserCreationForm
from assets.models import Location

from .models import (
    Department,
    Profile,
    USER_TYPE_STAFF,
    USER_TYPE_STUDENT,
    USER_TYPE_CHOICES,
)

User = get_user_model()


class SignUpForm(UserCreationForm):
    first_name = forms.CharField(max_length=150, required=True)
    last_name = forms.CharField(max_length=150, required=True)
    email = forms.EmailField(required=True)
    phone_number = forms.CharField(max_length=30, required=True)
    user_type = forms.ChoiceField(choices=USER_TYPE_CHOICES, required=True)
    registration_number = forms.CharField(max_length=50, required=False)
    employee_id = forms.CharField(max_length=50, required=False, label="Staff ID")
    department = forms.ModelChoiceField(queryset=Department.objects.select_related("faculty").order_by("name"), required=True)

    class Meta(UserCreationForm.Meta):
        model = User
        fields = (
            "username",
            "first_name",
            "last_name",
            "email",
            "phone_number",
            "user_type",
            "registration_number",
            "employee_id",
            "department",
            "password1",
            "password2",
        )

    def clean(self):
        cleaned_data = super().clean()
        user_type = cleaned_data.get("user_type")
        registration_number = cleaned_data.get("registration_number", "").strip()
        employee_id = cleaned_data.get("employee_id", "").strip()

        if user_type == USER_TYPE_STUDENT and not registration_number:
            self.add_error("registration_number", "Registration number is required for students.")

        if user_type == USER_TYPE_STAFF and not employee_id:
            self.add_error("employee_id", "Staff ID is required for staff accounts.")

        return cleaned_data

    def save(self, commit=True):
        user = super().save(commit=False)
        user.first_name = self.cleaned_data["first_name"]
        user.last_name = self.cleaned_data["last_name"]
        user.email = self.cleaned_data["email"]
        if commit:
            user.save()
            profile = user.profile
            profile.phone_number = self.cleaned_data["phone_number"]
            profile.user_type = self.cleaned_data["user_type"]
            profile.registration_number = self.cleaned_data["registration_number"]
            profile.employee_id = self.cleaned_data["employee_id"]
            profile.department = self.cleaned_data["department"]
            profile.save()
        return user


class ProfilePhotoForm(forms.ModelForm):
    class Meta:
        model = Profile
        fields = ("photo",)


class AccountProfileForm(forms.ModelForm):
    first_name = forms.CharField(max_length=150, required=True)
    last_name = forms.CharField(max_length=150, required=True)
    email = forms.EmailField(required=True)

    class Meta:
        model = Profile
        fields = (
            "first_name",
            "last_name",
            "email",
            "phone_number",
            "staff_location",
            "photo",
        )

    def __init__(self, *args, **kwargs):
        self.user = kwargs.pop("user")
        super().__init__(*args, **kwargs)
        self.fields["phone_number"].required = True
        self.fields["photo"].required = False
        self.fields["staff_location"].required = False
        self.fields["staff_location"].label = "Office / Lab"

        self.fields["first_name"].initial = self.user.first_name
        self.fields["last_name"].initial = self.user.last_name
        self.fields["email"].initial = self.user.email

        department = getattr(self.instance, "department", None)
        if department:
            self.fields["staff_location"].queryset = Location.objects.filter(department=department).order_by("building", "room")
        else:
            self.fields["staff_location"].queryset = Location.objects.none()

        if getattr(self.instance, "user_type", "") != USER_TYPE_STAFF:
            self.fields.pop("staff_location")

    def save(self, commit=True):
        profile = super().save(commit=False)
        self.user.first_name = self.cleaned_data["first_name"]
        self.user.last_name = self.cleaned_data["last_name"]
        self.user.email = self.cleaned_data["email"]

        if commit:
            self.user.save(update_fields=["first_name", "last_name", "email"])
            profile.save()

        return profile
