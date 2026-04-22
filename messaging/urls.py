from django.urls import path
from . import views

app_name = "messaging"

urlpatterns = [
    path("messaging/inbox/", views.inbox_view, name="inbox"),
    path("messaging/start/", views.start_conversation_view, name="start"),
    path("messaging/conversation/<int:conversation_id>/", views.conversation_view, name="conversation"),
]
