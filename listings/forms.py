from __future__ import annotations

from dataclasses import dataclass
from decimal import Decimal
from typing import Any, Iterable

from crispy_forms.helper import FormHelper
from django import forms
from django.core.exceptions import ValidationError
from django.core.validators import MinValueValidator

from catalog.models import AllowedAttributeValue, Attribute, Category, ItemCondition
from core.models import City, State
from core.validators.images import validate_uploaded_image


DESCRIPTION_MIN_LENGTH: int = 20
DESCRIPTION_MAX_LENGTH: int = 4000
TITLE_MAX_LENGTH: int = 255
PRICE_MAX_DIGITS: int = 12
PRICE_DECIMAL_PLACES: int = 2


@dataclass(slots=True)
class ListingAttributeFieldGroup:
    attribute_id: int
    attribute_key: str
    value_type_name: str
    label: str
    field_names: list[str]


class MultipleFileInput(forms.ClearableFileInput):
    allow_multiple_selected = True


class MultipleFileField(forms.FileField):
    widget = MultipleFileInput

    def clean(self, data: Any, initial: Any | None = None) -> list[Any]:
        if data in self.empty_values:
            if self.required:
                raise ValidationError(self.error_messages["required"], code="required")
            return []

        files: list[Any] = list(data) if isinstance(data, (list, tuple)) else [data]
        cleaned_files: list[Any] = []
        errors: list[ValidationError] = []

        for uploaded_file in files:
            try:
                cleaned_file: Any = super().clean(uploaded_file, initial)
                validate_uploaded_image(cleaned_file)
                cleaned_files.append(cleaned_file)
            except ValidationError as exc:
                errors.extend(exc.error_list)

        if errors:
            raise ValidationError(errors)

        return cleaned_files


class CreateListingForm(forms.Form):
    title: forms.CharField = forms.CharField(
        label="Listing title",
        max_length=TITLE_MAX_LENGTH,
        widget=forms.TextInput(
            attrs={
                "placeholder": "Enter a clear title",
                "autocomplete": "off",
            }
        ),
    )
    price_amount: forms.DecimalField = forms.DecimalField(
        label="Price",
        min_value=Decimal("0.00"),
        max_digits=PRICE_MAX_DIGITS,
        decimal_places=PRICE_DECIMAL_PLACES,
        widget=forms.NumberInput(
            attrs={
                "placeholder": "0.00",
                "step": "0.01",
                "min": "0",
                "inputmode": "decimal",
            }
        ),
    )
    category: forms.TypedChoiceField = forms.TypedChoiceField(
        label="Category",
        required=True,
        choices=(),
        coerce=int,
        empty_value=None,
    )
    condition: forms.TypedChoiceField = forms.TypedChoiceField(
        label="Condition",
        required=True,
        choices=(),
        coerce=int,
        empty_value=None,
    )
    city_name: forms.CharField = forms.CharField(
        label="City",
        max_length=50,
        widget=forms.TextInput(
            attrs={
                "placeholder": "City",
                "autocomplete": "address-level2",
                "list": "city-suggestions",
            }
        ),
    )
    state: forms.TypedChoiceField = forms.TypedChoiceField(
        label="State",
        required=True,
        choices=(),
        coerce=int,
        empty_value=None,
        widget=forms.Select(attrs={"autocomplete": "address-level1"}),
    )
    description: forms.CharField = forms.CharField(
        label="Description",
        min_length=DESCRIPTION_MIN_LENGTH,
        max_length=DESCRIPTION_MAX_LENGTH,
        widget=forms.Textarea(
            attrs={
                "rows": 7,
                "placeholder": "Describe the item, condition, included accessories, and anything a buyer should know.",
            }
        ),
    )
    images: MultipleFileField = MultipleFileField(
        label="Images",
        required=False,
        widget=MultipleFileInput(
            attrs={
                "accept": ".jpg,.jpeg,.png,.webp",
                "multiple": True,
            }
        ),
    )

    def __init__(self, *args: Any, **kwargs: Any) -> None:
        selected_category_id: int | None = kwargs.pop("selected_category_id", None)
        super().__init__(*args, **kwargs)

        self.attribute_field_groups: list[ListingAttributeFieldGroup] = []

        self.fields["category"].choices = self._build_leaf_category_choices()
        self.fields["condition"].choices = self._build_condition_choices()
        self.fields["state"].choices = self._build_state_choices()

        if selected_category_id is None:
            selected_category_id = self._get_selected_category_id()

        if selected_category_id is not None:
            self._add_dynamic_attribute_fields(selected_category_id)

        self._add_bootstrap_classes()

        self.helper = FormHelper(self)
        self.helper.form_tag = False
        self.helper.form_method = "post"
        self.helper.attrs = {
            "id": "listing-editor-form",
        }

    def clean_title(self) -> str:
        title: str = str(self.cleaned_data["title"]).strip()
        if title == "":
            raise ValidationError("Listing title is required.")
        return title

    def clean_city_name(self) -> str:
        city_name: str = str(self.cleaned_data["city_name"]).strip()
        if city_name == "":
            raise ValidationError("City is required.")
        return city_name

    def clean_description(self) -> str:
        description: str = str(self.cleaned_data["description"]).strip()
        if description == "":
            raise ValidationError("Description is required.")
        return description

    def clean(self) -> dict[str, Any]:
        cleaned_data: dict[str, Any] = super().clean()

        category_id: int | None = cleaned_data.get("category")
        if category_id is not None and Category.objects.filter(parent_category_id=category_id).exists():
            self.add_error(
                "category",
                "Choose a child category so the listing has a precise category and the correct attribute set.",
            )

        state_id: int | None = cleaned_data.get("state")
        city_name: str = str(cleaned_data.get("city_name") or "").strip()
        if state_id is not None and city_name != "":
            city: City | None = (
                City.objects.select_related("state")
                .filter(state_id=state_id, city_name__iexact=city_name)
                .first()
            )
            if city is None:
                self.add_error("city_name", "Choose a city that exists in the selected state.")
            else:
                cleaned_data["resolved_city"] = city
                cleaned_data["city_name"] = str(city.city_name)

        for group in self.attribute_field_groups:
            value_type_name: str = group.value_type_name.lower()
            if value_type_name not in {"int", "integer", "decimal"}:
                continue

            field_name: str = group.field_names[0]
            value: Any = cleaned_data.get(field_name)
            if value is None:
                continue

            if value_type_name in {"int", "integer"} and int(value) < 0:
                self.add_error(field_name, f"{group.label} cannot be negative.")
            if value_type_name == "decimal" and Decimal(value) < Decimal("0"):
                self.add_error(field_name, f"{group.label} cannot be negative.")

        return cleaned_data

    def _get_selected_category_id(self) -> int | None:
        raw_value: Any = self.data.get("category") if self.is_bound else self.initial.get("category")
        return self._parse_optional_db_id(raw_value)

    def _build_leaf_category_choices(self) -> list[tuple[Any, str]]:
        category_rows: list[tuple[int, str, int | None]] = list(
            Category.objects.values_list("category_id", "name", "parent_category_id")
        )
        category_name_by_id: dict[int, str] = {
            int(category_id): str(name).strip()
            for category_id, name, _parent_category_id in category_rows
        }
        parent_ids_with_children: set[int] = {
            int(parent_category_id)
            for _category_id, _name, parent_category_id in category_rows
            if parent_category_id is not None
        }

        leaf_rows: list[tuple[int, str]] = []
        for category_id, name, parent_category_id in category_rows:
            parsed_category_id: int = int(category_id)
            if parsed_category_id in parent_ids_with_children:
                continue

            label: str = str(name).strip()
            if parent_category_id is not None:
                parent_name: str = category_name_by_id.get(int(parent_category_id), "")
                if parent_name != "":
                    label = f"{parent_name} › {label}"
            leaf_rows.append((parsed_category_id, label))

        leaf_rows = sorted(leaf_rows, key=lambda row: row[1].lower())
        choices: list[tuple[Any, str]] = [("", "Select a category")]
        for category_id, label in leaf_rows:
            choices.append((category_id, label))

        return choices

    def _build_condition_choices(self) -> list[tuple[Any, str]]:
        choices: list[tuple[Any, str]] = [("", "Select condition")]
        for condition in ItemCondition.objects.order_by("condition_name"):
            choices.append((condition.condition_id, condition.condition_name))
        return choices

    def _build_state_choices(self) -> list[tuple[Any, str]]:
        choices: list[tuple[Any, str]] = [("", "Select state")]
        for state in State.objects.order_by("state_name"):
            choices.append((state.state_id, state.state_name))
        return choices

    def _add_dynamic_attribute_fields(self, category_id: int) -> None:
        attributes: Iterable[Attribute] = (
            Attribute.objects.select_related("value_type")
            .filter(category_id=category_id)
            .order_by("attribute_key")
        )

        for attribute in attributes:
            attribute_id: int = int(attribute.attribute_id)
            attribute_key: str = str(attribute.attribute_key)
            value_type_name: str = str(attribute.value_type.value_type_name).strip().lower()
            label: str = self._labelize_attribute_key(attribute_key)
            field_name: str = f"attr_{attribute_id}_value"

            if value_type_name in {"int", "integer"}:
                self.fields[field_name] = forms.IntegerField(
                    label=label,
                    required=False,
                    validators=[MinValueValidator(0)],
                    widget=forms.NumberInput(attrs={"placeholder": label}),
                )
            elif value_type_name == "decimal":
                self.fields[field_name] = forms.DecimalField(
                    label=label,
                    required=False,
                    min_value=Decimal("0"),
                    max_digits=18,
                    decimal_places=6,
                    widget=forms.NumberInput(attrs={"placeholder": label, "step": "0.000001"}),
                )
            elif value_type_name == "datetime":
                self.fields[field_name] = forms.DateField(
                    label=label,
                    required=False,
                    widget=forms.DateInput(attrs={"type": "date"}),
                )
            elif value_type_name in {"bool", "boolean"}:
                self.fields[field_name] = forms.TypedChoiceField(
                    label=label,
                    required=False,
                    choices=[("", "Not set"), ("false", "No"), ("true", "Yes")],
                    coerce=self._coerce_optional_bool,
                    empty_value=None,
                    widget=forms.RadioSelect(
                        attrs={
                            "class": "btn-check",
                            "autocomplete": "off",
                        }
                    ),
                )
            else:
                allowed_value_choices: list[tuple[Any, str]] = [("", f"Select {label.lower()}")]
                for allowed_value in AllowedAttributeValue.objects.filter(attribute_id=attribute_id).order_by("allowed_value_label"):
                    allowed_value_choices.append((allowed_value.allowed_value_id, allowed_value.allowed_value_label))

                self.fields[field_name] = forms.TypedChoiceField(
                    label=label,
                    required=False,
                    choices=allowed_value_choices,
                    coerce=int,
                    empty_value=None,
                )

            self.attribute_field_groups.append(
                ListingAttributeFieldGroup(
                    attribute_id=attribute_id,
                    attribute_key=attribute_key,
                    value_type_name=value_type_name,
                    label=label,
                    field_names=[field_name],
                )
            )

    def _add_bootstrap_classes(self) -> None:
        for field_name, field in self.fields.items():
            css_class: str = "form-control"
            if isinstance(field.widget, (forms.Select, forms.SelectMultiple)):
                css_class = "form-select"
            elif isinstance(field.widget, forms.RadioSelect):
                css_class = ""
            elif isinstance(field.widget, forms.CheckboxInput):
                css_class = "form-check-input"

            existing_css_class: str = str(field.widget.attrs.get("class", "")).strip()
            if css_class != "":
                field.widget.attrs["class"] = f"{existing_css_class} {css_class}".strip()
            else:
                field.widget.attrs["class"] = existing_css_class
            field.widget.attrs.setdefault("id", f"id_{field_name}")

    @staticmethod
    def _labelize_attribute_key(attribute_key: str) -> str:
        return attribute_key.replace("_", " ").strip().title()

    @staticmethod
    def _coerce_optional_bool(raw_value: str) -> bool | None:
        normalized_value: str = str(raw_value).strip().lower()
        if normalized_value == "":
            return None
        return normalized_value == "true"

    @staticmethod
    def _parse_optional_db_id(raw_value: Any) -> int | None:
        if raw_value in {None, ""}:
            return None
        try:
            return int(raw_value)
        except (TypeError, ValueError):
            return None
