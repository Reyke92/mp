from django.urls import path

from . import views

urlpatterns = [
    path("moderation/queue/", views.mod_queue_view, name="moderation_queue"),
]
