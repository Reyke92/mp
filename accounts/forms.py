from __future__ import annotations

from typing import Any

from django import forms
from django.contrib.auth import get_user_model
from django.contrib.auth.password_validation import validate_password
from django.core.exceptions import ValidationError

from crispy_forms.helper import FormHelper
from crispy_forms.layout import Layout, Row, Column, Submit

from core.validators.images import validate_uploaded_image


US_STATES: list[tuple[str, str]] = [
    ("Alabama", "Alabama"),
    ("Alaska", "Alaska"),
    ("Arizona", "Arizona"),
    ("Arkansas", "Arkansas"),
    ("California", "California"),
    ("Colorado", "Colorado"),
    ("Connecticut", "Connecticut"),
    ("Delaware", "Delaware"),
    ("Florida", "Florida"),
    ("Georgia", "Georgia"),
    ("Hawaii", "Hawaii"),
    ("Idaho", "Idaho"),
    ("Illinois", "Illinois"),
    ("Indiana", "Indiana"),
    ("Iowa", "Iowa"),
    ("Kansas", "Kansas"),
    ("Kentucky", "Kentucky"),
    ("Louisiana", "Louisiana"),
    ("Maine", "Maine"),
    ("Maryland", "Maryland"),
    ("Massachusetts", "Massachusetts"),
    ("Michigan", "Michigan"),
    ("Minnesota", "Minnesota"),
    ("Mississippi", "Mississippi"),
    ("Missouri", "Missouri"),
    ("Montana", "Montana"),
    ("Nebraska", "Nebraska"),
    ("Nevada", "Nevada"),
    ("New Hampshire", "New Hampshire"),
    ("New Jersey", "New Jersey"),
    ("New Mexico", "New Mexico"),
    ("New York", "New York"),
    ("North Carolina", "North Carolina"),
    ("North Dakota", "North Dakota"),
    ("Ohio", "Ohio"),
    ("Oklahoma", "Oklahoma"),
    ("Oregon", "Oregon"),
    ("Pennsylvania", "Pennsylvania"),
    ("Rhode Island", "Rhode Island"),
    ("South Carolina", "South Carolina"),
    ("South Dakota", "South Dakota"),
    ("Tennessee", "Tennessee"),
    ("Texas", "Texas"),
    ("Utah", "Utah"),
    ("Vermont", "Vermont"),
    ("Virginia", "Virginia"),
    ("Washington", "Washington"),
    ("West Virginia", "West Virginia"),
    ("Wisconsin", "Wisconsin"),
    ("Wyoming", "Wyoming"),
]


class RegisterForm(forms.Form):
    email: forms.EmailField = forms.EmailField(
        label="Email",
        max_length=254,
        widget=forms.EmailInput(attrs={"autocomplete": "email"}),
    )

    first_name: forms.CharField = forms.CharField(
        label="First name",
        max_length=150,
        widget=forms.TextInput(attrs={"autocomplete": "given-name"}),
    )
    last_name: forms.CharField = forms.CharField(
        label="Last name",
        max_length=150,
        widget=forms.TextInput(attrs={"autocomplete": "family-name"}),
    )

    password1: forms.CharField = forms.CharField(
        label="Password",
        strip=False,
        widget=forms.PasswordInput(attrs={"autocomplete": "new-password"}),
    )
    password2: forms.CharField = forms.CharField(
        label="Confirm password",
        strip=False,
        widget=forms.PasswordInput(attrs={"autocomplete": "new-password"}),
    )

    city_name: forms.CharField = forms.CharField(
        label="City",
        max_length=80,
        widget=forms.TextInput(attrs={"autocomplete": "address-level2"}),
    )
    state_name: forms.ChoiceField = forms.ChoiceField(
        label="State",
        choices=US_STATES,
        widget=forms.Select(attrs={"autocomplete": "address-level1"}),
    )

    def __init__(self, *args: Any, **kwargs: Any) -> None:
        super().__init__(*args, **kwargs)

        # Crispy helper (Bootstrap 5)
        self.helper = FormHelper(self)
        self.helper.form_method = "post"
        self.helper.layout = Layout(
            "email",
            Row(
                Column("first_name", css_class="col-md-6"),
                Column("last_name", css_class="col-md-6"),
                css_class="g-3",
            ),
            "password1",
            "password2",
            Row(
                Column("city_name", css_class="col-md-6"),
                Column("state_name", css_class="col-md-6"),
                css_class="g-3",
            ),
            Submit("submit", "Register", css_class="btn btn-primary w-100 mt-3"),
        )

    def clean_first_name(self) -> str:
        first_name: str = self.cleaned_data["first_name"].strip()
        if not first_name.isalpha():
            raise ValidationError("First name may only contain alphabetical characters.")
        return first_name

    def clean_last_name(self) -> str:
        last_name: str = self.cleaned_data["last_name"].strip()
        if not last_name.isalpha():
            raise ValidationError("Last name may only contain alphabetical characters.")
        return last_name

    def clean_city_name(self) -> str:
        city_name: str = self.cleaned_data["city_name"].strip()
        if not city_name:
            raise ValidationError("City is required.")
        return city_name
    
    def clean_email(self) -> str:
        email: str = self.cleaned_data["email"].strip().lower()
        UserModel = get_user_model()

        # Most projects keep email unique. If yours doesn't, remove this check.
        if UserModel.objects.filter(email=email).exists():
            raise ValidationError("An account with that email already exists.")
        return email

    def clean(self) -> dict[str, Any]:
        cleaned_data: dict[str, Any] = super().clean()
        password1: str | None = cleaned_data.get("password1")
        password2: str | None = cleaned_data.get("password2")

        if password1 and password2 and password1 != password2:
            self.add_error("password2", "Passwords do not match.")
            return cleaned_data

        # Run Django password validators (length, common password, etc.)
        if password1:
            try:
                validate_password(password1)
            except ValidationError as exc:
                self.add_error("password1", exc)

        return cleaned_data

    def save(self) -> Any:
        """
        Creates the user. If you also store city/state in a profile model,
        do it in the view right after this call (see below).
        """
        UserModel = get_user_model()

        email: str = self.cleaned_data["email"]
        password: str = self.cleaned_data["password1"]
        first_name: str = self.cleaned_data["first_name"]
        last_name: str = self.cleaned_data["last_name"]

        # If you're using Django's default User model, it requires username.
        # Using email as username is a common simple approach.
        user = UserModel.objects.create_user(
            username=email,
            email=email,
            password=password,
            first_name=first_name,
            last_name=last_name
        )
        return user


class LoginForm(forms.Form):
    email: forms.EmailField = forms.EmailField(
        label="Email",
        max_length=254,
        widget=forms.EmailInput(attrs={"autocomplete": "email"}),
    )
    password: forms.CharField = forms.CharField(
        label="Password",
        strip=False,
        widget=forms.PasswordInput(attrs={"autocomplete": "current-password"}),
    )

    def __init__(self, *args: Any, **kwargs: Any) -> None:
        super().__init__(*args, **kwargs)

        self.helper = FormHelper(self)
        self.helper.form_method = "post"
        self.helper.layout = Layout(
            "email",
            "password",
            Submit("submit", "Log In", css_class="btn btn-primary w-100 mt-3"),
        )


class ProfileForm(forms.Form):
    first_name: forms.CharField = forms.CharField(
        label="First name",
        max_length=150,
        widget=forms.TextInput(attrs={"autocomplete": "given-name"}),
    )
    last_name: forms.CharField = forms.CharField(
        label="Last name",
        max_length=150,
        widget=forms.TextInput(attrs={"autocomplete": "family-name"}),
    )

    bio: forms.CharField = forms.CharField(
        label="Bio",
        required=False,
        max_length=80,
        widget=forms.Textarea(
            attrs={
                "rows": 5,
                "placeholder": "Short bio... (a message you want other users to see)",
            }
        ),
    )

    avatar: forms.ImageField = forms.ImageField(
        label="Avatar",
        required=False,
        validators=[validate_uploaded_image],
    )

    city_name: forms.CharField = forms.CharField(
        label="City",
        max_length=80,
        widget=forms.TextInput(attrs={"autocomplete": "address-level2"}),
    )
    state_name: forms.ChoiceField = forms.ChoiceField(
        label="State",
        choices=US_STATES,
        widget=forms.Select(attrs={"autocomplete": "address-level1"}),
    )

    def __init__(self, *args: Any, **kwargs: Any) -> None:
        super().__init__(*args, **kwargs)

        self.helper = FormHelper(self)
        self.helper.form_method = "post"
        self.helper.attrs = {"enctype": "multipart/form-data"}
        self.helper.layout = Layout(
            Row(
                Column("first_name", css_class="col-md-6"),
                Column("last_name", css_class="col-md-6"),
                css_class="g-3",
            ),
            "bio",
            "avatar",
            Row(
                Column("city_name", css_class="col-md-6"),
                Column("state_name", css_class="col-md-6"),
                css_class="g-3",
            ),
            # Not including this submit button - there will already be one in the template.
            # Preserving this in case we change our minds.
            #Submit("submit", "Save Changes", css_class="btn btn-primary w-100 mt-3"),
        )

    def clean_first_name(self) -> str:
        first_name: str = self.cleaned_data["first_name"].strip()
        if not first_name.isalpha():
            raise ValidationError("First name may only contain alphabetical characters.")
        return first_name

    def clean_last_name(self) -> str:
        last_name: str = self.cleaned_data["last_name"].strip()
        if not last_name.isalpha():
            raise ValidationError("Last name may only contain alphabetical characters.")
        return last_name

    def clean_bio(self) -> str:
        bio: str = self.cleaned_data.get("bio", "").strip()
        return bio

    def clean_city_name(self) -> str:
        city_name: str = self.cleaned_data["city_name"].strip()
        if not city_name:
            raise ValidationError("City is required.")
        return city_name
