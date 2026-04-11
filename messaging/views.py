from accounts.models import UserProfile
from django.contrib.auth.decorators import login_required
from django.core.exceptions import PermissionDenied
from django.db.models import Q
from django.http import HttpRequest, HttpResponse, JsonResponse
from django.shortcuts import redirect, render
from messaging.models import Conversation
from typing import Any

@login_required
def inbox_view(request: HttpRequest) -> HttpResponse:
    conversations = Conversation.objects.filter(Q(user_a=request.user) | Q(user_b=request.user)).order_by('-created_at')
    
    context: dict[str, Any] = {
        "rows": conversations,
        "active_sidebar_item": "messages",
    }
    return render(request, "messaging/inbox.html", context)