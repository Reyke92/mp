from typing import Any, Optional

from django.contrib.auth import authenticate, get_user_model
from django.http import HttpRequest, HttpResponse

def authenticate_with_email(request: HttpRequest, email: str, password: str) -> Optional[Any]:
    """
    Tries to authenticate using the project's USERNAME_FIELD.
    Works if USERNAME_FIELD == "email" (custom user), or if you store email as username.
    """
    UserModel = get_user_model()
    username_field: str = UserModel.USERNAME_FIELD

    # Treat the input email as USERNAME_FIELD value.
    user = authenticate(request, **{username_field: email, "password": password})
    if user is not None:
        return user

    return None
