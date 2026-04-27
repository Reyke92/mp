from __future__ import annotations

from dataclasses import dataclass
from typing import Any

from django.contrib.auth import get_user_model
from django.shortcuts import get_object_or_404
from django.urls import reverse

from accounts.models import UserProfile
from messaging.models import Conversation, Message


UserModel = get_user_model()


@dataclass(frozen=True)
class OversightConversationRow:
    conversation_id: int
    other_user_display_name: str
    other_user_email_address: str
    other_user_profile_url: str
    last_message_text: str
    last_message_at: Any | None
    message_count: int
    detail_url: str


@dataclass(frozen=True)
class OversightUserConversationsPageContext:
    oversight_user: Any
    oversight_user_profile: UserProfile | None
    conversation_rows: list[OversightConversationRow]


@dataclass(frozen=True)
class LimitedConversationMessageRow:
    sender_display_name: str
    sender_email_address: str
    is_selected_user_sender: bool
    message_text: str
    sent_at: Any


@dataclass(frozen=True)
class LimitedUserConversationPageContext:
    oversight_user: Any
    oversight_user_profile: UserProfile | None
    conversation: Conversation
    participant_a: Any
    participant_b: Any
    participant_a_profile: UserProfile | None
    participant_b_profile: UserProfile | None
    message_rows: list[LimitedConversationMessageRow]
    back_to_conversations_url: str



def build_user_conversations_page_context(*, user_id: int) -> OversightUserConversationsPageContext:
    oversight_user = get_object_or_404(UserModel, pk=user_id)
    oversight_profile = UserProfile.objects.select_related("city", "city__state").filter(user_id=user_id).first()

    conversations = (
        Conversation.objects.select_related("user_a", "user_b")
        .filter(user_a_id=user_id)
        | Conversation.objects.select_related("user_a", "user_b").filter(user_b_id=user_id)
    )
    conversations = conversations.order_by("-created_at", "-conversation_id")

    rows: list[OversightConversationRow] = []
    for conversation in conversations:
        other_user = conversation.user_b if int(conversation.user_a_id) == int(user_id) else conversation.user_a
        last_message = Message.objects.filter(conversation_id=conversation.conversation_id).order_by("-sent_at", "-message_id").first()
        message_count = Message.objects.filter(conversation_id=conversation.conversation_id).count()
        rows.append(
            OversightConversationRow(
                conversation_id=int(conversation.conversation_id),
                other_user_display_name=_build_person_display_name(other_user),
                other_user_email_address=str(other_user.username),
                other_user_profile_url=reverse("view_profile", kwargs={"id": int(other_user.id)}),
                last_message_text=str(getattr(last_message, "message_text", "")).strip() or "No messages yet.",
                last_message_at=getattr(last_message, "sent_at", None),
                message_count=message_count,
                detail_url=reverse(
                    "limited_user_conversation",
                    kwargs={"user_id": int(user_id), "conversation_id": int(conversation.conversation_id)},
                ),
            )
        )

    return OversightUserConversationsPageContext(
        oversight_user=oversight_user,
        oversight_user_profile=oversight_profile,
        conversation_rows=rows,
    )



def build_limited_user_conversation_page_context(
    *,
    user_id: int,
    conversation_id: int,
) -> LimitedUserConversationPageContext:
    oversight_user = get_object_or_404(UserModel, pk=user_id)
    conversation = get_object_or_404(
        Conversation.objects.select_related("user_a", "user_b"),
        pk=conversation_id,
    )
    if int(conversation.user_a_id) != int(user_id) and int(conversation.user_b_id) != int(user_id):
        raise Conversation.DoesNotExist

    oversight_profile = UserProfile.objects.select_related("city", "city__state").filter(user_id=user_id).first()
    participant_a_profile = UserProfile.objects.select_related("city", "city__state").filter(user_id=conversation.user_a_id).first()
    participant_b_profile = UserProfile.objects.select_related("city", "city__state").filter(user_id=conversation.user_b_id).first()

    message_rows: list[LimitedConversationMessageRow] = []
    for message in Message.objects.filter(conversation_id=conversation_id).select_related("sender_user").order_by("sent_at", "message_id"):
        message_rows.append(
            LimitedConversationMessageRow(
                sender_display_name=_build_person_display_name(message.sender_user),
                sender_email_address=str(message.sender_user.username),
                is_selected_user_sender=int(message.sender_user_id) == int(user_id),
                message_text=str(message.message_text),
                sent_at=message.sent_at,
            )
        )

    return LimitedUserConversationPageContext(
        oversight_user=oversight_user,
        oversight_user_profile=oversight_profile,
        conversation=conversation,
        participant_a=conversation.user_a,
        participant_b=conversation.user_b,
        participant_a_profile=participant_a_profile,
        participant_b_profile=participant_b_profile,
        message_rows=message_rows,
        back_to_conversations_url=reverse("user_conversations", kwargs={"user_id": int(user_id)}),
    )



def _build_person_display_name(user: Any) -> str:
    first_name = str(getattr(user, "first_name", "")).strip()
    last_name = str(getattr(user, "last_name", "")).strip()
    full_name = f"{first_name} {last_name}".strip()
    return full_name or str(getattr(user, "username", "Unknown user"))
