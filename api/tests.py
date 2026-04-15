import datetime
import shutil
from pathlib import Path

from django.contrib.auth import get_user_model
from django.conf import settings
from django.core.exceptions import ValidationError
from django.core.files.uploadedfile import SimpleUploadedFile
from django.test import TestCase, override_settings
from rest_framework.test import APIClient

from accounts.models import AuditLog, Department, Faculty
from accounts.roles import ROLE_ADMIN, ROLE_COD, ROLE_INTERNAL_AUDITOR, ROLE_LAB_TECHNICIAN, ROLE_LECTURER
from allocations.models import Allocation
from assets.models import Asset, AssetMovement, Category, DepreciationRecord, Location, Supplier
from maintenance.models import Maintenance

User = get_user_model()


class BaseAPITestCase(TestCase):
    def setUp(self):
        self.client = APIClient()
        self.faculty = Faculty.objects.create(name="Faculty of Science")
        self.comp_sci = Department.objects.create(code="COMP", name="Computer Science", faculty=self.faculty)
        self.maths = Department.objects.create(code="MATH", name="Mathematics", faculty=self.faculty)
        self.category = Category.objects.create(name="ICT")
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

    def test_cod_search_only_returns_assets_from_own_department(self):
        cod = self.create_user("comp_cod", ROLE_COD, self.comp_sci)
        self.create_asset("Chem Microscope", self.comp_lab, cod)
        self.create_asset("Chem Cabinet", self.maths_office, cod)

        self.client.force_authenticate(cod)
        response = self.client.get("/api/assets/", {"search": "Chem"})

        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.data["count"], 1)
        self.assertEqual(response.data["results"][0]["name"], "Chem Microscope")

    def test_internal_auditor_sees_assets_across_all_departments(self):
        auditor = self.create_user("auditor_user", ROLE_INTERNAL_AUDITOR)
        self.create_asset("Comp Asset", self.comp_lab, auditor)
        self.create_asset("Math Asset", self.maths_office, auditor)

        self.client.force_authenticate(auditor)
        response = self.client.get("/api/assets/")

        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.data["count"], 2)
        departments = {item["department_name"] for item in response.data["results"]}
        self.assertEqual(departments, {"Computer Science", "Mathematics"})

    def test_internal_auditor_cannot_create_assets(self):
        auditor = self.create_user("auditor_writer", ROLE_INTERNAL_AUDITOR)

        self.client.force_authenticate(auditor)
        response = self.client.post(
            "/api/assets/",
            {
                "name": "Blocked Asset",
                "category": self.category.id,
                "description": "Should not be created",
                "purchase_date": "2026-03-01",
                "purchase_cost": "1200.00",
                "supplier": self.supplier.id,
                "current_location": self.comp_lab.id,
                "condition": "good",
                "status": "available",
            },
            format="json",
        )

        self.assertEqual(response.status_code, 403)


class DepartmentScopeTests(BaseAPITestCase):
    def test_cod_only_sees_own_department_in_department_endpoint(self):
        cod = self.create_user("dept_cod", ROLE_COD, self.comp_sci)

        self.client.force_authenticate(cod)
        response = self.client.get("/api/departments/")

        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.data["count"], 1)
        self.assertEqual(response.data["results"][0]["id"], self.comp_sci.id)
        self.assertEqual(response.data["results"][0]["code"], self.comp_sci.code)

    def test_internal_auditor_sees_all_departments_in_department_endpoint(self):
        auditor = self.create_user("dept_auditor", ROLE_INTERNAL_AUDITOR)

        self.client.force_authenticate(auditor)
        response = self.client.get("/api/departments/")

        self.assertEqual(response.status_code, 200)
        department_codes = {item["code"] for item in response.data["results"]}
        self.assertEqual(department_codes, {self.comp_sci.code, self.maths.code})


class UserManagementScopeTests(BaseAPITestCase):
    def test_lab_technician_can_list_users_in_own_department_only(self):
        technician = self.create_user("labtech_user", ROLE_LAB_TECHNICIAN, self.comp_sci)
        own_department_user = self.create_user("comp_lecturer", ROLE_LECTURER, self.comp_sci)
        self.create_user("math_lecturer", ROLE_LECTURER, self.maths)

        self.client.force_authenticate(technician)
        response = self.client.get("/api/users/")

        self.assertEqual(response.status_code, 200)
        usernames = {item["username"] for item in response.data["results"]}
        self.assertIn(technician.username, usernames)
        self.assertIn(own_department_user.username, usernames)
        self.assertNotIn("math_lecturer", usernames)

    def test_admin_can_delete_user(self):
        admin = self.create_user("admin_user", ROLE_ADMIN, self.comp_sci)
        lecturer = self.create_user("lecturer_user", ROLE_LECTURER, self.comp_sci)

        self.client.force_authenticate(admin)
        response = self.client.delete(f"/api/users/{lecturer.id}/")

        self.assertEqual(response.status_code, 204)
        self.assertFalse(User.objects.filter(id=lecturer.id).exists())
        delete_log = AuditLog.objects.filter(
            actor=admin,
            action=AuditLog.ACTION_DELETE,
            target_object_id=str(lecturer.id),
        ).first()
        self.assertIsNotNone(delete_log)
        self.assertEqual(delete_log.source, f"/api/users/{lecturer.id}/")

    def test_cod_can_create_user_for_own_department(self):
        cod = self.create_user("cod_user", ROLE_COD, self.comp_sci)

        self.client.force_authenticate(cod)
        response = self.client.post(
            "/api/users/",
            {
                "username": "newlecturer",
                "password": "StrongPass123!",
                "first_name": "New",
                "last_name": "Lecturer",
                "role": ROLE_LECTURER,
                "user_type": "staff",
                "employee_id": "EMP-200",
            },
            format="json",
        )

        self.assertEqual(response.status_code, 201, response.data)
        created_user = User.objects.get(username="newlecturer")
        self.assertEqual(created_user.profile.department, self.comp_sci)
        self.assertEqual(created_user.profile.role, ROLE_LECTURER)
        self.assertEqual(created_user.profile.employee_id, "EMP-200")
        create_log = AuditLog.objects.filter(
            actor=cod,
            action=AuditLog.ACTION_CREATE,
            target_object_id=str(created_user.id),
        ).first()
        self.assertIsNotNone(create_log)
        self.assertEqual(create_log.source, "/api/users/")
        self.assertIn("username", create_log.metadata.get("fields", []))
        self.assertIn("profile.role", create_log.metadata.get("fields", []))
        self.assertNotIn("password", create_log.metadata.get("fields", []))

    def test_cod_can_update_user_in_own_department(self):
        cod = self.create_user("cod_user", ROLE_COD, self.comp_sci)
        lecturer = self.create_user("lecturer_user", ROLE_LECTURER, self.comp_sci)

        self.client.force_authenticate(cod)
        response = self.client.patch(
            f"/api/users/{lecturer.id}/",
            {
                "first_name": "Updated",
                "role": ROLE_LAB_TECHNICIAN,
            },
            format="json",
        )

        self.assertEqual(response.status_code, 200, response.data)
        lecturer.refresh_from_db()
        self.assertEqual(lecturer.first_name, "Updated")
        self.assertEqual(lecturer.profile.role, ROLE_LAB_TECHNICIAN)

    def test_cod_cannot_create_user_for_another_department(self):
        cod = self.create_user("cod_user", ROLE_COD, self.comp_sci)

        self.client.force_authenticate(cod)
        response = self.client.post(
            "/api/users/",
            {
                "username": "mathslecturer",
                "password": "StrongPass123!",
                "role": ROLE_LECTURER,
                "department": self.maths.id,
            },
            format="json",
        )

        self.assertEqual(response.status_code, 400, response.data)
        self.assertIn("CoD users can only manage users in their own department.", str(response.data))

    def test_cod_cannot_assign_admin_or_dean_role(self):
        cod = self.create_user("cod_user", ROLE_COD, self.comp_sci)

        self.client.force_authenticate(cod)
        response = self.client.post(
            "/api/users/",
            {
                "username": "promoteduser",
                "password": "StrongPass123!",
                "role": "admin",
            },
            format="json",
        )

        self.assertEqual(response.status_code, 400, response.data)
        self.assertIn("CoD users cannot assign Admin or Dean roles.", str(response.data))


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

    def test_allocation_to_staff_user_moves_asset_to_staff_location(self):
        cod = self.create_user("cod_user", ROLE_COD, self.comp_sci)
        staff_user = self.create_user("staff_holder", ROLE_LECTURER, self.comp_sci)
        staff_office = Location.objects.create(
            department=self.comp_sci,
            building="Staff Block",
            floor="3",
            room="Office 12",
            room_type="office",
        )
        staff_user.profile.user_type = "staff"
        staff_user.profile.employee_id = "EMP-300"
        staff_user.profile.staff_location = staff_office
        staff_user.profile.save()
        asset = self.create_asset("Department Laptop", self.comp_lab, cod)

        self.client.force_authenticate(cod)
        response = self.client.post(
            "/api/allocations/",
            {
                "asset": asset.id,
                "allocated_to": staff_user.id,
                "allocation_type": "temporary",
                "allocation_date": "2026-03-10",
                "expected_return_date": "2026-03-15",
                "purpose": "Issued to staff office.",
                "condition_out": "good",
                "status": "active",
            },
            format="json",
        )

        self.assertEqual(response.status_code, 201, response.data)
        asset.refresh_from_db()
        self.assertEqual(asset.current_location, staff_office)
        movement = AssetMovement.objects.get(asset=asset)
        self.assertEqual(movement.from_location, self.comp_lab)
        self.assertEqual(movement.to_location, staff_office)
        self.assertEqual(movement.moved_by, cod)

    def test_staff_recipient_requires_profile_location_before_allocation(self):
        cod = self.create_user("cod_user", ROLE_COD, self.comp_sci)
        staff_user = self.create_user("staff_holder", ROLE_LECTURER, self.comp_sci)
        staff_user.profile.user_type = "staff"
        staff_user.profile.employee_id = "EMP-301"
        staff_user.profile.save()
        asset = self.create_asset("Department Projector", self.comp_lab, cod)

        self.client.force_authenticate(cod)
        response = self.client.post(
            "/api/allocations/",
            {
                "asset": asset.id,
                "allocated_to": staff_user.id,
                "allocation_type": "temporary",
                "allocation_date": "2026-03-10",
                "expected_return_date": "2026-03-15",
                "purpose": "Should require a staff location.",
                "condition_out": "good",
                "status": "active",
            },
            format="json",
        )

        self.assertEqual(response.status_code, 400, response.data)
        self.assertIn("Staff recipients must have an office or lab location on their profile before allocation.", str(response.data))

    def test_permanent_allocation_does_not_require_expected_return_date(self):
        admin = self.create_user("admin_user", ROLE_ADMIN, self.comp_sci)
        lecturer = self.create_user("permanent_holder", ROLE_LECTURER, self.comp_sci)
        asset = self.create_asset("Office Desktop", self.comp_lab, admin)

        self.client.force_authenticate(admin)
        response = self.client.post(
            "/api/allocations/",
            {
                "asset": asset.id,
                "allocated_to": lecturer.id,
                "allocation_type": "permanent",
                "allocation_date": "2026-03-10",
                "purpose": "Permanently issued workstation.",
                "condition_out": "good",
                "status": "active",
            },
            format="json",
        )

        self.assertEqual(response.status_code, 201, response.data)
        self.assertEqual(response.data["allocation_type"], "permanent")
        self.assertIsNone(response.data["expected_return_date"])

    def test_temporary_allocation_requires_expected_return_date(self):
        admin = self.create_user("admin_user", ROLE_ADMIN, self.comp_sci)
        lecturer = self.create_user("temporary_holder", ROLE_LECTURER, self.comp_sci)
        asset = self.create_asset("Loan Laptop", self.comp_lab, admin)

        self.client.force_authenticate(admin)
        response = self.client.post(
            "/api/allocations/",
            {
                "asset": asset.id,
                "allocated_to": lecturer.id,
                "allocation_type": "temporary",
                "allocation_date": "2026-03-10",
                "purpose": "Short-term use.",
                "condition_out": "good",
                "status": "active",
            },
            format="json",
        )

        self.assertEqual(response.status_code, 400, response.data)
        self.assertIn("Temporary allocations require an expected return date.", str(response.data))

    def test_allocation_requires_exactly_one_recipient(self):
        admin = self.create_user("admin_user", ROLE_ADMIN, self.comp_sci)
        lecturer = self.create_user("recipient_user", ROLE_LECTURER, self.comp_sci)
        asset = self.create_asset("Shared Projector", self.comp_lab, admin)

        self.client.force_authenticate(admin)
        response = self.client.post(
            "/api/allocations/",
            {
                "asset": asset.id,
                "allocated_to": lecturer.id,
                "allocated_to_lab": self.comp_lab.id,
                "allocation_type": "temporary",
                "allocation_date": "2026-03-10",
                "expected_return_date": "2026-03-15",
                "purpose": "Conflicting recipient test.",
                "condition_out": "good",
                "status": "active",
            },
            format="json",
        )

        self.assertEqual(response.status_code, 400, response.data)
        self.assertIn("Allocate the asset to exactly one recipient", str(response.data))

    def test_allocation_rejects_return_date_earlier_than_issue_date(self):
        admin = self.create_user("admin_user", ROLE_ADMIN, self.comp_sci)
        lecturer = self.create_user("datecheck_user", ROLE_LECTURER, self.comp_sci)
        asset = self.create_asset("Date Checked Laptop", self.comp_lab, admin)

        self.client.force_authenticate(admin)
        response = self.client.post(
            "/api/allocations/",
            {
                "asset": asset.id,
                "allocated_to": lecturer.id,
                "allocation_type": "temporary",
                "allocation_date": "2026-03-10",
                "expected_return_date": "2026-03-09",
                "purpose": "Invalid date range.",
                "condition_out": "good",
                "status": "active",
            },
            format="json",
        )

        self.assertEqual(response.status_code, 400, response.data)
        self.assertIn("Expected return date cannot be earlier than the allocation date.", str(response.data))

    def test_asset_cannot_receive_two_active_allocations(self):
        admin = self.create_user("admin_user", ROLE_ADMIN, self.comp_sci)
        first_holder = self.create_user("first_holder", ROLE_LECTURER, self.comp_sci)
        second_holder = self.create_user("second_holder", ROLE_LECTURER, self.comp_sci)
        asset = self.create_asset("Single-Issue Laptop", self.comp_lab, admin)

        self.client.force_authenticate(admin)
        first_response = self.client.post(
            "/api/allocations/",
            {
                "asset": asset.id,
                "allocated_to": first_holder.id,
                "allocation_type": "temporary",
                "allocation_date": "2026-03-10",
                "expected_return_date": "2026-03-15",
                "purpose": "First issue.",
                "condition_out": "good",
                "status": "active",
            },
            format="json",
        )

        self.assertEqual(first_response.status_code, 201, first_response.data)

        second_response = self.client.post(
            "/api/allocations/",
            {
                "asset": asset.id,
                "allocated_to": second_holder.id,
                "allocation_type": "temporary",
                "allocation_date": "2026-03-11",
                "expected_return_date": "2026-03-16",
                "purpose": "Second issue should fail.",
                "condition_out": "good",
                "status": "active",
            },
            format="json",
        )

        self.assertEqual(second_response.status_code, 400, second_response.data)
        self.assertIn("This asset already has an active allocation.", str(second_response.data))

    def test_cod_cannot_allocate_asset_from_another_department(self):
        cod = self.create_user("comp_cod", ROLE_COD, self.comp_sci)
        lecturer = self.create_user("comp_lecturer", ROLE_LECTURER, self.comp_sci)
        maths_asset = self.create_asset("Math Department Laptop", self.maths_office, cod)

        self.client.force_authenticate(cod)
        response = self.client.post(
            "/api/allocations/",
            {
                "asset": maths_asset.id,
                "allocated_to": lecturer.id,
                "allocation_type": "temporary",
                "allocation_date": "2026-03-10",
                "expected_return_date": "2026-03-15",
                "purpose": "Should be blocked for CoD scope.",
                "condition_out": "good",
                "status": "active",
            },
            format="json",
        )

        self.assertEqual(response.status_code, 400, response.data)
        self.assertIn("CoD users can only allocate assets from their own department.", str(response.data))

    def test_cod_cannot_allocate_asset_to_user_in_another_department(self):
        cod = self.create_user("comp_cod", ROLE_COD, self.comp_sci)
        maths_lecturer = self.create_user("math_lecturer", ROLE_LECTURER, self.maths)
        asset = self.create_asset("Comp Department Laptop", self.comp_lab, cod)

        self.client.force_authenticate(cod)
        response = self.client.post(
            "/api/allocations/",
            {
                "asset": asset.id,
                "allocated_to": maths_lecturer.id,
                "allocation_type": "temporary",
                "allocation_date": "2026-03-10",
                "expected_return_date": "2026-03-15",
                "purpose": "Should be blocked for cross-department allocation.",
                "condition_out": "good",
                "status": "active",
            },
            format="json",
        )

        self.assertEqual(response.status_code, 400, response.data)
        self.assertIn("CoD users can only allocate assets to users in their own department.", str(response.data))


class AuditLogTests(BaseAPITestCase):
    def test_asset_crud_writes_audit_entries(self):
        admin = self.create_user("asset_admin", ROLE_ADMIN, self.comp_sci)

        self.client.force_authenticate(admin)
        create_response = self.client.post(
            "/api/assets/",
            {
                "name": "Tracked Laptop",
                "category": self.category.id,
                "description": "Tracked asset",
                "purchase_date": "2026-03-01",
                "purchase_cost": "1200.00",
                "supplier": self.supplier.id,
                "current_location": self.comp_lab.id,
                "condition": "good",
                "status": "available",
                "serial_number": "SER-TRACK-1",
            },
            format="json",
        )

        self.assertEqual(create_response.status_code, 201, create_response.data)
        asset_id = create_response.data["id"]

        update_response = self.client.patch(
            f"/api/assets/{asset_id}/",
            {
                "name": "Tracked Laptop Updated",
                "status": "maintenance",
            },
            format="json",
        )
        self.assertEqual(update_response.status_code, 200, update_response.data)

        delete_response = self.client.delete(f"/api/assets/{asset_id}/")
        self.assertEqual(delete_response.status_code, 204)

        logs = list(
            AuditLog.objects.filter(actor=admin, target_content_type__app_label="assets", target_content_type__model="asset")
            .order_by("created_at")
            .values_list("action", flat=True)
        )
        self.assertEqual(logs, [AuditLog.ACTION_CREATE, AuditLog.ACTION_UPDATE, AuditLog.ACTION_DELETE])


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

    def test_maintenance_rejects_completed_date_earlier_than_scheduled_date(self):
        technician = self.create_user("tech_user", ROLE_LAB_TECHNICIAN, self.comp_sci)
        asset = self.create_asset("Spectrometer", self.comp_lab, technician)

        self.client.force_authenticate(technician)
        response = self.client.post(
            "/api/maintenance/",
            {
                "asset": asset.id,
                "maintenance_type": "corrective",
                "scheduled_date": "2026-03-11",
                "completed_date": "2026-03-10",
                "description": "Invalid completion date test.",
                "status": "completed",
            },
            format="json",
        )

        self.assertEqual(response.status_code, 400, response.data)
        self.assertIn("Completed date cannot be earlier than the scheduled date.", str(response.data))


class AssetLifecycleTests(BaseAPITestCase):
    def test_asset_creation_auto_generates_barcode_from_asset_id(self):
        cod = self.create_user("cod_user", ROLE_COD, self.comp_sci)

        self.client.force_authenticate(cod)
        response = self.client.post(
            "/api/assets/",
            {
                "name": "Barcode Printer",
                "category": self.category.id,
                "description": "Department printer",
                "purchase_date": "2026-03-10",
                "purchase_cost": "2500.00",
                "supplier": self.supplier.id,
                "current_location": self.comp_lab.id,
                "condition": "good",
                "status": "available",
                "serial_number": "SN-2026-001",
            },
            format="json",
        )

        self.assertEqual(response.status_code, 201, response.data)
        self.assertTrue(response.data["asset_id"])
        self.assertTrue(response.data["asset_id"].startswith("COMP-26-"))
        self.assertEqual(response.data["barcode"], response.data["asset_id"])

        asset = Asset.objects.get(pk=response.data["id"])
        self.assertEqual(asset.barcode, asset.asset_id)

    def test_cod_cannot_move_asset_to_location_in_another_department(self):
        cod = self.create_user("cod_user", ROLE_COD, self.comp_sci)
        asset = self.create_asset("Projector", self.comp_lab, cod)

        self.client.force_authenticate(cod)
        response = self.client.patch(
            f"/api/assets/{asset.id}/",
            {"current_location": self.maths_office.id},
            format="json",
        )

        self.assertEqual(response.status_code, 400, response.data)
        self.assertIn("CoD users can only manage assets in their own department.", str(response.data))
        self.assertFalse(AssetMovement.objects.filter(asset=asset).exists())

    def test_admin_asset_location_update_creates_movement_record(self):
        admin = self.create_user("admin_user", ROLE_ADMIN, self.comp_sci)
        asset = self.create_asset("Projector", self.comp_lab, admin)

        self.client.force_authenticate(admin)
        response = self.client.patch(
            f"/api/assets/{asset.id}/",
            {"current_location": self.maths_office.id},
            format="json",
        )

        self.assertEqual(response.status_code, 200, response.data)
        movement = AssetMovement.objects.get(asset=asset)
        self.assertEqual(movement.from_location, self.comp_lab)
        self.assertEqual(movement.to_location, self.maths_office)
        self.assertEqual(movement.moved_by, admin)

    def test_asset_creation_generates_depreciation_records(self):
        cod = self.create_user("cod_user", ROLE_COD, self.comp_sci)
        asset = self.create_asset("Server Rack", self.comp_lab, cod)

        records = DepreciationRecord.objects.filter(asset=asset)
        self.assertTrue(records.exists())
        self.assertEqual(records.first().year, 2026)

    def test_reports_expose_movement_history_and_depreciation_summary(self):
        admin = User.objects.create_superuser("admin", "admin@example.com", "pass12345Strong")
        asset = self.create_asset("3D Printer", self.comp_lab, admin)
        AssetMovement.objects.create(
            asset=asset,
            from_location=self.comp_lab,
            to_location=self.maths_office,
            moved_by=admin,
            notes="Transferred for faculty demo.",
        )

        self.client.force_authenticate(admin)
        movement_response = self.client.get("/api/reports/asset-movements/")
        depreciation_response = self.client.get("/api/reports/depreciation-summary/")

        self.assertEqual(movement_response.status_code, 200)
        self.assertEqual(depreciation_response.status_code, 200)
        self.assertEqual(movement_response.data[0]["asset_identifier"], asset.asset_id)
        self.assertIn("totals", depreciation_response.data)
        self.assertGreaterEqual(len(depreciation_response.data["records"]), 1)

    def test_internal_auditor_report_endpoints_use_global_scope(self):
        auditor = self.create_user("reportauditor", ROLE_INTERNAL_AUDITOR)
        self.create_asset("Comp Asset", self.comp_lab, auditor)
        self.create_asset("Math Asset", self.maths_office, auditor)

        self.client.force_authenticate(auditor)
        dashboard_response = self.client.get("/api/reports/dashboard/")
        distribution_response = self.client.get("/api/reports/assets-by-department/")

        self.assertEqual(dashboard_response.status_code, 200)
        self.assertEqual(distribution_response.status_code, 200)
        self.assertEqual(dashboard_response.data["total_assets"], 2)
        self.assertEqual(len(distribution_response.data), 2)


class AssetThumbnailTests(BaseAPITestCase):
    def setUp(self):
        super().setUp()
        self.temp_media_root = Path(settings.BASE_DIR) / "test-media"
        self.temp_media_root.mkdir(parents=True, exist_ok=True)
        self.addCleanup(lambda: shutil.rmtree(self.temp_media_root, ignore_errors=True))

    def test_asset_thumbnail_upload_returns_thumbnail_url(self):
        cod = self.create_user("cod_user", ROLE_COD, self.comp_sci)
        asset = self.create_asset("Camera", self.comp_lab, cod)
        thumbnail = SimpleUploadedFile(
            "thumb.gif",
            (
                b"GIF89a\x01\x00\x01\x00\x80\x00\x00\x00\x00\x00"
                b"\xff\xff\xff!\xf9\x04\x01\x00\x00\x00\x00,\x00\x00\x00\x00"
                b"\x01\x00\x01\x00\x00\x02\x02D\x01\x00;"
            ),
            content_type="image/gif",
        )

        self.client.force_authenticate(cod)
        with override_settings(MEDIA_ROOT=str(self.temp_media_root)):
            response = self.client.post(
                f"/api/assets/{asset.id}/thumbnail/",
                {"thumbnail": thumbnail},
                format="multipart",
            )
            detail_response = self.client.get(f"/api/assets/{asset.id}/")

        self.assertEqual(response.status_code, 200, response.data)
        self.assertEqual(detail_response.status_code, 200, detail_response.data)

        asset.refresh_from_db()
        self.assertTrue(asset.thumbnail.name)
        self.assertIn(asset.asset_id, asset.thumbnail.name)
        self.assertTrue(response.data["thumbnail_url"].startswith("http://testserver/media/assets/"))
        self.assertEqual(detail_response.data["thumbnail_url"], response.data["thumbnail_url"])


class OperationalAndDisposalWorkflowTests(BaseAPITestCase):
    def test_health_endpoint_is_public(self):
        response = self.client.get("/api/health/")

        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.data["status"], "ok")
        self.assertEqual(response.data["application"], "FASSETS")

    def test_asset_disposal_requires_reason(self):
        admin = self.create_user("disposal_admin", ROLE_ADMIN, self.comp_sci)
        asset = self.create_asset("Disposed Printer", self.comp_lab, admin)

        self.client.force_authenticate(admin)
        response = self.client.patch(
            f"/api/assets/{asset.id}/",
            {
                "status": "disposed",
                "disposal_reason": "",
            },
            format="json",
        )

        self.assertEqual(response.status_code, 400, response.data)
        self.assertIn("Provide a disposal reason", str(response.data))

    def test_asset_disposal_sets_timestamp_and_restore_clears_metadata(self):
        admin = self.create_user("restore_admin", ROLE_ADMIN, self.comp_sci)
        asset = self.create_asset("Restore Candidate", self.comp_lab, admin)

        self.client.force_authenticate(admin)
        dispose_response = self.client.patch(
            f"/api/assets/{asset.id}/",
            {
                "status": "disposed",
                "disposal_reason": "Beyond economical repair.",
                "disposal_reference": "DISP-2026-04",
            },
            format="json",
        )

        self.assertEqual(dispose_response.status_code, 200, dispose_response.data)
        asset.refresh_from_db()
        self.assertEqual(asset.status, "disposed")
        self.assertEqual(asset.disposal_reason, "Beyond economical repair.")
        self.assertEqual(asset.disposal_reference, "DISP-2026-04")
        self.assertIsNotNone(asset.disposed_at)

        restore_response = self.client.patch(
            f"/api/assets/{asset.id}/",
            {
                "status": "available",
            },
            format="json",
        )

        self.assertEqual(restore_response.status_code, 200, restore_response.data)
        asset.refresh_from_db()
        self.assertEqual(asset.status, "available")
        self.assertIsNone(asset.disposed_at)
        self.assertEqual(asset.disposal_reason, "")
        self.assertEqual(asset.disposal_reference, "")

    def test_asset_disposal_is_blocked_when_active_allocation_exists(self):
        admin = self.create_user("dispose_block_admin", ROLE_ADMIN, self.comp_sci)
        lecturer = self.create_user("dispose_holder", ROLE_LECTURER, self.comp_sci)
        asset = self.create_asset("Allocated Laptop", self.comp_lab, admin)
        Allocation.objects.create(
            asset=asset,
            allocated_to=lecturer,
            allocated_by=admin,
            allocation_type="temporary",
            allocation_date=datetime.date(2026, 3, 10),
            expected_return_date=datetime.date(2026, 3, 15),
            purpose="Issued before disposal attempt.",
            condition_out="good",
            status="active",
        )

        self.client.force_authenticate(admin)
        response = self.client.patch(
            f"/api/assets/{asset.id}/",
            {
                "status": "disposed",
                "disposal_reason": "Broken screen.",
            },
            format="json",
        )

        self.assertEqual(response.status_code, 400, response.data)
        self.assertIn("active allocations", str(response.data))

    def test_direct_asset_save_cannot_bypass_disposal_validation(self):
        admin = self.create_user("direct_disposal_admin", ROLE_ADMIN, self.comp_sci)
        lecturer = self.create_user("direct_disposal_holder", ROLE_LECTURER, self.comp_sci)
        asset = self.create_asset("Direct Save Laptop", self.comp_lab, admin)
        Allocation.objects.create(
            asset=asset,
            allocated_to=lecturer,
            allocated_by=admin,
            allocation_type="temporary",
            allocation_date=datetime.date(2026, 3, 10),
            expected_return_date=datetime.date(2026, 3, 15),
            purpose="Issued before ORM disposal attempt.",
            condition_out="good",
            status="active",
        )

        asset.status = "disposed"
        asset.disposal_reason = "Attempted bypass."

        with self.assertRaises(ValidationError):
            asset.save()

    def test_asset_disposal_is_blocked_when_open_maintenance_exists(self):
        technician = self.create_user("dispose_tech", ROLE_LAB_TECHNICIAN, self.comp_sci)
        asset = self.create_asset("Maintained Device", self.comp_lab, technician)
        Maintenance.objects.create(
            asset=asset,
            maintenance_type="corrective",
            scheduled_date=datetime.date(2026, 3, 12),
            reported_by=technician,
            description="Open repair ticket.",
            status="scheduled",
        )

        self.client.force_authenticate(technician)
        response = self.client.patch(
            f"/api/assets/{asset.id}/",
            {
                "status": "disposed",
                "disposal_reason": "Obsolete unit.",
            },
            format="json",
        )

        self.assertEqual(response.status_code, 400, response.data)
        self.assertIn("open maintenance", str(response.data))

    def test_maintenance_cannot_be_created_for_disposed_asset(self):
        technician = self.create_user("disposed_tech", ROLE_LAB_TECHNICIAN, self.comp_sci)
        asset = self.create_asset("Disposed Microscope", self.comp_lab, technician)
        asset.status = "disposed"
        asset.disposal_reason = "Condemned after inspection."
        asset.save(update_fields=["status", "disposal_reason", "updated_at"])

        self.client.force_authenticate(technician)
        response = self.client.post(
            "/api/maintenance/",
            {
                "asset": asset.id,
                "maintenance_type": "corrective",
                "scheduled_date": "2026-03-11",
                "description": "Should be rejected because the asset is disposed.",
                "status": "scheduled",
            },
            format="json",
        )

        self.assertEqual(response.status_code, 400, response.data)
        self.assertIn("Disposed assets cannot be scheduled for maintenance.", str(response.data))
