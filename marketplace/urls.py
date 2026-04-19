"""
URL configuration for marketplace project.

The `urlpatterns` list routes URLs to views. For more information please see:
    https://docs.djangoproject.com/en/6.0/topics/http/urls/
Examples:
Function views
    1. Add an import:  from my_app import views
    2. Add a URL to urlpatterns:  path('', views.home, name='home')
Class-based views
    1. Add an import:  from other_app.views import Home
    2. Add a URL to urlpatterns:  path('', Home.as_view(), name='home')
Including another URLconf
    1. Import the include() function: from django.urls import include, path
    2. Add a URL to urlpatterns:  path('blog/', include('blog.urls'))
"""
from django.conf import settings
from django.urls import include, path, re_path
from django.views.static import serve

handler403 = "marketplace.error_views.error_403"
handler404 = "marketplace.error_views.error_404"
handler500 = "marketplace.error_views.error_500"

urlpatterns = [
    path("", include("core.urls")),
    path("", include("accounts.urls")),
    path("", include("search.urls")),
    path("", include("listings.urls")),
    path("", include("reports.urls")),
    path("", include("admin_ops.urls")),
]

if settings.DEBUG or getattr(settings, "SERVE_FILES_THROUGH_DJANGO", False):
    urlpatterns += [
        re_path(
            r"^static/(?P<path>.*)$",
            serve,
            {"document_root": settings.STATIC_ROOT},
        ),
        re_path(
            r"^(?P<path>.*)$",
            serve,
            {"document_root": settings.MEDIA_ROOT},
        ),
    ]