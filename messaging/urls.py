from django.urls import path
from . import views

urlpatterns = [
    path("messaging/inbox/", views.inbox_view, name="inbox"),
]
