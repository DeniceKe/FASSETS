import datetime

from django.contrib.auth import get_user_model
from django.test import TestCase

from accounts.models import Department, Faculty
from assets.models import Asset, Category, Location, Supplier
from allocations.models import AssetRequest

User = get_user_model()


class DashboardRequestTests(TestCase):
    def setUp(self):
        faculty = Faculty.objects.create(name="Faculty of Science")
        self.department = Department.objects.create(code="MATH", name="Mathematics", faculty=faculty)
        other_department = Department.objects.create(code="BIO", name="Biology", faculty=faculty)
        self.category = Category.objects.create(name="ICT", code="ICT")
        self.supplier = Supplier.objects.create(name="Campus Supplier")
        self.location = Location.objects.create(
            department=self.department,
            building="Main Block",
            floor="1",
            room="101",
            room_type="office",
        )
        other_location = Location.objects.create(
            department=other_department,
            building="Bio Block",
            floor="2",
            room="201",
            room_type="lab",
        )
        self.admin = User.objects.create_superuser("admin", "admin@example.com", "pass12345Strong")
        self.visible_asset = Asset.objects.create(
            name="Math Laptop",
            category=self.category,
            description="Visible asset",
            purchase_date=datetime.date(2026, 3, 1),
            purchase_cost=1000,
            supplier=self.supplier,
            current_location=self.location,
            created_by=self.admin,
        )
        Asset.objects.create(
            name="Bio Laptop",
            category=self.category,
            description="Hidden asset",
            purchase_date=datetime.date(2026, 3, 1),
            purchase_cost=1000,
            supplier=self.supplier,
            current_location=other_location,
            created_by=self.admin,
        )
        self.user = User.objects.create_user("mathuser", password="pass12345Strong")
        self.user.profile.department = self.department
        self.user.profile.user_type = "student"
        self.user.profile.registration_number = "MTH/001/26"
        self.user.profile.save()

    def test_user_dashboard_is_department_scoped_and_can_request_available_asset(self):
        self.client.force_login(self.user)
        response = self.client.get("/dashboard/")

        self.assertContains(response, "Math Laptop")
        self.assertNotContains(response, "Bio Laptop")

        request_response = self.client.post(f"/assets/{self.visible_asset.id}/request/")
        self.assertRedirects(request_response, "/dashboard/")
        self.assertEqual(
            AssetRequest.objects.filter(asset=self.visible_asset, requested_by=self.user, status="pending").count(),
            1,
        )
