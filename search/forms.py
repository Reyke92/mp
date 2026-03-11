from __future__ import annotations

from dataclasses import dataclass
from decimal import Decimal
from typing import Any

from django import forms

from catalog.models import AllowedAttributeValue, Attribute, ItemCondition
from catalog.utils import get_category


SORT_CHOICES: list[tuple[str, str]] = [
    ("most_relevant", "Most relevant"),
    ("newest", "Newest"),
    ("closest", "Closest to me"),
    ("price_low", "Price low to high"),
    ("price_high", "Price high to low"),
]


@dataclass(slots=True)
class DynamicAttributeFieldGroup:
    attribute_id: int
    attribute_key: str
    value_type_name: str
    label: str
    field_names: list[str]


class ListingSearchForm(forms.Form):
    q: forms.CharField = forms.CharField(
        label="Keyword",
        required=False,
        max_length=255,
        widget=forms.TextInput(
            attrs={
                "placeholder": "Search listings by title or city",
            }
        ),
    )
    category: forms.TypedChoiceField = forms.TypedChoiceField(
        label="Category",
        required=False,
        choices=(),
        coerce=int,
        empty_value=None,
    )
    condition: forms.TypedChoiceField = forms.TypedChoiceField(
        label="Condition",
        required=False,
        choices=(),
        coerce=int,
        empty_value=None,
    )
    min_price: forms.DecimalField = forms.DecimalField(
        label="Minimum price",
        required=False,
        min_value=Decimal("0.00"),
        max_digits=12,
        decimal_places=2,
        widget=forms.NumberInput(
            attrs={
                "placeholder": "0.00",
                "step": "0.01",
                "min": "0",
            }
        ),
    )
    max_price: forms.DecimalField = forms.DecimalField(
        label="Maximum price",
        required=False,
        min_value=Decimal("0.00"),
        max_digits=12,
        decimal_places=2,
        widget=forms.NumberInput(
            attrs={
                "placeholder": "0.00",
                "step": "0.01",
                "min": "0",
            }
        ),
    )
    distance_miles: forms.IntegerField = forms.IntegerField(
        label="Distance (miles)",
        required=False,
        min_value=1,
        widget=forms.NumberInput(
            attrs={
                "placeholder": "25",
                "min": "1",
                "step": "1",
            }
        ),
        help_text="Uses the signed-in user's profile city.",
    )
    sort: forms.ChoiceField = forms.ChoiceField(
        label="Sort by",
        required=False,
        choices=SORT_CHOICES,
        initial="most_relevant",
    )

    def __init__(self, *args: Any, **kwargs: Any) -> None:
        self.default_sort: str = str(kwargs.pop("default_sort", "most_relevant") or "most_relevant")
        super().__init__(*args, **kwargs)

        self.dynamic_attribute_field_groups: list[DynamicAttributeFieldGroup] = []

        self.fields["category"].choices = self._build_category_choices()
        self.fields["condition"].choices = self._build_condition_choices()
        self.fields["sort"].initial = self.default_sort

        self._add_bootstrap_classes()

        selected_category_id: int | None = self._get_selected_category_id()
        if selected_category_id is not None:
            self._add_dynamic_attribute_fields(selected_category_id)

    def clean(self) -> dict[str, Any]:
        cleaned_data: dict[str, Any] = super().clean()

        min_price: Decimal | None = cleaned_data.get("min_price")
        max_price: Decimal | None = cleaned_data.get("max_price")
        if min_price is not None and max_price is not None and min_price > max_price:
            self.add_error("max_price", "Maximum price must be greater than or equal to minimum price.")

        for group in self.dynamic_attribute_field_groups:
            value_type_name: str = group.value_type_name.lower()

            if value_type_name in {"int", "integer", "decimal"}:
                minimum_field_name: str = group.field_names[0]
                maximum_field_name: str = group.field_names[1]
                minimum_value: Any = cleaned_data.get(minimum_field_name)
                maximum_value: Any = cleaned_data.get(maximum_field_name)

                if minimum_value is not None and maximum_value is not None and minimum_value > maximum_value:
                    self.add_error(maximum_field_name, f"{group.label}: maximum must be greater than or equal to minimum.")

            if value_type_name == "datetime":
                lower_field_name: str = group.field_names[0]
                upper_field_name: str = group.field_names[1]
                lower_value: Any = cleaned_data.get(lower_field_name)
                upper_value: Any = cleaned_data.get(upper_field_name)

                if lower_value is not None and upper_value is not None and lower_value > upper_value:
                    self.add_error(upper_field_name, f"{group.label}: upper bound must be after the lower bound.")

        return cleaned_data

    def _get_selected_category_id(self) -> int | None:
        raw_value: Any
        if self.is_bound:
            raw_value = self.data.get("category")
        else:
            raw_value = self.initial.get("category")

        if raw_value in {None, ""}:
            return None

        try:
            parsed_value: int = int(raw_value)
        except (TypeError, ValueError):
            return None

        return parsed_value if parsed_value > 0 else None

    def _build_category_choices(self) -> list[tuple[Any, str]]:
        grouped_categories: list[dict[str, Any]] = get_category()
        choices: list[tuple[Any, str]] = [("", "Any category")]

        for group in grouped_categories:
            parent: dict[str, Any] = group["parent"]
            children: list[dict[str, Any]] = group["children"]

            choices.append((parent["id"], parent["name"]))
            for child in children:
                choices.append((child["id"], f"— {child['name']}"))

        return choices

    def _build_condition_choices(self) -> list[tuple[Any, str]]:
        choices: list[tuple[Any, str]] = [("", "Any condition")]

        for condition in ItemCondition.objects.order_by("condition_name"):
            choices.append((condition.condition_id, condition.condition_name))

        return choices

    def _add_dynamic_attribute_fields(self, category_id: int) -> None:
        attributes = (
            Attribute.objects.select_related("value_type")
            .filter(category_id=category_id)
            .order_by("attribute_key")
        )

        for attribute in attributes:
            attribute_id: int = int(attribute.attribute_id)
            attribute_key: str = str(attribute.attribute_key)
            value_type_name: str = str(attribute.value_type.value_type_name).strip().lower()
            label: str = self._labelize_attribute_key(attribute_key)

            if value_type_name in {"int", "integer"}:
                minimum_field_name: str = f"attr_{attribute_id}_min"
                maximum_field_name: str = f"attr_{attribute_id}_max"

                self.fields[minimum_field_name] = forms.IntegerField(
                    label=f"{label} minimum",
                    required=False,
                    widget=forms.NumberInput(attrs={"placeholder": "Minimum"}),
                )
                self.fields[maximum_field_name] = forms.IntegerField(
                    label=f"{label} maximum",
                    required=False,
                    widget=forms.NumberInput(attrs={"placeholder": "Maximum"}),
                )
                self.dynamic_attribute_field_groups.append(
                    DynamicAttributeFieldGroup(
                        attribute_id=attribute_id,
                        attribute_key=attribute_key,
                        value_type_name=value_type_name,
                        label=label,
                        field_names=[minimum_field_name, maximum_field_name],
                    )
                )
                continue

            if value_type_name == "decimal":
                minimum_field_name = f"attr_{attribute_id}_min"
                maximum_field_name = f"attr_{attribute_id}_max"

                self.fields[minimum_field_name] = forms.DecimalField(
                    label=f"{label} minimum",
                    required=False,
                    decimal_places=6,
                    max_digits=18,
                    widget=forms.NumberInput(attrs={"placeholder": "Minimum", "step": "0.000001"}),
                )
                self.fields[maximum_field_name] = forms.DecimalField(
                    label=f"{label} maximum",
                    required=False,
                    decimal_places=6,
                    max_digits=18,
                    widget=forms.NumberInput(attrs={"placeholder": "Maximum", "step": "0.000001"}),
                )
                self.dynamic_attribute_field_groups.append(
                    DynamicAttributeFieldGroup(
                        attribute_id=attribute_id,
                        attribute_key=attribute_key,
                        value_type_name=value_type_name,
                        label=label,
                        field_names=[minimum_field_name, maximum_field_name],
                    )
                )
                continue

            if value_type_name == "datetime":
                lower_field_name = f"attr_{attribute_id}_from"
                upper_field_name = f"attr_{attribute_id}_to"

                self.fields[lower_field_name] = forms.DateTimeField(
                    label=f"{label} lower bound",
                    required=False,
                    input_formats=["%Y-%m-%dT%H:%M"],
                    widget=forms.DateTimeInput(
                        attrs={"type": "datetime-local"},
                        format="%Y-%m-%dT%H:%M",
                    ),
                )
                self.fields[upper_field_name] = forms.DateTimeField(
                    label=f"{label} upper bound",
                    required=False,
                    input_formats=["%Y-%m-%dT%H:%M"],
                    widget=forms.DateTimeInput(
                        attrs={"type": "datetime-local"},
                        format="%Y-%m-%dT%H:%M",
                    ),
                )
                self.dynamic_attribute_field_groups.append(
                    DynamicAttributeFieldGroup(
                        attribute_id=attribute_id,
                        attribute_key=attribute_key,
                        value_type_name=value_type_name,
                        label=label,
                        field_names=[lower_field_name, upper_field_name],
                    )
                )
                continue

            if value_type_name in {"bool", "boolean"}:
                field_name = f"attr_{attribute_id}_value"

                self.fields[field_name] = forms.TypedChoiceField(
                    label=label,
                    required=False,
                    choices=[
                        ("", "Either"),
                        ("true", "True"),
                        ("false", "False"),
                    ],
                    coerce=self._coerce_optional_bool,
                    empty_value=None,
                )
                self.dynamic_attribute_field_groups.append(
                    DynamicAttributeFieldGroup(
                        attribute_id=attribute_id,
                        attribute_key=attribute_key,
                        value_type_name=value_type_name,
                        label=label,
                        field_names=[field_name],
                    )
                )
                continue

            field_name = f"attr_{attribute_id}_value"
            allowed_value_choices: list[tuple[Any, str]] = [("", f"Any {label.lower()}")]
            for allowed_value in AllowedAttributeValue.objects.filter(attribute_id=attribute_id).order_by("allowed_value_label"):
                allowed_value_choices.append((allowed_value.allowed_value_id, allowed_value.allowed_value_label))

            self.fields[field_name] = forms.TypedChoiceField(
                label=label,
                required=False,
                choices=allowed_value_choices,
                coerce=int,
                empty_value=None,
            )
            self.dynamic_attribute_field_groups.append(
                DynamicAttributeFieldGroup(
                    attribute_id=attribute_id,
                    attribute_key=attribute_key,
                    value_type_name=value_type_name,
                    label=label,
                    field_names=[field_name],
                )
            )

        self._add_bootstrap_classes()

    def _add_bootstrap_classes(self) -> None:
        for field_name, field in self.fields.items():
            css_class: str = "form-control"

            if isinstance(field.widget, (forms.Select, forms.SelectMultiple)):
                css_class = "form-select"
            if isinstance(field.widget, forms.CheckboxInput):
                css_class = "form-check-input"

            existing_css_class: str = str(field.widget.attrs.get("class", "")).strip()
            field.widget.attrs["class"] = f"{existing_css_class} {css_class}".strip()
            field.widget.attrs.setdefault("id", f"id_{field_name}")

    @staticmethod
    def _labelize_attribute_key(attribute_key: str) -> str:
        return attribute_key.replace("_", " ").strip().title()

    @staticmethod
    def _coerce_optional_bool(raw_value: str) -> bool | None:
        normalized_value: str = raw_value.strip().lower()
        if normalized_value == "":
            return None
        return normalized_value == "true"
