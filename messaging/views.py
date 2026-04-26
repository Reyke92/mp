from django.contrib.auth.decorators import login_required
from django.core.exceptions import PermissionDenied
from django.db.models import Q, Max, Subquery, OuterRef, CharField
from django.db.models.functions import Coalesce
from django.http import Http404, HttpRequest, JsonResponse
from django.shortcuts import render, get_object_or_404, redirect
from django.utils.dateparse import parse_datetime
from django.views.decorators.http import require_POST
from listings.utils import can_view_listing, get_listing_by_id_or_404
from messaging.models import Conversation, Message
from typing import Any

@login_required
def inbox_view(request: HttpRequest):
    latest_msg = Message.objects.filter(conversation=OuterRef('pk')).order_by('-sent_at')

    conversations = Conversation.objects.filter(
        Q(user_a=request.user) | Q(user_b=request.user)
    ).select_related('user_a', 'user_b').annotate(
        last_msg_at=Subquery(latest_msg.values('sent_at')[:1]),
        last_msg_text=Subquery(latest_msg.values('message_text')[:1]),
    ).order_by('-last_msg_at', '-created_at')
    
    context: dict[str, Any] = {
        "rows": conversations,
        "active_sidebar_item": "messages",
    }
    return render(request, "messaging/inbox.html", context)

@login_required
@require_POST
def start_conversation_view(request: HttpRequest):
    listing_id = request.POST.get("listing_id")
    if(listing_id is None):
        raise Http404("Listing not found.")
    listing = get_listing_by_id_or_404(int(listing_id))
    
    if (not can_view_listing(listing=listing, viewer=request.user)):
        raise PermissionDenied("You do not have permission to view this listing.")
    
    if listing.seller_user == request.user:
        raise PermissionDenied("You cannot start a conversation with yourself.")

    user_a, user_b = Conversation.standard_pair(request.user, listing.seller_user)
    conversation, _created = Conversation.objects.get_or_create(user_a=user_a, user_b=user_b)

    
    return redirect("messaging:conversation", conversation_id=conversation.conversation_id)

@login_required
def conversation_view(request: HttpRequest, conversation_id: int):
    conversation = get_object_or_404(Conversation, pk=conversation_id)

    if (request.user != conversation.user_a and request.user != conversation.user_b):
        raise PermissionDenied("You do not have permission to view this conversation.")
    
    other_user = conversation.user_b if conversation.user_a == request.user else conversation.user_a

    thread_messages = Message.objects.filter(conversation=conversation).order_by('sent_at')

    context: dict[str, Any] = {
        "conversation": conversation,
        "other_user": other_user,
        "thread_messages": thread_messages,
        "active_sidebar_item": "messages",
    }
    return render(request, "messaging/conversation.html", context)

@login_required
@require_POST
def send_message_view(request: HttpRequest, conversation_id: int):
    conversation = get_object_or_404(Conversation, pk=conversation_id)

    if (request.user != conversation.user_a and request.user != conversation.user_b):
        raise PermissionDenied("You do not have permission to view this conversation.")
    
    content = request.POST.get("message_text", "").strip()
    if len(content) == 0:
        return redirect("messaging:conversation", conversation_id=conversation.conversation_id)

    Message.objects.create(
        conversation=conversation,
        sender_user=request.user,
        message_text=content,
    )
    
    return redirect("messaging:conversation", conversation_id=conversation.conversation_id)

@login_required
def conversation_messages_json(request: HttpRequest, conversation_id: int):
    conversation = get_object_or_404(Conversation, pk=conversation_id)

    if (request.user != conversation.user_a and request.user != conversation.user_b):
        return JsonResponse({"error": "Forbidden"}, status=403)
    
    after = request.GET.get("after", "")
    messages_qs = Message.objects.filter(conversation=conversation).order_by('sent_at')

    if after:
        after_dt = parse_datetime(after)
        if after_dt is not None:
            messages_qs = messages_qs.filter(sent_at__gt=after_dt)

    messages_data = []
    for msg in messages_qs:
        messages_data.append({
            "sender_user": msg.sender_user_id,  # type: ignore[attr-defined]
            "message_text": msg.message_text,
            "sent_at": msg.sent_at.strftime("%b %d, %Y, %I:%M %p"),
            "sent_at_iso": msg.sent_at.isoformat(),
            "is_mine": msg.sender_user_id == request.user.id,   # type: ignore[attr-defined]
        })  

    return JsonResponse({"messages": messages_data})