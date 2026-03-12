from django.urls import path

from . import views

urlpatterns = [
    path("my-listings/", views.my_listings_view, name="my_listings"),
    path("listings/create/", views.create_listing_view, name="create_listing"),
    path(
        "listings/create/attributes/",
        views.create_listing_attribute_fields_partial_view,
        name="create_listing_attribute_fields",
    ),
    path("listings/cities/", views.state_cities_view, name="state_cities"),
    path("listings/<int:listing_id>/", views.listing_detail_view, name="listing_detail"),
    path("listings/<int:listing_id>/edit/", views.edit_listing_view, name="edit_listing"),
    path("listings/<int:listing_id>/delete/", views.delete_listing_view, name="delete_listing"),
]
