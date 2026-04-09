from django.urls import path

from . import views

urlpatterns = [
    path(
        "admin/administration_log/selected-card/<int:action_id>/",
        views.administration_log_selected_card_view,
        name="administration_log_selected_card",
    ),
    path("admin/administration_log/", views.administration_log_view, name="administration_log"),
    path(
        "admin/moderation_log/selected-card/<int:action_id>/",
        views.moderation_log_selected_card_view,
        name="moderation_log_selected_card",
    ),
    path(
        "admin/listing_management/selected-card/<int:listing_id>/",
        views.listing_management_selected_card_view,
        name="listing_management_selected_card",
    ),
    path(
        "admin/user_management/selected-card/<int:user_id>/",
        views.user_management_selected_card_view,
        name="user_management_selected_card",
    ),
    path("admin/listing_management/", views.listing_management_view, name="listing_management"),
    path("admin/moderation_log/", views.moderation_log_view, name="moderation_log"),
    path("admin/user_management/", views.user_management_view, name="user_management"),
    path(
        "admin/oversight/conversations/<int:user_id>/",
        views.user_conversations_view,
        name="user_conversations",
    ),
]
