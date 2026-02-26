from django.urls import path

from . import views

urlpatterns = [
    path("login/", views.login_view, name="login"),
    path("register/", views.register_view, name="register"),
    path("logout/", views.logout_view, name="logout"),
    path("profile/", views.edit_profile_view, name="profile"),
    path("profile/<int:id>/", views.view_profile_view, name="view_profile"),
]
