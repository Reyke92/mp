from __future__ import annotations

from django.test import RequestFactory
from django.urls import resolve

from core.context_processors import user_profile_context
from tests.common import MarketplaceTestCase


class CoreContextProcessorUnitTests(MarketplaceTestCase):
    def setUp(self) -> None:
        self.factory = RequestFactory()
        self.world = self.create_basic_listing_world()
        self.user = self.create_user(
            email="user@example.com",
            with_profile=True,
            city=self.world.city,
        )
        self.admin = self.create_user(
            email="admin@example.com",
            with_profile=True,
            city=self.world.city,
        )
        self.assign_role(user=self.admin, role_name="Administrator")

    def test_user_profile_context_sets_active_sidebar_item_from_route_name(self) -> None:
        request = self.factory.get("/profile/")
        request.user = self.user
        request.resolver_match = resolve("/profile/")

        context = user_profile_context(request)

        self.assertEqual(context["active_sidebar_item"], "profile")

    def test_user_profile_context_marks_admin_and_builds_admin_sections(self) -> None:
        request = self.factory.get("/")
        request.user = self.admin
        request.resolver_match = resolve("/")

        context = user_profile_context(request)

        self.assertTrue(context["is_admin"])
        self.assertFalse(context["is_mod"])
        section_titles = [section["title"] for section in context["sidebar_navigation_sections"]]
        self.assertIn("Administration", section_titles)

    def test_user_profile_context_marks_active_category_path(self) -> None:
        request = self.factory.get(f"/?category={int(self.world.child_category.category_id)}")
        request.user = self.user
        request.resolver_match = resolve("/")

        context = user_profile_context(request)

        active_nodes = []
        for node in context["categories_sidebar_tree"]:
            if node["is_open"]:
                active_nodes.append(node["id"])
                for child in node["children"]:
                    if child["is_active"]:
                        active_nodes.append(child["id"])
        self.assertIn(int(self.world.parent_category.category_id), active_nodes)
        self.assertIn(int(self.world.child_category.category_id), active_nodes)
