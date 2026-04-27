from django.urls import path

from . import views

urlpatterns = [
    path("moderation/queue/", views.mod_queue_view, name="moderation_queue"),
    path("moderation/reports/<int:report_id>/", views.report_details_view, name="report_details")
]
