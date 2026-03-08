from __future__ import annotations

from django.contrib.auth import login, logout, authenticate, get_user_model
from django.contrib.auth.models import AnonymousUser, User
from django.contrib import messages
from django.contrib.auth.decorators import login_required
from django.core.files import File
from django.http import HttpRequest, HttpResponse
from django.shortcuts import redirect, render
from django.views.decorators.http import require_http_methods
from typing import Any, cast

from .forms import RegisterForm, LoginForm, ProfileForm
from .models import UserProfile
from core import storage
from core.models import City, State
from tracking.json_snapshots import get_snapshot, refresh_snapshot, ListingMetadataSnapshotData
from accounts.utils.storage import copy_default_avatar_for_user
from accounts.utils.auth import authenticate_with_email


def login_view(request: HttpRequest) -> HttpResponse:
    if request.method == "POST":
        form = LoginForm(request.POST)
        if form.is_valid():
            email: str = form.cleaned_data["email"].strip().lower()
            password: str = form.cleaned_data["password"]

            user = authenticate_with_email(request, email, password)
            if user is None:
                # Shows directly on the login page
                form.add_error(None, "Invalid email or password.")
            else:
                login(request, user)
                return redirect("home")
    else:
        form = LoginForm()

    return render(request, "accounts/login.html", {"form": form})

@require_http_methods(["GET", "POST"])
def register_view(request: HttpRequest) -> HttpResponse:
    context: dict[str, Any] = {}

    if request.method == "POST":
        form = RegisterForm(request.POST)
        context["form"] = form
        if form.is_valid():
            city_name = form.cleaned_data["city_name"].strip()
            state_name = form.cleaned_data["state_name"].strip()

            # Resolve City (cities has unique key on (state_id, city_name))
            try:
                state_obj = State.objects.get(state_name__iexact=state_name)
                city_obj = City.objects.get(
                    city_name__iexact=city_name,
                    state=state_obj
                )
            except City.DoesNotExist:
                form.add_error("city_name", "That city/state was not found in our supported cities.")
                return render(request, "accounts/register.html", context)

            user = form.save()

            try:
                avatar_rel_path = copy_default_avatar_for_user()
                UserProfile.objects.create(
                    user=user,
                    city=city_obj,
                    bio="",
                    avatar=avatar_rel_path,  # relative media path
                )
            except:
                return redirect("register")

            login(request, user)
            return redirect("home")

    else:
        form = RegisterForm()
        context["form"] = form
    
    return render(request, "accounts/register.html", context)

@require_http_methods(["POST"])
def logout_view(request: HttpRequest) -> HttpResponse:
    logout(request)
    return redirect("home")

@login_required
@require_http_methods(["GET", "POST"])
def edit_profile_view(request: HttpRequest) -> HttpResponse:
    context: dict[str, Any] = {}

    if isinstance(request.user, AnonymousUser):
        return redirect("login")
    user: User = cast(User, request.user)

    try:
        profile: UserProfile = UserProfile.objects.select_related("city", "city__state").get(
            user=user
        )
    except UserProfile.DoesNotExist:
        return redirect("home")

    if request.method == "POST":
        form = ProfileForm(request.POST, request.FILES)
        context["form"] = form

        if form.is_valid():
            city_name: str = form.cleaned_data["city_name"].strip()
            state_name: str = form.cleaned_data["state_name"].strip()

            try:
                state_obj: State = State.objects.get(state_name__iexact=state_name)
            except State.DoesNotExist:
                form.add_error("state_name", "That state was not found.")
                return render(request, "accounts/edit_profile.html", context)

            try:
                city_obj: City = City.objects.get(
                    city_name__iexact=city_name,
                    state=state_obj,
                )
            except City.DoesNotExist:
                form.add_error("city_name", "That city/state was not found in our supported cities.")
                return render(request, "accounts/edit_profile.html", context)

            user.first_name = form.cleaned_data["first_name"]
            user.last_name = form.cleaned_data["last_name"]
            user.save()

            profile.bio = form.cleaned_data["bio"]
            profile.city = city_obj

            avatar = form.cleaned_data.get("avatar")
            if avatar is not None:
                profile.avatar.delete(save=False)
                profile.avatar = avatar

            profile.save()

            messages.success(request, "Your profile was updated successfully.")
            return redirect("profile")

    else:
        form = ProfileForm(
            initial={
                "first_name": user.first_name,
                "last_name": user.last_name,
                "bio": profile.bio or "",
                "city_name": profile.city.city_name,
                "state_name": profile.city.state.state_name,
            }
        )
        context["form"] = form

    return render(request, "accounts/profile.html", context)

def view_profile_view(request, user_id:int):
    return render(request, 'accounts/view_profile.html', context={})
