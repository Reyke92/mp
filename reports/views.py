from __future__ import annotations

from django.contrib import messages
from django.contrib.auth.decorators import login_required
from django.db.models import Q
from django.http import HttpRequest, HttpResponse
from django.shortcuts import get_object_or_404, redirect, render

from listings.models import Listing
from messaging.models import Conversation
from reports.forms import ReportForm
from reports.models import ReportStatus


NON_REPORTABLE_LISTING_STATUS_NAMES: set[str] = {"frozen", "deleted"}


@login_required
def report_view(request: HttpRequest) -> HttpResponse:
    listing_id = request.GET.get("listing_id") or request.POST.get("listing_id")
    conversation_id = request.GET.get("conversation_id") or request.POST.get("conversation_id")

    listing = None
    conversation = None

    if listing_id:
        listing = get_object_or_404(Listing.objects.select_related("status", "seller_user"), pk=listing_id)
        validation_error = _validate_listing_report_target(request=request, listing=listing)
        if validation_error is not None:
            messages.error(request, validation_error)
            return redirect("listing_detail", listing_id=listing.pk)

    if conversation_id:
        conversation = get_object_or_404(
            Conversation.objects.select_related("user_a", "user_b"),
            Q(pk=conversation_id),
            (Q(user_a=request.user) | Q(user_b=request.user)),
        )

    if request.method == "POST":
        form = ReportForm(request.POST, listing=listing, conversation=conversation)
        if form.is_valid():
            initial_status = ReportStatus.objects.get(status_name="Received")
            form.save(reporter=request.user, status=initial_status)

            messages.success(request, "Your report has been submitted.")
            if listing is not None:
                return redirect("listing_detail", listing_id=listing.pk)
            if conversation is not None:
                return redirect("messaging:conversation", conversation_id=conversation.pk)
            return redirect("home")
    else:
        form = ReportForm(listing=listing, conversation=conversation)

    return render(
        request,
        "reports/report_form.html",
        {
            "form": form,
            "listing": listing,
            "conversation": conversation,
        },
    )



def _validate_listing_report_target(*, request: HttpRequest, listing: Listing) -> str | None:
    if int(listing.seller_user_id) == int(request.user.id):
        return "Listing owners cannot report their own listings."

    listing_status_name = str(listing.status.status_name).strip().lower()
    if listing_status_name in NON_REPORTABLE_LISTING_STATUS_NAMES:
        return "This listing is not currently reportable."

    if not bool(listing.seller_user.is_active):
        return "Listings owned by banned accounts are not currently reportable from this surface."

    return None
