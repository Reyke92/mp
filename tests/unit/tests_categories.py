from __future__ import annotations

from django.test import TestCase
from catalog.models import Category
from catalog.utils import get_category

class CategoryRetrievalTests(TestCase):
    def setUp(self) -> None:
        self.parent1 = Category.objects.create(name="Parent 1", slug="parent-1")
        self.parent2 = Category.objects.create(name="Parent 2", slug="parent-2")
        self.child1 = Category.objects.create(name="Child 1", slug="child-1", parent_category=self.parent1)
        self.child2 = Category.objects.create(name="Child 2", slug="child-2", parent_category=self.parent1)
        self.child3 = Category.objects.create(name="Child 3", slug="child-3", parent_category=self.parent2)

    def test_get_category_returns_grouped_categories(self) -> None:
        expected = [
            {
                "parent": {
                    "id": int(self.parent1.category_id),
                    "name": "Parent 1",
                    "slug": "parent-1",
                },
                "children": [
                    {
                        "id": int(self.child1.category_id),
                        "name": "Child 1",
                        "slug": "child-1",
                    },
                    {
                        "id": int(self.child2.category_id),
                        "name": "Child 2",
                        "slug": "child-2",
                    },
                ],
            },
            {
                "parent": {
                    "id": int(self.parent2.category_id),
                    "name": "Parent 2",
                    "slug": "parent-2",
                },
                "children": [
                    {
                        "id": int(self.child3.category_id),
                        "name": "Child 3",
                        "slug": "child-3",
                    },
                ],
            },
        ]

        result = get_category()
        self.assertEqual(result, expected)