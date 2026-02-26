from __future__ import annotations

from typing import Any

from django.http import HttpRequest

from accounts.models import UserProfile


def user_profile_context(request: HttpRequest) -> dict[str, Any]:
    """
    Adds:
      - user: request.user
      - profile: UserProfile
    """
    context: dict[str, Any] = {"user": request.user}

    if request.user.is_authenticated:
        # Cache on the request object to avoid multiple DB hits in one request.
        profile = getattr(request, "_cached_user_profile", None)
        if profile is None:
            profile = UserProfile.objects.get(user=request.user)
            setattr(request, "_cached_user_profile", profile)

        context["profile"] = profile

    return context
