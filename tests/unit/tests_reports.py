from __future__ import annotations

from django.contrib.auth import get_user_model
from django.test import TestCase
from django.urls import reverse
from listings.models import Listing, ListingStatus
from reports.models import Report, ReportStatus