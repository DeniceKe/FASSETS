import datetime

from django.contrib.auth import get_user_model
from django.test import TestCase
from rest_framework.test import APIClient

from accounts.models import Department, Faculty
from accounts.roles import ROLE_COD, ROLE_LAB_TECHNICIAN, ROLE_LECTURER
from assets.models import Asset, Category, Location, Supplier
from maintenance.models import Maintenance

User = get_user_model()


class BaseAPITestCase(TestCase):
    def setUp(self):
        self.client = APIClient()
        self.faculty = Faculty.objects.create(name="Faculty of Science")
        self.comp_sci = Department.objects.create(code="COMP", name="Computer Science", faculty=self.faculty)
        self.maths = Department.objects.create(code="MATH", name="Mathematics", faculty=self.faculty)
        self.category = Category.objects.create(name="ICT", code="ICT")
        self.supplier = Supplier.objects.create(name="Tech Supplies")
        self.comp_lab = Location.objects.create(
            department=self.comp_sci,
            building="Science Block",
            floor="1",
            room="101",
            room_type="lab",
        )
        self.maths_office = Location.objects.create(
            department=self.maths,
            building="Math Block",
            floor="2",
            room="201",
            room_type="office",
        )

    def create_user(self, username, role, department=None):
        user = User.objects.create_user(username=username, password="testpass123")
        user.profile.role = role
        user.profile.department = department
        user.profile.save()
        return user

    def create_asset(self, name, location, created_by):
        return Asset.objects.create(
            name=name,
            category=self.category,
            description=f"{name} description",
            purchase_date=datetime.date(2026, 3, 1),
            purchase_cost=1000,
            supplier=self.supplier,
            current_location=location,
            created_by=created_by,
        )


class AssetScopeTests(BaseAPITestCase):
    def test_cod_only_sees_assets_from_own_department(self):
        cod = self.create_user("cod_user", ROLE_COD, self.comp_sci)
        self.create_asset("Comp Asset", self.comp_lab, cod)
        self.create_asset("Math Asset", self.maths_office, cod)

        self.client.force_authenticate(cod)
        response = self.client.get("/api/assets/")

        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.data["count"], 1)
        self.assertEqual(response.data["results"][0]["department_name"], "Computer Science")


class AllocationWorkflowTests(BaseAPITestCase):
    def test_allocation_and_return_update_asset_status(self):
        cod = self.create_user("cod_user", ROLE_COD, self.comp_sci)
        lecturer = self.create_user("lecturer_user", ROLE_LECTURER, self.comp_sci)
        asset = self.create_asset("Laptop", self.comp_lab, cod)

        self.client.force_authenticate(cod)
        create_response = self.client.post(
            "/api/allocations/",
            {
                "asset": asset.id,
                "allocated_to": lecturer.id,
                "allocation_date": "2026-03-10",
                "expected_return_date": "2026-03-15",
                "purpose": "Teaching",
                "condition_out": "good",
                "status": "active",
            },
            format="json",
        )

        self.assertEqual(create_response.status_code, 201, create_response.data)
        asset.refresh_from_db()
        self.assertEqual(asset.status, "allocated")

        allocation_id = create_response.data["id"]
        return_response = self.client.patch(
            f"/api/allocations/{allocation_id}/",
            {
                "status": "returned",
                "actual_return_date": "2026-03-14",
                "condition_in": "good",
            },
            format="json",
        )

        self.assertEqual(return_response.status_code, 200, return_response.data)
        asset.refresh_from_db()
        self.assertEqual(asset.status, "available")


class MaintenanceWorkflowTests(BaseAPITestCase):
    def test_maintenance_open_and_completion_update_asset_status(self):
        technician = self.create_user("tech_user", ROLE_LAB_TECHNICIAN, self.comp_sci)
        asset = self.create_asset("Microscope", self.comp_lab, technician)

        self.client.force_authenticate(technician)
        create_response = self.client.post(
            "/api/maintenance/",
            {
                "asset": asset.id,
                "maintenance_type": "corrective",
                "scheduled_date": "2026-03-11",
                "description": "Lens replacement",
                "status": "in_progress",
            },
            format="json",
        )

        self.assertEqual(create_response.status_code, 201, create_response.data)
        asset.refresh_from_db()
        self.assertEqual(asset.status, "maintenance")

        maintenance_id = create_response.data["id"]
        complete_response = self.client.patch(
            f"/api/maintenance/{maintenance_id}/",
            {
                "status": "completed",
                "completed_date": "2026-03-12",
                "resolution_notes": "Lens replaced and calibrated.",
            },
            format="json",
        )

        self.assertEqual(complete_response.status_code, 200, complete_response.data)
        asset.refresh_from_db()
        self.assertEqual(asset.status, "available")
        self.assertEqual(Maintenance.objects.get(pk=maintenance_id).reported_by, technician)
