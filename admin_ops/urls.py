from django.urls import path

from . import views

urlpatterns = [
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
    path("admin/user_management/", views.user_management_view, name="user_management"),
    path(
        "admin/oversight/conversations/<int:user_id>/",
        views.user_conversations_view,
        name="user_conversations",
    ),
]
