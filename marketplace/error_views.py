from __future__ import annotations

from django.http import HttpRequest, HttpResponse
from django.shortcuts import render



def error_403(request: HttpRequest, exception: Exception) -> HttpResponse:
    """Render the custom 403 page."""
    return render(request, "errors/403.html", status=403)



def error_404(request: HttpRequest, exception: Exception) -> HttpResponse:
    """Render the custom 404 page."""
    return render(request, "errors/404.html", status=404)



def error_500(request: HttpRequest) -> HttpResponse:
    """Render the custom 500 page."""
    return render(request, "errors/500.html", status=500)
