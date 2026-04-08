from django.shortcuts import render

from django.contrib.auth.decorators import login_required
from django.contrib import messages
from django.shortcuts import get_object_or_404, redirect, render

from listings.models import Listing
from messaging.models import Conversation
from .forms import ReportForm
from .models import Report, ReportStatus


@login_required
def report_view(request):
    listing_id = request.GET.get("listing_id") or request.POST.get("listing_id")
    conversation_id = request.GET.get("conversation_id") or request.POST.get("conversation_id")

    listing = None
    conversation = None

    if listing_id:
        listing = get_object_or_404(Listing, pk=listing_id)

    if conversation_id:
        conversation = get_object_or_404(Conversation, pk=conversation_id)

    if request.method == "POST":
        form = ReportForm(request.POST, listing=listing, conversation=conversation)
        if form.is_valid():
            initial_status = ReportStatus.objects.get(status_name="Received")

            report = Report(
                reporter_user=request.user,
                listing=listing,
                conversation=conversation,
                details=form.cleaned_data["reason"],
                status=initial_status,
            )
            report.save()

            messages.success(request, "Your report has been submitted.")
            if listing:
                return redirect("listing_detail", listing_id=listing.pk)
            if conversation:
                return redirect("conversation_detail", conversation_id=conversation.pk)
            return redirect("homepage")
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
