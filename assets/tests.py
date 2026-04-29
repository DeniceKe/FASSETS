import datetime

from django.contrib.auth import get_user_model
from django.core.exceptions import ValidationError
from django.test import TestCase
from django.urls import reverse
from django.utils import timezone

from accounts.models import AuditLog, Department, Faculty
from accounts.roles import ROLE_INTERNAL_AUDITOR
from assets.models import Asset, Category, Location, Supplier
from assets.notifications import build_user_notifications
from allocations.models import Allocation, AssetRequest
from maintenance.models import Maintenance

User = get_user_model()


class DashboardRequestTests(TestCase):
    def setUp(self):
        faculty = Faculty.objects.create(name="Faculty of Science")
        self.department = Department.objects.create(code="MATH", name="Mathematics", faculty=faculty)
        other_department = Department.objects.create(code="BIO", name="Biology", faculty=faculty)
        self.category = Category.objects.create(name="ICT")
        self.supplier = Supplier.objects.create(name="Campus Supplier")
        self.location = Location.objects.create(
            department=self.department,
            building="Main Block",
            floor="1",
            room="101",
            room_type="office",
        )
        self.lab_location = Location.objects.create(
            department=self.department,
            building="Physical Science Complex",
            floor="2",
            room="Lab 2",
            room_type="lab",
        )
        self.other_location = Location.objects.create(
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
        self.unavailable_asset = Asset.objects.create(
            name="Math Laptop Reserved",
            category=self.category,
            description="Unavailable asset",
            purchase_date=datetime.date(2026, 3, 1),
            purchase_cost=1100,
            supplier=self.supplier,
            current_location=self.location,
            created_by=self.admin,
            status="allocated",
        )
        Asset.objects.create(
            name="Bio Laptop",
            category=self.category,
            description="Hidden asset",
            purchase_date=datetime.date(2026, 3, 1),
            purchase_cost=1000,
            supplier=self.supplier,
            current_location=self.other_location,
            created_by=self.admin,
        )
        self.user = User.objects.create_user("mathuser", password="pass12345Strong")
        self.user.profile.department = self.department
        self.user.profile.user_type = "student"
        self.user.profile.registration_number = "MTH/001/26"
        self.user.profile.save()
        self.request_start = timezone.now() + datetime.timedelta(days=1)
        self.request_end = self.request_start + datetime.timedelta(days=2)
        self.usage_location = "Mathematics Lab 1"
        self.handover_location = "Main Block Reception Desk"
        self.issue_person_details = "Mr. James Kariuki, Store Officer, Ext. 204"

    def make_request_payload(self, **overrides):
        payload = {
            "message": "Need this asset for practical instruction.",
            "requested_start_at": self.request_start.strftime("%Y-%m-%dT%H:%M"),
            "requested_end_at": self.request_end.strftime("%Y-%m-%dT%H:%M"),
            "usage_location": self.usage_location,
        }
        payload.update(overrides)
        return payload

    def create_pending_request(self, **overrides):
        data = {
            "asset": self.visible_asset,
            "requested_by": self.user,
            "message": "Please approve this request.",
            "requested_start_at": self.request_start,
            "requested_end_at": self.request_end,
            "usage_location": self.usage_location,
        }
        data.update(overrides)
        return AssetRequest.objects.create(**data)

    def test_user_dashboard_is_department_scoped_and_can_request_available_asset(self):
        self.client.force_login(self.user)
        response = self.client.get("/dashboard/")

        self.assertEqual(response.context["default_dashboard_section"], "personal-overview")
        self.assertNotContains(response, "Math Laptop")
        self.assertNotContains(response, "Math Laptop Reserved")
        self.assertNotContains(response, "Bio Laptop")
        self.assertContains(response, "Search for an asset first")

        search_response = self.client.get("/dashboard/", {"asset_search": "Math Laptop"})
        self.assertEqual(search_response.context["default_dashboard_section"], "department-assets")
        self.assertContains(search_response, "Math Laptop")
        self.assertNotContains(search_response, "Math Laptop Reserved")
        self.assertNotContains(search_response, "Bio Laptop")

        request_response = self.client.post(
            f"/assets/{self.visible_asset.id}/request/",
            self.make_request_payload(),
        )
        self.assertRedirects(request_response, "/dashboard/")

        asset_request = AssetRequest.objects.get(asset=self.visible_asset, requested_by=self.user, status="pending")
        self.assertEqual(asset_request.message, "Need this asset for practical instruction.")
        self.assertEqual(asset_request.usage_location, self.usage_location)
        self.assertEqual(
            asset_request.requested_start_at.strftime("%Y-%m-%dT%H:%M"),
            self.make_request_payload()["requested_start_at"],
        )
        self.assertEqual(
            asset_request.requested_end_at.strftime("%Y-%m-%dT%H:%M"),
            self.make_request_payload()["requested_end_at"],
        )
        self.assertTrue(
            AuditLog.objects.filter(
                actor=self.user,
                action=AuditLog.ACTION_CREATE,
                target_object_id=str(asset_request.id),
                source=reverse("assets:request_asset", args=[self.visible_asset.id]),
            ).exists()
        )

    def test_user_can_search_assets_within_their_department(self):
        Asset.objects.create(
            name="Math Projector",
            category=self.category,
            description="Second visible asset",
            purchase_date=datetime.date(2026, 3, 2),
            purchase_cost=900,
            supplier=self.supplier,
            current_location=self.location,
            created_by=self.admin,
        )
        self.client.force_login(self.user)

        response = self.client.get("/dashboard/", {"asset_search": "projector"})

        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "Math Projector")
        self.assertNotContains(response, "Bio Laptop")
        self.assertContains(response, 'name="asset_search"', html=False)
        self.assertContains(response, 'value="projector"', html=False)
        self.assertEqual(response.context["department_assets_total"], 1)
        self.assertEqual([asset.name for asset in response.context["department_assets"]], ["Math Projector"])

    def test_regular_user_search_only_returns_available_assets(self):
        self.client.force_login(self.user)

        response = self.client.get("/dashboard/", {"asset_search": "Math Laptop"})

        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "Math Laptop")
        self.assertNotContains(response, "Math Laptop Reserved")
        self.assertEqual([asset.name for asset in response.context["department_assets"]], ["Math Laptop"])

    def test_user_request_requires_reason_time_and_place(self):
        self.client.force_login(self.user)

        response = self.client.post(
            f"/assets/{self.visible_asset.id}/request/",
            {"message": "", "requested_start_at": "", "requested_end_at": "", "usage_location": ""},
        )

        self.assertEqual(response.status_code, 400)
        self.assertContains(response, "Reason for request", status_code=400)
        self.assertContains(response, "This field is required.", status_code=400)
        self.assertFalse(AssetRequest.objects.filter(asset=self.visible_asset, requested_by=self.user).exists())

    def test_user_dashboard_hides_admin_links_and_api_endpoint_monitoring(self):
        self.client.force_login(self.user)
        response = self.client.get("/dashboard/")

        self.assertNotContains(response, "/api/reports/dashboard/")
        self.assertNotContains(response, "Proposal report endpoints")
        self.assertNotContains(response, 'href="/admin/"')
        self.assertNotContains(response, "Activity Overview")
        self.assertNotContains(response, ">Reports<", html=False)
        self.assertContains(response, "Help Center")
        self.assertContains(response, "Your recent asset requests")

    def test_dashboard_help_center_shows_role_aligned_topics(self):
        self.client.force_login(self.user)

        response = self.client.get("/dashboard/")

        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "Help topics aligned to what your account can do")
        self.assertContains(response, "Request an asset correctly")
        self.assertContains(response, "Return an asset correctly")
        self.assertContains(response, "Open Full Help Center")
        self.assertNotContains(response, "Search a user and review assigned assets")
        self.assertNotContains(response, "Open the reports center for oversight review")

    def test_help_center_is_public_and_searchable(self):
        response = self.client.get(reverse("assets:help_center"))

        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "Help Center")
        self.assertContains(response, "Search Help")
        self.assertContains(response, "Sign in and open the right workspace")
        self.assertNotContains(response, "Request an asset correctly")
        self.assertContains(response, reverse("login"))

        search_response = self.client.get(reverse("assets:help_center"), {"q": "maintenance"})

        self.assertEqual(search_response.status_code, 200)
        self.assertContains(search_response, 'value="maintenance"', html=False)
        self.assertContains(search_response, "No help topics matched that search")
        self.assertNotContains(search_response, "Report an issue or maintenance need")

        sign_in_search_response = self.client.get(reverse("assets:help_center"), {"q": "sign in"})

        self.assertEqual(sign_in_search_response.status_code, 200)
        self.assertContains(sign_in_search_response, "Sign in and open the right workspace")
        self.assertContains(sign_in_search_response, "Open Login")

    def test_dashboard_links_to_help_center(self):
        self.client.force_login(self.user)

        response = self.client.get("/dashboard/")

        self.assertEqual(response.status_code, 200)
        self.assertContains(response, reverse("assets:help_center"))
        self.assertContains(response, "Open Help Center")

    def test_dashboard_renders_visual_insights_charts(self):
        self.client.force_login(self.user)

        response = self.client.get("/dashboard/")

        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "Visual Insights")
        self.assertContains(response, "Asset status distribution")
        self.assertContains(response, "Top categories by asset volume")
        self.assertContains(response, "Allocations and maintenance over time")
        self.assertEqual(len(response.context["dashboard_status_chart"]), 4)
        self.assertTrue(response.context["dashboard_category_chart"])
        self.assertTrue(response.context["dashboard_department_chart"])
        self.assertEqual(len(response.context["dashboard_activity_chart"]), 6)

    def test_reports_center_can_export_pdf_and_excel(self):
        self.client.force_login(self.admin)

        pdf_response = self.client.get(
            reverse("assets:reports_center"),
            {"export": "pdf", "section": "inventory-report"},
        )
        excel_response = self.client.get(
            reverse("assets:reports_center"),
            {"export": "excel", "section": "inventory-report"},
        )

        self.assertEqual(pdf_response.status_code, 200)
        self.assertEqual(pdf_response["Content-Type"], "application/pdf")
        self.assertIn("inventory-report-", pdf_response["Content-Disposition"])
        self.assertTrue(pdf_response.content.startswith(b"%PDF-1.4"))

        self.assertEqual(excel_response.status_code, 200)
        self.assertEqual(excel_response["Content-Type"], "application/vnd.ms-excel")
        self.assertIn("inventory-report-", excel_response["Content-Disposition"])
        self.assertIn(b'<?xml version="1.0"?>', excel_response.content)
        self.assertIn(b"Inventory Report", excel_response.content)

    def test_qr_tracking_page_and_label_views_resolve_visible_asset(self):
        self.visible_asset.barcode = "MATH-TRACK-01"
        self.visible_asset.save(update_fields=["barcode", "updated_at"])
        self.client.force_login(self.user)

        tracker_response = self.client.get(reverse("assets:asset_tracker"), {"code": "https://fassets.example/tracking/?code=MATH-TRACK-01"})
        qr_image_response = self.client.get(reverse("assets:asset_qr_image", args=[self.visible_asset.id]))
        qr_label_response = self.client.get(reverse("assets:asset_qr_label", args=[self.visible_asset.id]))

        self.assertEqual(tracker_response.status_code, 200)
        self.assertContains(tracker_response, "QR Tracking")
        self.assertContains(tracker_response, self.visible_asset.asset_id)
        self.assertContains(tracker_response, self.visible_asset.name)
        self.assertEqual(tracker_response.context["normalized_tracking_code"], "MATH-TRACK-01")
        self.assertEqual(tracker_response.context["tracked_asset"], self.visible_asset)

        self.assertEqual(qr_image_response.status_code, 200)
        self.assertEqual(qr_image_response["Content-Type"], "image/png")
        self.assertTrue(qr_image_response.content.startswith(b"\x89PNG\r\n\x1a\n"))

        self.assertEqual(qr_label_response.status_code, 200)
        self.assertContains(qr_label_response, "FASSETS Asset Label")
        self.assertContains(qr_label_response, self.visible_asset.asset_id)
        self.assertContains(qr_label_response, reverse("assets:asset_tracker"))

    def test_authenticated_help_center_hides_topics_outside_user_role(self):
        self.client.force_login(self.user)

        response = self.client.get(reverse("assets:help_center"))

        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "Request an asset correctly")
        self.assertContains(response, "Return an asset correctly")
        self.assertNotContains(response, "Search a user and review assigned assets")
        self.assertNotContains(response, "Open the reports center for oversight review")

    def test_user_dashboard_shows_assets_under_their_care(self):
        furniture_category = Category.objects.create(name="Furniture")
        chair_asset = Asset.objects.create(
            name="Office Chair",
            category=furniture_category,
            description="Assigned chair",
            purchase_date=datetime.date(2026, 3, 6),
            purchase_cost=250,
            supplier=self.supplier,
            current_location=self.location,
            created_by=self.admin,
        )
        Allocation.objects.create(
            asset=self.visible_asset,
            allocated_to=self.user,
            allocated_by=self.admin,
            allocation_date=timezone.localdate(),
            expected_return_date=timezone.localdate() + datetime.timedelta(days=14),
            purpose="Issued for teaching preparation.",
            condition_out=self.visible_asset.condition,
            status="active",
        )
        Allocation.objects.create(
            asset=chair_asset,
            allocated_to=self.user,
            allocated_by=self.admin,
            allocation_date=timezone.localdate(),
            expected_return_date=timezone.localdate() + datetime.timedelta(days=21),
            purpose="Issued for office support.",
            condition_out=chair_asset.condition,
            status="active",
        )
        self.client.force_login(self.user)

        response = self.client.get("/dashboard/")

        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "Assets currently assigned to you")
        self.assertContains(response, self.visible_asset.name)
        self.assertContains(response, chair_asset.name)
        self.assertContains(response, "Under Your Care")
        self.assertContains(response, "Total assigned assets")
        self.assertContains(response, ">2<", html=False)
        self.assertContains(response, "ICT")
        self.assertContains(response, "Furniture")
        self.assertContains(response, "Condition")
        self.assertContains(response, "Return")
        self.assertContains(response, "Action")
        self.assertContains(response, "Report An Issue")
        self.assertContains(response, "Send Issue Report")
        self.assertNotContains(response, "Issue Help")
        self.assertNotContains(response, "Return Steps")
        self.assertNotContains(response, "If this asset has a fault, damage, missing part, or maintenance need")
        self.assertNotContains(response, "Issue details")
        self.assertEqual(response.context["assets_under_care_total"], 2)
        self.assertEqual(
            list(response.context["assets_under_care_by_category"]),
            [
                {"asset__category__name": "Furniture", "total": 1},
                {"asset__category__name": "ICT", "total": 1},
            ],
        )

    def test_user_dashboard_shows_due_return_and_maintenance_notifications(self):
        Allocation.objects.create(
            asset=self.visible_asset,
            allocated_to=self.user,
            allocated_by=self.admin,
            allocation_type="temporary",
            allocation_date=timezone.localdate(),
            expected_return_date=timezone.localdate() + datetime.timedelta(days=2),
            purpose="Issued for class preparation.",
            condition_out=self.visible_asset.condition,
            status="active",
        )
        Maintenance.objects.create(
            asset=self.visible_asset,
            maintenance_type="preventive",
            scheduled_date=timezone.localdate(),
            reported_by=self.admin,
            description="Routine servicing before the next lab session.",
            status="scheduled",
        )
        self.client.force_login(self.user)

        response = self.client.get("/dashboard/")

        self.assertEqual(response.status_code, 200)
        self.assertContains(response, 'class="notification-bell has-alert"', html=False)
        self.assertContains(response, 'aria-label="Open notifications"', html=False)
        self.assertContains(response, '<span class="notification-bell-badge">2</span>', html=False)
        self.assertContains(response, 'title="Scheduled maintenance today"', html=False)
        self.assertContains(
            response,
            f'href="{reverse("assets:dashboard")}?focus_asset_id={self.visible_asset.id}&amp;notification=',
            html=False,
        )
        self.assertEqual(response.context["dashboard_notification_count"], 2)
        self.assertEqual(
            [notification["title"] for notification in response.context["dashboard_notifications"]],
            ["Scheduled maintenance today", "Return due soon"],
        )
        self.assertTrue(all(notification["action_required"] for notification in response.context["dashboard_notifications"]))

    def test_user_dashboard_shows_empty_reminder_state_when_nothing_is_due(self):
        Allocation.objects.create(
            asset=self.visible_asset,
            allocated_to=self.user,
            allocated_by=self.admin,
            allocation_type="permanent",
            allocation_date=timezone.localdate(),
            purpose="Issued for continuing use.",
            condition_out=self.visible_asset.condition,
            status="active",
        )
        self.client.force_login(self.user)

        response = self.client.get("/dashboard/")

        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "No reminders right now")
        self.assertNotContains(response, 'class="notification-bell has-alert"', html=False)
        self.assertContains(response, '<span class="notification-bell-badge">0</span>', html=False)
        self.assertEqual(response.context["dashboard_notification_count"], 0)
        self.assertEqual(response.context["dashboard_notifications"], [])

    def test_lab_technician_dashboard_shows_assigned_scheduled_maintenance_notification(self):
        technician = User.objects.create_user("mathtech", password="pass12345Strong")
        technician.profile.department = self.department
        technician.profile.role = "lab_technician"
        technician.profile.user_type = "staff"
        technician.profile.employee_id = "TECH-ALERT-001"
        technician.profile.save()

        maintenance_record = Maintenance.objects.create(
            asset=self.visible_asset,
            maintenance_type="preventive",
            scheduled_date=timezone.localdate(),
            technician=technician,
            reported_by=self.admin,
            description="Routine servicing assigned to the lab technician.",
            status="scheduled",
        )

        self.client.force_login(technician)
        response = self.client.get("/dashboard/")

        self.assertEqual(response.status_code, 200)
        self.assertContains(response, 'class="notification-bell has-alert"', html=False)
        self.assertContains(response, 'title="Assigned maintenance today"', html=False)
        self.assertContains(
            response,
            f'href="{reverse("assets:workspace_resource", kwargs={"resource": "maintenance"})}?search={self.visible_asset.asset_id}&amp;edit={maintenance_record.id}&amp;notification=',
            html=False,
        )
        self.assertEqual(response.context["dashboard_notification_count"], 1)
        self.assertEqual(
            [notification["title"] for notification in response.context["dashboard_notifications"]],
            ["Assigned maintenance today"],
        )
        self.assertTrue(all(notification["action_required"] for notification in response.context["dashboard_notifications"]))

    def test_dashboard_notification_focus_highlights_target_asset_and_shows_maintenance_context(self):
        Allocation.objects.create(
            asset=self.visible_asset,
            allocated_to=self.user,
            allocated_by=self.admin,
            allocation_type="temporary",
            allocation_date=timezone.localdate(),
            expected_return_date=timezone.localdate() + datetime.timedelta(days=2),
            purpose="Issued for class preparation.",
            condition_out=self.visible_asset.condition,
            status="active",
        )
        Maintenance.objects.create(
            asset=self.visible_asset,
            maintenance_type="preventive",
            scheduled_date=timezone.localdate(),
            reported_by=self.admin,
            description="Routine servicing before the next lab session.",
            status="scheduled",
        )

        self.client.force_login(self.user)
        notification_id = next(
            notification["id"]
            for notification in build_user_notifications(self.user)
            if notification["title"] == "Scheduled maintenance today"
        )
        response = self.client.get(
            reverse("assets:dashboard"),
            {"focus_asset_id": self.visible_asset.id, "notification": notification_id},
        )

        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "Notification Reason")
        self.assertContains(response, "Scheduled maintenance today")
        self.assertContains(response, "Make the asset available for servicing today and pause normal use until the technician has completed the work.")
        self.assertContains(response, f'id="asset-care-{self.visible_asset.id}"', html=False)
        self.assertContains(response, 'class="asset-care-row is-notification-focus"', html=False)
        self.assertContains(response, "Routine servicing before the next lab session.")

    def test_maintenance_workspace_shows_notification_reason_banner(self):
        technician = User.objects.create_user("workspacetech", password="pass12345Strong")
        technician.profile.department = self.department
        technician.profile.role = "lab_technician"
        technician.profile.user_type = "staff"
        technician.profile.employee_id = "TECH-WORKSPACE-001"
        technician.profile.save()

        maintenance_record = Maintenance.objects.create(
            asset=self.visible_asset,
            maintenance_type="preventive",
            scheduled_date=timezone.localdate(),
            technician=technician,
            reported_by=self.admin,
            description="Technician workspace reminder.",
            status="scheduled",
        )

        notification_id = next(
            notification["id"]
            for notification in build_user_notifications(technician)
            if notification["title"] == "Assigned maintenance today"
        )

        self.client.force_login(technician)
        response = self.client.get(
            reverse("assets:workspace_resource", kwargs={"resource": "maintenance"}),
            {
                "search": self.visible_asset.asset_id,
                "edit": maintenance_record.id,
                "notification": notification_id,
            },
        )

        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "Notification Reason")
        self.assertContains(response, "Assigned maintenance today")
        self.assertContains(response, "Technician workspace reminder.")

    def test_user_dashboard_shows_more_than_six_assigned_assets(self):
        asset_names = []
        for index in range(8):
            asset = Asset.objects.create(
                name=f"Assigned Device {index + 1}",
                category=self.category,
                description="Assigned asset",
                purchase_date=datetime.date(2026, 3, 10 + index),
                purchase_cost=500 + index,
                supplier=self.supplier,
                current_location=self.location,
                created_by=self.admin,
            )
            Allocation.objects.create(
                asset=asset,
                allocated_to=self.user,
                allocated_by=self.admin,
                allocation_type="permanent",
                allocation_date=timezone.localdate() + datetime.timedelta(days=index),
                purpose="Issued for continuing use.",
                condition_out=asset.condition,
                status="active",
            )
            asset_names.append(asset.name)

        self.client.force_login(self.user)

        response = self.client.get("/dashboard/")

        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.context["assets_under_care_total"], 8)
        self.assertEqual(len(response.context["assets_under_care"]), 8)
        for asset_name in asset_names:
            self.assertContains(response, asset_name)

    def test_user_can_report_issue_for_asset_under_their_care(self):
        Allocation.objects.create(
            asset=self.visible_asset,
            allocated_to=self.user,
            allocated_by=self.admin,
            allocation_date=timezone.localdate(),
            expected_return_date=timezone.localdate() + datetime.timedelta(days=14),
            purpose="Issued for teaching preparation.",
            condition_out=self.visible_asset.condition,
            status="active",
        )
        self.client.force_login(self.user)

        response = self.client.post(
            reverse("assets:report_asset_issue", args=[self.visible_asset.id]),
            {"description": "The laptop battery is failing and the hinge is loose."},
            follow=True,
        )

        self.assertRedirects(response, f"{reverse('assets:dashboard')}#personal-overview")
        self.assertContains(response, "Your maintenance report for Math Laptop has been submitted.")
        maintenance_record = Maintenance.objects.get(asset=self.visible_asset, reported_by=self.user)
        self.assertEqual(maintenance_record.maintenance_type, "corrective")
        self.assertEqual(maintenance_record.status, "scheduled")
        self.assertEqual(maintenance_record.description, "The laptop battery is failing and the hinge is loose.")
        self.assertTrue(
            AuditLog.objects.filter(
                actor=self.user,
                action=AuditLog.ACTION_CREATE,
                target_object_id=str(maintenance_record.id),
                source=reverse("assets:report_asset_issue", args=[self.visible_asset.id]),
            ).exists()
        )

    def test_role_assigned_user_sees_workspace_tools_on_dashboard(self):
        self.user.profile.role = "cod"
        self.user.profile.save()
        self.client.force_login(self.user)

        response = self.client.get("/dashboard/")

        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "Activity Overview")
        self.assertContains(response, "Workspace Tools")
        self.assertContains(response, "Asset Manager")
        self.assertContains(response, reverse("assets:workspace_resource", kwargs={"resource": "assets"}))
        self.assertContains(response, reverse("assets:workspace_resource", kwargs={"resource": "maintenance"}))

    def test_non_admin_role_does_not_see_workspace_tools_on_dashboard(self):
        self.user.profile.role = "lecturer"
        self.user.profile.save()
        self.client.force_login(self.user)

        response = self.client.get("/dashboard/")

        self.assertEqual(response.status_code, 200)
        self.assertNotContains(response, "Workspace Tools")
        self.assertNotContains(response, reverse("assets:workspace_resource", kwargs={"resource": "assets"}))

    def test_lab_technician_sees_lab_operations_tools_on_dashboard(self):
        self.user.profile.role = "lab_technician"
        self.user.profile.save()
        self.client.force_login(self.user)

        response = self.client.get("/dashboard/")

        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.context["default_dashboard_section"], "role-workspace")
        self.assertContains(response, "Workspace Tools")
        self.assertContains(response, "Activity Overview")
        self.assertContains(response, "Asset Manager")
        self.assertContains(response, "Allocation Manager")
        self.assertContains(response, "Maintenance Manager")
        self.assertContains(response, reverse("assets:workspace_resource", kwargs={"resource": "assets"}))
        self.assertContains(response, reverse("assets:workspace_resource", kwargs={"resource": "allocations"}))
        self.assertContains(response, reverse("assets:workspace_resource", kwargs={"resource": "maintenance"}))
        self.assertNotContains(response, reverse("assets:workspace_resource", kwargs={"resource": "users"}))
        self.assertContains(response, "View and manage assets assigned to your labs, including status, condition, and availability.")
        self.assertContains(response, "Check assets in and out for lab use and keep issue activity current.")

    def test_lab_technician_with_allocated_asset_defaults_to_personal_overview(self):
        self.user.profile.role = "lab_technician"
        self.user.profile.save()
        Allocation.objects.create(
            asset=self.visible_asset,
            allocated_to=self.user,
            allocated_by=self.admin,
            allocation_type="permanent",
            allocation_date=timezone.localdate(),
            purpose="Permanently issued lab support laptop.",
            condition_out=self.visible_asset.condition,
            status="active",
        )
        self.client.force_login(self.user)

        response = self.client.get("/dashboard/")

        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.context["default_dashboard_section"], "personal-overview")
        self.assertContains(response, "Assets currently assigned to you")
        self.assertContains(response, self.visible_asset.name)

    def test_lab_technician_must_search_to_load_department_assets(self):
        self.user.profile.role = "lab_technician"
        self.user.profile.save()
        self.client.force_login(self.user)

        response = self.client.get("/dashboard/")

        self.assertEqual(response.status_code, 200)
        self.assertNotContains(response, "Math Laptop")
        self.assertContains(response, "Search for an asset first")

    def test_cod_must_search_to_load_department_assets(self):
        self.user.profile.role = "cod"
        self.user.profile.save()
        self.client.force_login(self.user)

        response = self.client.get("/dashboard/")

        self.assertEqual(response.status_code, 200)
        self.assertNotContains(response, "Math Laptop")
        self.assertContains(response, "Search for an asset first")

    def test_cod_search_can_still_see_unavailable_assets(self):
        self.user.profile.role = "cod"
        self.user.profile.save()
        self.client.force_login(self.user)

        response = self.client.get("/dashboard/", {"asset_search": "Reserved"})

        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "Math Laptop Reserved")

    def test_role_assigned_user_can_open_workspace_manager_from_account(self):
        self.user.profile.role = "cod"
        self.user.profile.save()
        self.client.force_login(self.user)

        response = self.client.get(reverse("assets:workspace_resource", kwargs={"resource": "assets"}))

        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "Workspace Tools")
        self.assertContains(response, "Asset Manager")
        self.assertContains(response, "New Asset")

    def test_admin_role_asset_workspace_exposes_allocate_to_user_shortcut(self):
        admin_user = User.objects.create_user("assetallocator", password="pass12345Strong")
        admin_user.profile.department = self.department
        admin_user.profile.role = "admin"
        admin_user.profile.user_type = "staff"
        admin_user.profile.employee_id = "ADM-ALLOC-001"
        admin_user.profile.save()
        self.client.force_login(admin_user)

        response = self.client.get(reverse("assets:workspace_resource", kwargs={"resource": "assets"}))

        self.assertEqual(response.status_code, 200)
        self.assertTrue(response.context["allocation_shortcuts"]["enabled"])
        self.assertEqual(
            response.context["allocation_shortcuts"]["manager_url"],
            reverse("assets:workspace_resource", kwargs={"resource": "allocations"}),
        )
        self.assertContains(response, "Allocate To User")
        self.assertContains(response, reverse("assets:workspace_resource", kwargs={"resource": "allocations"}))

    def test_non_admin_role_without_workspace_access_cannot_open_workspace_manager_from_account(self):
        self.user.profile.role = "lecturer"
        self.user.profile.save()
        self.client.force_login(self.user)

        response = self.client.get(
            reverse("assets:workspace_resource", kwargs={"resource": "assets"}),
            follow=True,
        )

        self.assertRedirects(response, reverse("assets:dashboard"))
        self.assertContains(response, "Your account role does not have access to that workspace.")

    def test_lab_technician_can_open_maintenance_workspace_from_account(self):
        self.user.profile.role = "lab_technician"
        self.user.profile.save()
        self.client.force_login(self.user)

        response = self.client.get(reverse("assets:workspace_resource", kwargs={"resource": "maintenance"}))

        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "Maintenance Manager")
        self.assertContains(response, "New Maintenance")
        self.assertFalse(response.context["workspace_permissions"]["can_delete"])

    def test_lab_technician_can_open_asset_workspace_from_account(self):
        self.user.profile.role = "lab_technician"
        self.user.profile.save()
        self.client.force_login(self.user)

        response = self.client.get(reverse("assets:workspace_resource", kwargs={"resource": "assets"}))

        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "Asset Manager")
        self.assertContains(response, "New Asset")
        self.assertContains(response, "Quick help")
        self.assertContains(response, "Required fields are marked with *.")
        self.assertContains(response, "Restore Last Clear")
        self.assertFalse(response.context["workspace_permissions"]["can_delete"])

    def test_lab_technician_can_open_allocation_workspace_from_account(self):
        self.user.profile.role = "lab_technician"
        self.user.profile.save()
        self.client.force_login(self.user)

        response = self.client.get(reverse("assets:workspace_resource", kwargs={"resource": "allocations"}))

        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "Allocation Manager")
        self.assertContains(response, "New Allocation")
        self.assertFalse(response.context["workspace_permissions"]["can_delete"])
        self.assertContains(response, "Allocate To")
        self.assertContains(response, 'field-recipient_mode', html=False)
        self.assertContains(response, "toggleAllocationFieldVisibility")
        self.assertContains(response, "Allocation Type")
        self.assertContains(response, 'field-expected_return_date', html=False)
        self.assertContains(response, 'field-condition_in', html=False)

    def test_admin_role_user_gets_management_tools_from_dashboard_without_admin_nav(self):
        admin_user = User.objects.create_user("dashboardadmin", password="pass12345Strong")
        admin_user.profile.department = self.department
        admin_user.profile.role = "admin"
        admin_user.profile.user_type = "staff"
        admin_user.profile.employee_id = "ADM-002"
        admin_user.profile.save()
        self.client.force_login(admin_user)

        response = self.client.get("/dashboard/")

        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "Reports")
        self.assertContains(response, reverse("assets:reports_center"))
        self.assertContains(response, f'{reverse("assets:reports_center")}#dashboard-summary')
        self.assertContains(response, "Workspace Tools")
        self.assertContains(response, reverse("assets:workspace_resource", kwargs={"resource": "users"}))
        self.assertContains(response, reverse("assets:workspace_resource", kwargs={"resource": "assets"}))
        self.assertNotContains(response, 'href="/admin/"')

    def test_admin_can_open_reports_center_from_dashboard_account(self):
        admin_user = User.objects.create_user("reportsadmin", password="pass12345Strong")
        admin_user.profile.department = self.department
        admin_user.profile.role = "admin"
        admin_user.profile.user_type = "staff"
        admin_user.profile.employee_id = "ADM-004"
        admin_user.profile.save()
        self.client.force_login(admin_user)

        response = self.client.get(reverse("assets:reports_center"))

        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "Generated Report")
        self.assertContains(response, "Department distribution")
        self.assertContains(response, "Maintenance records")
        self.assertNotContains(response, "Generate reports by date, maintenance status, asset status, and condition")
        self.assertNotContains(response, "Use one filter set to narrow the report tables below before printing or saving the report.")
        self.assertNotContains(response, "Available assets ignore request and maintenance status filters.")
        self.assertContains(response, "Generated By")
        self.assertContains(response, admin_user.username)
        self.assertContains(response, "Generated On")
        self.assertContains(response, "Print Current Report")
        self.assertContains(response, "FASSETS Official Report Copy")
        self.assertContains(response, "Fixed Assets Management System")
        self.assertContains(response, "Reviewed By")
        self.assertContains(response, "Approved By")
        self.assertContains(response, "Assets matching the current query")
        self.assertContains(response, self.visible_asset.name)
        self.assertContains(response, 'data-report-target="inventory-report"', html=False)
        self.assertContains(response, 'data-report-section="inventory-report"', html=False)
        self.assertNotContains(response, "Readable system reports for oversight accounts")
        self.assertNotContains(response, "Review reporting from one dashboard-style page instead of raw API responses.")
        self.assertNotContains(response, "Summary cards use live totals.")
        self.assertContains(response, 'data-report-target="assigned-assets"', html=False)
        self.assertContains(response, 'data-report-target="returned-assets"', html=False)
        self.assertContains(response, 'data-report-section="assigned-assets"', html=False)
        self.assertContains(response, 'data-report-section="returned-assets"', html=False)
        self.assertContains(response, 'data-report-section="maintenance-history"', html=False)
        self.assertContains(response, "showReportSection")
        self.assertContains(response, "reports-center-nav-link is-active")

    def test_reports_center_print_view_uses_clean_print_template_for_inventory_section(self):
        admin_user = User.objects.create_user("reportsprintadmin", password="pass12345Strong")
        admin_user.profile.department = self.department
        admin_user.profile.role = "admin"
        admin_user.profile.user_type = "staff"
        admin_user.profile.employee_id = "ADM-PRINT-001"
        admin_user.profile.save()
        self.client.force_login(admin_user)

        response = self.client.get(
            reverse("assets:reports_center"),
            {
                "print": "1",
                "section": "inventory-report",
            },
        )

        self.assertEqual(response.status_code, 200)
        self.assertTemplateUsed(response, "reports_center_print.html")
        self.assertContains(response, "Inventory Report")
        self.assertContains(response, "Assets matching the current query")
        self.assertContains(response, self.visible_asset.name)
        self.assertContains(response, "Generated By")
        self.assertContains(response, "Generated On")
        self.assertContains(response, "Active Filters")
        self.assertNotContains(response, 'data-report-target="inventory-report"', html=False)
        self.assertNotContains(response, "Print Current Report")

    def test_reports_center_can_filter_by_date_condition_category_and_maintenance_status(self):
        projector_category = Category.objects.create(name="Projectors")
        filtered_asset = Asset.objects.create(
            name="Excellent Projector",
            category=projector_category,
            description="Scheduled maintenance report target.",
            purchase_date=datetime.date(2026, 3, 10),
            purchase_cost=2200,
            supplier=self.supplier,
            current_location=self.location,
            created_by=self.admin,
            condition="excellent",
        )
        non_matching_asset = Asset.objects.create(
            name="Old Office Chair",
            category=Category.objects.create(name="Furniture"),
            description="Should not match the report query.",
            purchase_date=datetime.date(2026, 2, 10),
            purchase_cost=350,
            supplier=self.supplier,
            current_location=self.location,
            created_by=self.admin,
            condition="poor",
        )
        Maintenance.objects.create(
            asset=filtered_asset,
            maintenance_type="preventive",
            scheduled_date=datetime.date(2026, 4, 12),
            reported_by=self.admin,
            description="Scheduled projector service.",
            status="scheduled",
        )
        Maintenance.objects.create(
            asset=non_matching_asset,
            maintenance_type="corrective",
            scheduled_date=datetime.date(2026, 2, 12),
            reported_by=self.admin,
            description="Chair frame repair.",
            status="completed",
            completed_date=datetime.date(2026, 2, 13),
        )

        self.client.force_login(self.admin)
        response = self.client.get(
            reverse("assets:reports_center"),
            {
                "date_from": "2026-04-01",
                "date_to": "2026-04-30",
                "asset_condition": "excellent",
                "asset_category": str(projector_category.id),
                "maintenance_status": "scheduled",
            },
        )

        self.assertEqual(response.status_code, 200)
        self.assertContains(response, 'name="date_from"', html=False)
        self.assertContains(response, 'name="date_to"', html=False)
        self.assertContains(response, 'name="asset_condition"', html=False)
        self.assertContains(response, "Generate Report")
        self.assertContains(response, "Active Filters")
        self.assertContains(response, "Asset Condition: Excellent")
        self.assertContains(response, "Excellent Projector")
        self.assertEqual([asset.name for asset in response.context["inventory_assets"]], ["Excellent Projector"])
        self.assertEqual([item.asset.name for item in response.context["maintenance_report"]], ["Excellent Projector"])
        self.assertEqual(
            [row["current_location__department__name"] for row in response.context["assets_by_department"]],
            ["Mathematics"],
        )

    def test_reports_center_ignores_request_and_maintenance_status_when_inventory_is_available(self):
        report_date = timezone.localdate().isoformat()
        available_category = Category.objects.create(name="Portable Devices")
        available_asset = Asset.objects.create(
            name="Available Tablet",
            category=available_category,
            description="Available asset report target.",
            purchase_date=datetime.date(2026, 4, 9),
            purchase_cost=1800,
            supplier=self.supplier,
            current_location=self.location,
            created_by=self.admin,
            condition="excellent",
            status="available",
        )
        AssetRequest.objects.create(
            asset=available_asset,
            requested_by=self.user,
            message="Need the tablet for a field data collection class.",
            requested_start_at=timezone.now() + datetime.timedelta(days=1),
            requested_end_at=timezone.now() + datetime.timedelta(days=2),
            usage_location="Field Lab",
            status="pending",
        )
        Maintenance.objects.create(
            asset=available_asset,
            maintenance_type="corrective",
            scheduled_date=datetime.date(2026, 4, 11),
            completed_date=datetime.date(2026, 4, 12),
            reported_by=self.admin,
            description="Screen protector replaced and device checked.",
            status="completed",
        )
        available_asset.refresh_from_db()

        self.client.force_login(self.admin)
        response = self.client.get(
            reverse("assets:reports_center"),
            {
                "inventory_status": "available",
                "date_from": report_date,
                "date_to": report_date,
                "asset_condition": "excellent",
                "asset_category": str(available_category.id),
                "request_status": "cancelled",
                "maintenance_status": "scheduled",
            },
        )

        self.assertEqual(response.status_code, 200)
        self.assertEqual(available_asset.status, "available")
        self.assertEqual(response.context["request_status"], "")
        self.assertEqual(response.context["maintenance_status"], "")
        self.assertIn("Asset Status: Available", response.context["report_active_filters_text"])
        self.assertNotIn("Request Status", response.context["report_active_filters_text"])
        self.assertNotIn("Maintenance Status", response.context["report_active_filters_text"])
        self.assertNotContains(response, "Available assets ignore request and maintenance status filters.")
        self.assertContains(response, "Available Tablet")
        self.assertEqual([asset.name for asset in response.context["inventory_assets"]], ["Available Tablet"])
        self.assertEqual([item.asset.name for item in response.context["asset_requests_report"]], ["Available Tablet"])
        self.assertEqual(list(response.context["maintenance_report"]), [])

    def test_internal_auditor_dashboard_gets_global_read_only_tools(self):
        auditor_user = User.objects.create_user("internalauditor", password="pass12345Strong")
        auditor_user.profile.role = ROLE_INTERNAL_AUDITOR
        auditor_user.profile.user_type = "staff"
        auditor_user.profile.employee_id = "AUD-001"
        auditor_user.profile.save()
        self.client.force_login(auditor_user)

        response = self.client.get("/dashboard/")
        search_response = self.client.get("/dashboard/", {"asset_search": "Bio"})

        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "Reports")
        self.assertContains(response, "Workspace Tools")
        self.assertContains(response, reverse("assets:workspace_resource", kwargs={"resource": "assets"}))
        self.assertContains(response, reverse("assets:workspace_resource", kwargs={"resource": "users"}))
        self.assertContains(response, "Administrator and auditor accounts can review inventory here, but they cannot submit asset requests.")
        self.assertContains(response, "Search for an asset first")
        self.assertContains(search_response, "Bio Laptop")
        self.assertEqual(response.context["user_role"], "Auditor")

    def test_internal_auditor_can_open_read_only_workspace(self):
        auditor_user = User.objects.create_user("auditorworkspace", password="pass12345Strong")
        auditor_user.profile.role = ROLE_INTERNAL_AUDITOR
        auditor_user.profile.user_type = "staff"
        auditor_user.profile.employee_id = "AUD-002"
        auditor_user.profile.save()
        self.client.force_login(auditor_user)

        response = self.client.get(reverse("assets:workspace_resource", kwargs={"resource": "assets"}))

        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "Asset Manager")
        self.assertContains(response, "Read-only access")
        self.assertFalse(response.context["workspace_permissions"]["can_create"])
        self.assertFalse(response.context["workspace_permissions"]["can_edit"])
        self.assertFalse(response.context["workspace_permissions"]["can_delete"])

    def test_internal_auditor_can_open_reports_center(self):
        auditor_user = User.objects.create_user("auditorreports", password="pass12345Strong")
        auditor_user.profile.role = ROLE_INTERNAL_AUDITOR
        auditor_user.profile.user_type = "staff"
        auditor_user.profile.employee_id = "AUD-003"
        auditor_user.profile.save()
        self.client.force_login(auditor_user)

        response = self.client.get(reverse("assets:reports_center"))

        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "Generated Report")
        self.assertContains(response, "Department distribution")
        self.assertContains(response, "Maintenance records")
        self.assertContains(response, "Assets matching the current query")
        self.assertNotContains(response, "Readable system reports for oversight accounts")

    def test_cod_dashboard_shows_reports_access(self):
        cod_user = User.objects.create_user("codreportsdashboard", password="pass12345Strong")
        cod_user.profile.department = self.department
        cod_user.profile.role = "cod"
        cod_user.profile.user_type = "staff"
        cod_user.profile.employee_id = "COD-REPORTS-001"
        cod_user.profile.save()
        self.client.force_login(cod_user)

        response = self.client.get("/dashboard/")

        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "Generate reports")
        self.assertContains(response, reverse("assets:reports_center"))
        self.assertContains(response, "Reports Center")

    def test_cod_can_open_department_scoped_reports_center(self):
        cod_user = User.objects.create_user("codreports", password="pass12345Strong")
        cod_user.profile.department = self.department
        cod_user.profile.role = "cod"
        cod_user.profile.user_type = "staff"
        cod_user.profile.employee_id = "COD-REPORTS-002"
        cod_user.profile.save()

        self.client.force_login(cod_user)
        response = self.client.get(reverse("assets:reports_center"))

        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "Generated Report")
        self.assertContains(response, "Math Laptop")
        self.assertNotContains(response, "Bio Laptop")
        self.assertContains(response, "Assets matching the current query")
        self.assertNotContains(response, "Readable system reports for oversight accounts")
        self.assertEqual(
            [row["current_location__department__name"] for row in response.context["assets_by_department"]],
            ["Mathematics"],
        )

    def test_regular_user_cannot_open_reports_center(self):
        self.client.force_login(self.user)

        response = self.client.get(reverse("assets:reports_center"))

        self.assertEqual(response.status_code, 404)

    def test_admin_can_open_user_manager_with_delete_permission(self):
        admin_user = User.objects.create_user("usermanageradmin", password="pass12345Strong")
        admin_user.profile.department = self.department
        admin_user.profile.role = "admin"
        admin_user.profile.user_type = "staff"
        admin_user.profile.employee_id = "ADM-003"
        admin_user.profile.save()
        self.client.force_login(admin_user)

        response = self.client.get(reverse("assets:workspace_resource", kwargs={"resource": "users"}))

        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "User Manager")
        self.assertTrue(response.context["workspace_permissions"]["can_delete"])
        self.assertContains(response, "workspace-delete-action")
        self.assertNotContains(response, ">Password<", html=False)
        self.assertContains(response, "toggleUserFieldVisibility")
        self.assertContains(response, "toggleUserIdentityFieldEditability")
        self.assertContains(response, "read_only_on_edit")
        self.assertContains(response, 'field-registration_number', html=False)
        self.assertContains(response, 'field-employee_id', html=False)

    def test_cod_can_open_department_user_manager_from_account(self):
        cod_user = User.objects.create_user("codmanager", password="pass12345Strong")
        cod_user.profile.department = self.department
        cod_user.profile.role = "cod"
        cod_user.profile.user_type = "staff"
        cod_user.profile.employee_id = "COD-001"
        cod_user.profile.save()
        self.client.force_login(cod_user)

        response = self.client.get(reverse("assets:workspace_resource", kwargs={"resource": "users"}))

        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "User Manager")
        self.assertContains(response, "New User")
        self.assertNotContains(response, "Read-only access")
        self.assertNotContains(response, ">Password<", html=False)
        self.assertContains(response, "toggleUserFieldVisibility")
        self.assertContains(response, "toggleUserIdentityFieldEditability")

    def test_cod_dashboard_shows_department_asset_category_breakdown(self):
        laptop_category = Category.objects.create(name="HP Laptops")
        printer_category = Category.objects.create(name="Printers")
        projector_category = Category.objects.create(name="Projectors")
        cod_user = User.objects.create_user("codsummary", password="pass12345Strong")
        cod_user.profile.department = self.department
        cod_user.profile.role = "cod"
        cod_user.profile.user_type = "staff"
        cod_user.profile.employee_id = "COD-002"
        cod_user.profile.save()

        Asset.objects.create(
            name="HP EliteBook 1",
            category=laptop_category,
            description="Department laptop",
            purchase_date=datetime.date(2026, 3, 3),
            purchase_cost=1200,
            supplier=self.supplier,
            current_location=self.location,
            created_by=self.admin,
            status="available",
        )
        Asset.objects.create(
            name="HP EliteBook 2",
            category=laptop_category,
            description="Department laptop",
            purchase_date=datetime.date(2026, 3, 4),
            purchase_cost=1200,
            supplier=self.supplier,
            current_location=self.location,
            created_by=self.admin,
            status="available",
        )
        Asset.objects.create(
            name="Office Printer",
            category=printer_category,
            description="Disposed printer",
            purchase_date=datetime.date(2026, 3, 5),
            purchase_cost=800,
            supplier=self.supplier,
            current_location=self.location,
            created_by=self.admin,
            status="disposed",
            disposal_reason="Disposed after repeated breakdowns.",
        )
        Asset.objects.create(
            name="Lecture Hall Projector",
            category=projector_category,
            description="Allocated projector",
            purchase_date=datetime.date(2026, 3, 6),
            purchase_cost=1500,
            supplier=self.supplier,
            current_location=self.location,
            created_by=self.admin,
            status="allocated",
        )
        other_department_category = Category.objects.create(name="Biology Projectors")
        Asset.objects.create(
            name="Biology Projector",
            category=other_department_category,
            description="Other department asset",
            purchase_date=datetime.date(2026, 3, 7),
            purchase_cost=1500,
            supplier=self.supplier,
            current_location=Location.objects.get(department__code="BIO"),
            created_by=self.admin,
            status="allocated",
        )

        self.client.force_login(cod_user)
        response = self.client.get("/dashboard/", {"category_search": "MATH"})

        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.context["default_dashboard_section"], "category-control")
        self.assertContains(response, "Manage department assets by category")
        summary = {row["category__name"]: row for row in response.context["department_category_breakdown"]}
        self.assertEqual(summary["HP Laptops"]["available_count"], 2)
        self.assertEqual(summary["HP Laptops"]["allocated_count"], 0)
        self.assertEqual(summary["Printers"]["disposed_count"], 1)
        self.assertEqual(summary["Projectors"]["allocated_count"], 1)
        self.assertNotIn("Biology Projectors", summary)

    def test_cod_category_control_search_is_independent_from_department_asset_search(self):
        self.user.profile.role = "cod"
        self.user.profile.save()
        Asset.objects.create(
            name="Math Projector",
            category=self.category,
            description="Department projector",
            purchase_date=datetime.date(2026, 3, 8),
            purchase_cost=950,
            supplier=self.supplier,
            current_location=self.location,
            created_by=self.admin,
        )
        self.client.force_login(self.user)

        response = self.client.get("/dashboard/", {"category_search": "projector"})

        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.context["default_dashboard_section"], "category-control")
        self.assertContains(response, 'name="category_search"', html=False)
        self.assertContains(response, 'value="projector"', html=False)
        self.assertEqual(response.context["department_assets_total"], 0)
        self.assertEqual(response.context["category_assets_total"], 1)
        self.assertEqual([asset.name for asset in response.context["department_assets"]], [])
        self.assertEqual([asset.name for asset in response.context["category_assets"]], ["Math Projector"])

    def test_inventory_views_search_is_independent_from_department_asset_search(self):
        self.user.profile.role = "cod"
        self.user.profile.save()
        Asset.objects.create(
            name="Math Projector",
            category=self.category,
            description="Inventory search asset",
            purchase_date=datetime.date(2026, 3, 8),
            purchase_cost=950,
            supplier=self.supplier,
            current_location=self.location,
            created_by=self.admin,
        )
        self.client.force_login(self.user)

        response = self.client.get("/dashboard/", {"inventory_search": "projector"})

        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.context["default_dashboard_section"], "inventory-views")
        self.assertContains(response, 'name="inventory_search"', html=False)
        self.assertContains(response, 'value="projector"', html=False)
        self.assertEqual(response.context["department_assets_total"], 0)
        self.assertEqual([asset.name for asset in response.context["recent_assets"]], ["Math Projector"])
        self.assertEqual(list(response.context["department_distribution"])[0]["current_location__department__name"], "Mathematics")

    def test_activity_overview_search_is_independent_from_department_asset_search(self):
        self.user.profile.role = "cod"
        self.user.profile.save()
        technician = User.objects.create_user("mathtech", password="pass12345Strong")
        technician.profile.department = self.department
        technician.profile.role = "lab_technician"
        technician.profile.user_type = "staff"
        technician.profile.employee_id = "TECH-001"
        technician.profile.save()
        Allocation.objects.create(
            asset=self.visible_asset,
            allocated_to=self.user,
            allocated_by=self.admin,
            allocation_date=timezone.localdate(),
            expected_return_date=timezone.localdate() + datetime.timedelta(days=7),
            purpose="Math Laptop issued for practical prep.",
            condition_out=self.visible_asset.condition,
            status="active",
        )
        Maintenance.objects.create(
            asset=self.visible_asset,
            maintenance_type="corrective",
            scheduled_date=timezone.localdate(),
            technician=technician,
            reported_by=self.admin,
            description="Math Laptop hinge inspection.",
            status="scheduled",
        )
        self.client.force_login(self.user)

        response = self.client.get("/dashboard/", {"activity_search": "Math Laptop"})

        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.context["default_dashboard_section"], "activity-overview")
        self.assertContains(response, 'name="activity_search"', html=False)
        self.assertContains(response, 'value="Math Laptop"', html=False)
        self.assertEqual(response.context["department_assets_total"], 0)
        self.assertEqual([allocation.asset.name for allocation in response.context["recent_allocations"]], ["Math Laptop"])
        self.assertEqual([item.asset.name for item in response.context["recent_maintenance"]], ["Math Laptop"])

    def test_superuser_dashboard_does_not_offer_asset_request_submission(self):
        self.client.force_login(self.admin)

        response = self.client.get("/dashboard/")
        search_response = self.client.get("/dashboard/", {"asset_search": "Math Laptop"})

        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "Administrator and auditor accounts can review inventory here, but they cannot submit asset requests.")
        self.assertNotContains(response, reverse("assets:request_asset", args=[self.visible_asset.id]))
        self.assertContains(response, "Search for an asset first")
        self.assertContains(search_response, "Manage Asset")
        self.assertContains(
            search_response,
            f'{reverse("assets:workspace_resource", kwargs={"resource": "assets"})}?edit={self.visible_asset.id}&search={self.visible_asset.asset_id}',
            html=False,
        )
        self.assertNotContains(search_response, reverse("assets:request_asset", args=[self.visible_asset.id]))

    def test_internal_auditor_department_assets_action_opens_review_workspace(self):
        auditor_user = User.objects.create_user("auditoraction", password="pass12345Strong")
        auditor_user.profile.role = ROLE_INTERNAL_AUDITOR
        auditor_user.profile.user_type = "staff"
        auditor_user.profile.employee_id = "AUD-ACTION-001"
        auditor_user.profile.save()
        self.client.force_login(auditor_user)

        response = self.client.get("/dashboard/", {"asset_search": "Math Laptop"})

        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "Review Asset")
        self.assertContains(
            response,
            f'{reverse("assets:workspace_resource", kwargs={"resource": "assets"})}?search={self.visible_asset.asset_id}',
            html=False,
        )

    def test_admin_role_account_cannot_request_asset(self):
        admin_user = User.objects.create_user("departmentadmin", password="pass12345Strong")
        admin_user.profile.department = self.department
        admin_user.profile.role = "admin"
        admin_user.profile.user_type = "staff"
        admin_user.profile.employee_id = "ADM-001"
        admin_user.profile.save()
        self.client.force_login(admin_user)

        response = self.client.post(
            reverse("assets:request_asset", args=[self.visible_asset.id]),
            self.make_request_payload(),
            follow=True,
        )

        self.assertRedirects(response, reverse("assets:dashboard"))
        self.assertContains(response, "Administrator and auditor accounts cannot request assets.")
        self.assertFalse(AssetRequest.objects.filter(asset=self.visible_asset, requested_by=admin_user).exists())

    def test_internal_auditor_account_cannot_request_asset(self):
        auditor_user = User.objects.create_user("departmentauditor", password="pass12345Strong")
        auditor_user.profile.role = ROLE_INTERNAL_AUDITOR
        auditor_user.profile.user_type = "staff"
        auditor_user.profile.employee_id = "AUD-004"
        auditor_user.profile.save()
        self.client.force_login(auditor_user)

        response = self.client.post(
            reverse("assets:request_asset", args=[self.visible_asset.id]),
            self.make_request_payload(),
            follow=True,
        )

        self.assertRedirects(response, reverse("assets:dashboard"))
        self.assertContains(response, "Administrator and auditor accounts cannot request assets.")
        self.assertFalse(AssetRequest.objects.filter(asset=self.visible_asset, requested_by=auditor_user).exists())

    def test_admin_can_approve_pending_asset_request(self):
        asset_request = self.create_pending_request()
        self.client.force_login(self.admin)

        response = self.client.post(
            reverse("admin:review_asset_request", args=[asset_request.id]),
            {
                "action": "approve",
                "handover_location": self.handover_location,
                "issue_person_details": self.issue_person_details,
            },
        )

        self.assertRedirects(response, reverse("admin:index"))
        asset_request.refresh_from_db()
        self.visible_asset.refresh_from_db()
        allocation = Allocation.objects.get(asset=self.visible_asset, allocated_to=self.user)

        self.assertEqual(asset_request.status, "approved")
        self.assertEqual(asset_request.reviewed_by, self.admin)
        self.assertIsNotNone(asset_request.reviewed_at)
        self.assertEqual(asset_request.decline_reason, "")
        self.assertEqual(asset_request.handover_location, self.handover_location)
        self.assertEqual(asset_request.issue_person_details, self.issue_person_details)
        self.assertEqual(allocation.allocated_by, self.admin)
        self.assertEqual(allocation.purpose, "Please approve this request.")
        self.assertEqual(allocation.condition_out, self.visible_asset.condition)
        self.assertEqual(allocation.expected_return_date, allocation.allocation_date + datetime.timedelta(days=14))
        self.assertEqual(allocation.status, "active")
        self.assertEqual(self.visible_asset.status, "allocated")
        self.assertTrue(
            AuditLog.objects.filter(
                actor=self.admin,
                action=AuditLog.ACTION_CREATE,
                target_object_id=str(allocation.id),
                source=reverse("admin:review_asset_request", args=[asset_request.id]),
            ).exists()
        )
        self.assertTrue(
            AuditLog.objects.filter(
                actor=self.admin,
                action=AuditLog.ACTION_UPDATE,
                target_object_id=str(asset_request.id),
                source=reverse("admin:review_asset_request", args=[asset_request.id]),
            ).exists()
        )

    def test_user_dashboard_shows_handover_details_for_approved_request(self):
        AssetRequest.objects.create(
            asset=self.visible_asset,
            requested_by=self.user,
            status="approved",
            reviewed_by=self.admin,
            reviewed_at=timezone.now(),
            handover_location=self.handover_location,
            issue_person_details=self.issue_person_details,
            message="Please approve this request.",
            requested_start_at=self.request_start,
            requested_end_at=self.request_end,
            usage_location=self.usage_location,
        )
        self.client.force_login(self.user)

        response = self.client.get("/dashboard/")

        self.assertContains(response, "Issued By")
        self.assertContains(response, "Handover Place")
        self.assertContains(response, self.issue_person_details)
        self.assertContains(response, self.handover_location)

    def test_user_can_cancel_own_pending_request(self):
        asset_request = self.create_pending_request()
        self.client.force_login(self.user)

        response = self.client.post(reverse("assets:cancel_request", args=[asset_request.id]))

        self.assertRedirects(response, "/dashboard/")
        asset_request.refresh_from_db()
        self.assertEqual(asset_request.status, "cancelled")
        self.assertIsNone(asset_request.reviewed_by)
        self.assertIsNone(asset_request.reviewed_at)
        self.assertTrue(
            AuditLog.objects.filter(
                actor=self.user,
                action=AuditLog.ACTION_UPDATE,
                target_object_id=str(asset_request.id),
                source=reverse("assets:cancel_request", args=[asset_request.id]),
            ).exists()
        )

    def test_user_cannot_cancel_non_pending_request(self):
        asset_request = AssetRequest.objects.create(
            asset=self.visible_asset,
            requested_by=self.user,
            status="approved",
            reviewed_by=self.admin,
            reviewed_at=timezone.now(),
            handover_location=self.handover_location,
            issue_person_details=self.issue_person_details,
            message="Please approve this request.",
            requested_start_at=self.request_start,
            requested_end_at=self.request_end,
            usage_location=self.usage_location,
        )
        self.client.force_login(self.user)

        response = self.client.post(reverse("assets:cancel_request", args=[asset_request.id]))

        self.assertRedirects(response, "/dashboard/")
        asset_request.refresh_from_db()
        self.assertEqual(asset_request.status, "approved")

    def test_admin_approval_requires_pickup_place_and_issuer_details(self):
        asset_request = self.create_pending_request()
        self.client.force_login(self.admin)

        response = self.client.post(
            reverse("admin:review_asset_request", args=[asset_request.id]),
            {"action": "approve", "handover_location": "", "issue_person_details": ""},
        )

        self.assertRedirects(response, reverse("admin:index"))
        asset_request.refresh_from_db()
        self.assertEqual(asset_request.status, "pending")
        self.assertFalse(Allocation.objects.filter(asset=self.visible_asset, allocated_to=self.user).exists())

    def test_admin_must_provide_decline_reason(self):
        asset_request = self.create_pending_request()
        self.client.force_login(self.admin)

        response = self.client.post(
            reverse("admin:review_asset_request", args=[asset_request.id]),
            {"action": "decline", "decline_reason": ""},
        )

        self.assertRedirects(response, reverse("admin:index"))
        asset_request.refresh_from_db()
        self.assertEqual(asset_request.status, "pending")

    def test_admin_approval_does_not_change_request_when_asset_is_no_longer_available(self):
        asset_request = self.create_pending_request()
        self.visible_asset.status = "maintenance"
        self.visible_asset.save(update_fields=["status", "updated_at"])
        self.client.force_login(self.admin)

        response = self.client.post(
            reverse("admin:review_asset_request", args=[asset_request.id]),
            {
                "action": "approve",
                "handover_location": self.handover_location,
                "issue_person_details": self.issue_person_details,
            },
        )

        self.assertRedirects(response, reverse("admin:index"))
        asset_request.refresh_from_db()
        self.assertEqual(asset_request.status, "pending")
        self.assertFalse(Allocation.objects.filter(asset=self.visible_asset, allocated_to=self.user).exists())

    def test_admin_can_decline_with_reason(self):
        asset_request = self.create_pending_request()
        self.client.force_login(self.admin)

        response = self.client.post(
            reverse("admin:review_asset_request", args=[asset_request.id]),
            {"action": "decline", "decline_reason": "Asset is reserved for a scheduled lab session."},
        )

        self.assertRedirects(response, reverse("admin:index"))
        asset_request.refresh_from_db()
        self.assertEqual(asset_request.status, "rejected")
        self.assertEqual(asset_request.decline_reason, "Asset is reserved for a scheduled lab session.")
        self.assertEqual(asset_request.reviewed_by, self.admin)
        self.assertTrue(
            AuditLog.objects.filter(
                actor=self.admin,
                action=AuditLog.ACTION_UPDATE,
                target_object_id=str(asset_request.id),
                source=reverse("admin:review_asset_request", args=[asset_request.id]),
            ).exists()
        )

    def test_admin_reports_page_shows_inventory_requests_maintenance_and_returned_assets(self):
        technician = User.objects.create_user("techuser", password="pass12345Strong")
        technician.profile.department = self.department
        technician.profile.role = "lab_technician"
        technician.profile.save()

        AssetRequest.objects.create(
            asset=self.visible_asset,
            requested_by=self.user,
            status="rejected",
            reviewed_by=self.admin,
            reviewed_at=timezone.now(),
            decline_reason="Asset is already committed to another class.",
            message="Need this for a lesson.",
            requested_start_at=self.request_start,
            requested_end_at=self.request_end,
            usage_location=self.usage_location,
        )
        Maintenance.objects.create(
            asset=self.visible_asset,
            maintenance_type="corrective",
            scheduled_date=datetime.date(2026, 3, 20),
            completed_date=datetime.date(2026, 3, 21),
            technician=technician,
            reported_by=self.admin,
            description="Battery was failing to hold charge.",
            resolution_notes="Battery replaced and charging cycle tested.",
            status="completed",
        )
        returned_asset = Asset.objects.create(
            name="Returned Projector",
            category=self.category,
            description="Previously assigned projector",
            purchase_date=datetime.date(2026, 3, 10),
            purchase_cost=1600,
            supplier=self.supplier,
            current_location=self.location,
            created_by=self.admin,
        )
        holder = User.objects.create_user("returnedholder", password="pass12345Strong")
        holder.profile.department = self.department
        holder.profile.role = "lecturer"
        holder.profile.user_type = "staff"
        holder.profile.employee_id = "LEC-RETURNED-001"
        holder.profile.staff_location = self.location
        holder.profile.save()
        Allocation.objects.create(
            asset=returned_asset,
            allocated_to=holder,
            allocated_by=self.admin,
            allocation_type="temporary",
            allocation_date=datetime.date(2026, 3, 11),
            expected_return_date=datetime.date(2026, 3, 15),
            actual_return_date=datetime.date(2026, 3, 14),
            purpose="Issued for teaching support.",
            condition_out=returned_asset.condition,
            condition_in="good",
            status="returned",
        )

        self.client.force_login(self.admin)
        response = self.client.get(reverse("admin:reports"))

        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "Whole asset inventory")
        self.assertContains(response, self.visible_asset.asset_id)
        self.assertContains(response, "Asset requests and decisions")
        self.assertContains(response, "Asset is already committed to another class.")
        self.assertContains(response, self.usage_location)
        self.assertContains(response, "Serviced assets, work done, and assigned technician")
        self.assertContains(response, "techuser")
        self.assertContains(response, "Battery replaced and charging cycle tested.")
        self.assertContains(response, "Returned Assets Report")
        self.assertContains(response, returned_asset.asset_id)
        self.assertContains(response, "Assets that have been checked back in")
        self.assertContains(response, "Generated By")
        self.assertContains(response, self.admin.username)
        self.assertContains(response, "Generated On")
        self.assertContains(response, "Print All Reports")
        self.assertContains(response, "FASSETS Official Report Copy")
        self.assertContains(response, "Fixed Assets Management System")
        self.assertContains(response, "Reviewed By")
        self.assertContains(response, "Approved By")

    def test_admin_reports_page_can_filter_by_date_condition_category_and_allocated_status(self):
        allocated_category = Category.objects.create(name="Lab Equipment")
        filtered_asset = Asset.objects.create(
            name="Allocated Oscilloscope",
            category=allocated_category,
            description="Allocated report target.",
            purchase_date=datetime.date(2026, 3, 8),
            purchase_cost=3400,
            supplier=self.supplier,
            current_location=self.location,
            created_by=self.admin,
            condition="excellent",
            status="allocated",
        )
        Asset.objects.create(
            name="Stored Whiteboard",
            category=Category.objects.create(name="Boards"),
            description="Should not match the report query.",
            purchase_date=datetime.date(2026, 2, 5),
            purchase_cost=500,
            supplier=self.supplier,
            current_location=self.location,
            created_by=self.admin,
            condition="poor",
            status="available",
        )

        self.client.force_login(self.admin)
        response = self.client.get(
            reverse("admin:reports"),
            {
                "date_from": "2026-04-01",
                "date_to": "2026-04-30",
                "inventory_status": "allocated",
                "asset_condition": "excellent",
                "asset_category": str(allocated_category.id),
            },
        )

        self.assertEqual(response.status_code, 200)
        self.assertContains(response, 'name="date_from"', html=False)
        self.assertContains(response, 'name="asset_condition"', html=False)
        self.assertContains(response, 'name="asset_category"', html=False)
        self.assertContains(response, "Active Filters")
        self.assertContains(response, "Asset Status: Allocated")
        self.assertContains(response, "Asset Condition: Excellent")
        self.assertEqual([asset.name for asset in response.context["inventory_assets"]], ["Allocated Oscilloscope"])

    def test_admin_reports_page_ignores_request_and_maintenance_status_when_inventory_is_available(self):
        report_date = timezone.localdate().isoformat()
        available_category = Category.objects.create(name="Portable Audio")
        available_asset = Asset.objects.create(
            name="Available Recorder",
            category=available_category,
            description="Available admin report target.",
            purchase_date=datetime.date(2026, 4, 7),
            purchase_cost=1450,
            supplier=self.supplier,
            current_location=self.location,
            created_by=self.admin,
            condition="excellent",
            status="available",
        )
        AssetRequest.objects.create(
            asset=available_asset,
            requested_by=self.user,
            message="Need the recorder for interview practice.",
            requested_start_at=timezone.now() + datetime.timedelta(days=1),
            requested_end_at=timezone.now() + datetime.timedelta(days=2),
            usage_location="Media Room",
            status="pending",
        )
        Maintenance.objects.create(
            asset=available_asset,
            maintenance_type="preventive",
            scheduled_date=datetime.date(2026, 4, 10),
            completed_date=datetime.date(2026, 4, 11),
            reported_by=self.admin,
            description="Microphone port cleaned and tested.",
            status="completed",
        )
        available_asset.refresh_from_db()

        self.client.force_login(self.admin)
        response = self.client.get(
            reverse("admin:reports"),
            {
                "date_from": report_date,
                "date_to": report_date,
                "inventory_status": "available",
                "asset_condition": "excellent",
                "asset_category": str(available_category.id),
                "request_status": "rejected",
                "maintenance_status": "scheduled",
            },
        )

        self.assertEqual(response.status_code, 200)
        self.assertEqual(available_asset.status, "available")
        self.assertEqual(response.context["request_status"], "")
        self.assertEqual(response.context["maintenance_status"], "")
        self.assertIn("Asset Status: Available", response.context["report_active_filters_text"])
        self.assertNotIn("Request Status", response.context["report_active_filters_text"])
        self.assertNotIn("Maintenance Status", response.context["report_active_filters_text"])
        self.assertNotContains(response, "Available assets ignore request and maintenance status filters.")
        self.assertEqual([asset.name for asset in response.context["inventory_assets"]], ["Available Recorder"])
        self.assertEqual([item.asset.name for item in response.context["asset_requests_report"]], ["Available Recorder"])
        self.assertEqual(list(response.context["maintenance_report"]), [])

    def test_admin_dashboard_can_search_user_and_view_assigned_assets(self):
        holder = User.objects.create_user("holderuser", "holder@example.com", "pass12345Strong")
        holder.profile.department = self.department
        holder.profile.role = "lecturer"
        holder.profile.user_type = "staff"
        holder.profile.employee_id = "LEC-101"
        holder.profile.staff_location = self.location
        holder.profile.save()

        second_asset = Asset.objects.create(
            name="Math Projector",
            category=self.category,
            description="Projector assigned to a lecturer.",
            purchase_date=datetime.date(2026, 3, 5),
            purchase_cost=1200,
            supplier=self.supplier,
            current_location=self.location,
            created_by=self.admin,
        )

        Allocation.objects.create(
            asset=self.visible_asset,
            allocated_to=holder,
            allocated_by=self.admin,
            allocation_type="temporary",
            allocation_date=timezone.localdate(),
            expected_return_date=timezone.localdate() + datetime.timedelta(days=5),
            purpose="Issued for lecture preparation.",
            condition_out=self.visible_asset.condition,
            status="active",
        )
        Allocation.objects.create(
            asset=second_asset,
            allocated_to=holder,
            allocated_by=self.admin,
            allocation_type="permanent",
            allocation_date=timezone.localdate(),
            purpose="Issued for classroom teaching.",
            condition_out=second_asset.condition,
            status="active",
        )

        self.client.force_login(self.admin)
        response = self.client.get(reverse("admin:index"), {"user_asset_search": "holderuser"})

        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "User Asset Lookup")
        self.assertContains(response, "holderuser")
        self.assertContains(response, "2 assigned assets")
        self.assertContains(response, self.visible_asset.asset_id)
        self.assertContains(response, second_asset.asset_id)
        self.assertContains(response, "Search User")

    def test_admin_dashboard_user_asset_lookup_is_available_from_account_dashboard(self):
        admin_user = User.objects.create_user("dashboardlookup", password="pass12345Strong")
        admin_user.profile.department = self.department
        admin_user.profile.role = "admin"
        admin_user.profile.user_type = "staff"
        admin_user.profile.employee_id = "ADM-LOOKUP-001"
        admin_user.profile.staff_location = self.location
        admin_user.profile.save()

        holder = User.objects.create_user("lookupholder", password="pass12345Strong")
        holder.profile.department = self.department
        holder.profile.role = "lecturer"
        holder.profile.user_type = "staff"
        holder.profile.employee_id = "LEC-LOOKUP-001"
        holder.profile.staff_location = self.location
        holder.profile.save()

        Allocation.objects.create(
            asset=self.visible_asset,
            allocated_to=holder,
            allocated_by=self.admin,
            allocation_type="temporary",
            allocation_date=timezone.localdate(),
            expected_return_date=timezone.localdate() + datetime.timedelta(days=5),
            purpose="Issued for lecture preparation.",
            condition_out=self.visible_asset.condition,
            status="active",
        )

        self.client.force_login(admin_user)
        response = self.client.get("/dashboard/", {"user_asset_search": "lookupholder"})

        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.context["default_dashboard_section"], "user-asset-lookup")
        self.assertContains(response, "User Asset Lookup")
        self.assertContains(response, "lookupholder")
        self.assertContains(response, self.visible_asset.asset_id)
        self.assertContains(response, "1 assigned asset")
        self.assertContains(response, "Search User")
        self.assertContains(response, "Mark Returned")
        self.assertContains(
            response,
            f'{reverse("assets:workspace_resource", kwargs={"resource": "allocations"})}?recipient=user&user={holder.id}',
            html=False,
        )
        self.assertContains(response, "Allocate Asset")

    def test_admin_can_mark_returned_from_user_asset_lookup(self):
        admin_user = User.objects.create_user("dashboardreturner", password="pass12345Strong")
        admin_user.profile.department = self.department
        admin_user.profile.role = "admin"
        admin_user.profile.user_type = "staff"
        admin_user.profile.employee_id = "ADM-RETURN-001"
        admin_user.profile.staff_location = self.location
        admin_user.profile.save()

        holder = User.objects.create_user("returnholder", password="pass12345Strong")
        holder.profile.department = self.department
        holder.profile.role = "lecturer"
        holder.profile.user_type = "staff"
        holder.profile.employee_id = "LEC-RETURN-001"
        holder.profile.staff_location = self.location
        holder.profile.save()

        allocation = Allocation.objects.create(
            asset=self.visible_asset,
            allocated_to=holder,
            allocated_by=self.admin,
            allocation_type="temporary",
            allocation_date=timezone.localdate(),
            expected_return_date=timezone.localdate() + datetime.timedelta(days=5),
            purpose="Issued for lecture preparation.",
            condition_out=self.visible_asset.condition,
            status="active",
        )

        self.client.force_login(admin_user)
        response = self.client.post(
            reverse("assets:mark_user_asset_returned", args=[allocation.id]),
            {"user_asset_search": "returnholder"},
        )

        self.assertEqual(response.status_code, 302)
        self.assertEqual(
            response["Location"],
            f'{reverse("assets:dashboard")}?user_asset_search=returnholder#user-asset-lookup',
        )

        allocation.refresh_from_db()
        self.visible_asset.refresh_from_db()
        self.assertEqual(allocation.status, "returned")
        self.assertEqual(allocation.actual_return_date, timezone.localdate())
        self.assertEqual(allocation.condition_in, self.visible_asset.condition)
        self.assertEqual(self.visible_asset.status, "available")
        self.assertTrue(
            AuditLog.objects.filter(
                actor=admin_user,
                action=AuditLog.ACTION_UPDATE,
                target_object_id=str(allocation.id),
                source=reverse("assets:mark_user_asset_returned", args=[allocation.id]),
            ).exists()
        )

    def test_marking_returned_updates_reports_summary_and_assigned_assets(self):
        admin_user = User.objects.create_user("reportsreturnadmin", password="pass12345Strong")
        admin_user.profile.department = self.department
        admin_user.profile.role = "admin"
        admin_user.profile.user_type = "staff"
        admin_user.profile.employee_id = "ADM-REPORT-RETURN-001"
        admin_user.profile.staff_location = self.location
        admin_user.profile.save()

        holder = User.objects.create_user("reportsholder", password="pass12345Strong")
        holder.profile.department = self.department
        holder.profile.role = "lecturer"
        holder.profile.user_type = "staff"
        holder.profile.employee_id = "LEC-REPORT-001"
        holder.profile.staff_location = self.location
        holder.profile.save()

        allocation = Allocation.objects.create(
            asset=self.visible_asset,
            allocated_to=holder,
            allocated_by=self.admin,
            allocation_type="temporary",
            allocation_date=timezone.localdate(),
            expected_return_date=timezone.localdate() + datetime.timedelta(days=5),
            purpose="Issued for lecture preparation.",
            condition_out=self.visible_asset.condition,
            status="active",
        )

        self.client.force_login(admin_user)
        self.client.post(
            reverse("assets:mark_user_asset_returned", args=[allocation.id]),
            {"user_asset_search": "reportsholder"},
        )

        response = self.client.get(reverse("assets:reports_center"))

        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.context["report_summary"]["available_assets"], 2)
        self.assertEqual(response.context["report_summary"]["allocated_assets"], 1)
        self.assertEqual(response.context["report_summary"]["active_allocations"], 0)
        self.assertEqual(response.context["report_summary"]["returned_allocations"], 1)
        self.assertEqual(list(response.context["assigned_assets_report"]), [])
        self.assertEqual(len(response.context["returned_assets_report"]), 1)
        self.assertContains(response, "No assigned assets")
        self.assertContains(response, "Returned Assets")
        self.assertContains(response, allocation.asset.asset_id)

    def test_cod_dashboard_user_asset_lookup_is_available_from_account_dashboard(self):
        cod_user = User.objects.create_user("codlookup", password="pass12345Strong")
        cod_user.profile.department = self.department
        cod_user.profile.role = "cod"
        cod_user.profile.user_type = "staff"
        cod_user.profile.employee_id = "COD-LOOKUP-001"
        cod_user.profile.staff_location = self.location
        cod_user.profile.save()

        holder = User.objects.create_user("codholder", password="pass12345Strong")
        holder.profile.department = self.department
        holder.profile.role = "lecturer"
        holder.profile.user_type = "staff"
        holder.profile.employee_id = "LEC-COD-001"
        holder.profile.staff_location = self.location
        holder.profile.save()

        Allocation.objects.create(
            asset=self.visible_asset,
            allocated_to=holder,
            allocated_by=self.admin,
            allocation_type="temporary",
            allocation_date=timezone.localdate(),
            expected_return_date=timezone.localdate() + datetime.timedelta(days=5),
            purpose="Issued for department teaching.",
            condition_out=self.visible_asset.condition,
            status="active",
        )

        self.client.force_login(cod_user)
        response = self.client.get("/dashboard/", {"user_asset_search": "codholder"})

        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.context["default_dashboard_section"], "user-asset-lookup")
        self.assertContains(response, "User Assets")
        self.assertContains(response, "User Asset Lookup")
        self.assertContains(response, "codholder")
        self.assertContains(response, self.visible_asset.asset_id)
        self.assertContains(response, "Allocate Asset")

    def test_cod_dashboard_lab_asset_lookup_finds_lab_inventory_and_lab_assigned_assets(self):
        cod_user = User.objects.create_user("codlablookup", password="pass12345Strong")
        cod_user.profile.department = self.department
        cod_user.profile.role = "cod"
        cod_user.profile.user_type = "staff"
        cod_user.profile.employee_id = "COD-LAB-001"
        cod_user.profile.staff_location = self.lab_location
        cod_user.profile.save()

        lab_inventory_asset = Asset.objects.create(
            name="Lab Microscope",
            category=self.category,
            description="Available for lab use.",
            purchase_date=datetime.date(2026, 3, 10),
            purchase_cost=1400,
            supplier=self.supplier,
            current_location=self.lab_location,
            created_by=self.admin,
            status="available",
        )
        lab_assigned_asset = Asset.objects.create(
            name="Lab Oscilloscope",
            category=self.category,
            description="Assigned to the electronics lab.",
            purchase_date=datetime.date(2026, 3, 11),
            purchase_cost=2200,
            supplier=self.supplier,
            current_location=self.location,
            created_by=self.admin,
            status="available",
        )
        Allocation.objects.create(
            asset=lab_assigned_asset,
            allocated_to_lab=self.lab_location,
            allocated_by=self.admin,
            allocation_type="permanent",
            allocation_date=timezone.localdate(),
            purpose="Dedicated lab use.",
            condition_out=lab_assigned_asset.condition,
            status="active",
        )

        self.client.force_login(cod_user)
        response = self.client.get("/dashboard/", {"lab_asset_search": "PSC"})

        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.context["default_dashboard_section"], "lab-asset-lookup")
        self.assertContains(response, "Lab Asset Lookup")
        self.assertContains(response, "Search Lab Assets")
        self.assertContains(response, "Lab Microscope")
        self.assertContains(response, "Lab Oscilloscope")
        self.assertContains(response, "Held in lab inventory")
        self.assertContains(response, "Assigned to")
        self.assertContains(response, "Lab Assets")
        self.assertEqual(len(response.context["lab_asset_lookup"]["results"]), 1)
        self.assertEqual(response.context["lab_asset_lookup"]["results"][0]["asset_count"], 2)
        self.assertEqual(
            [item["asset"].name for item in response.context["lab_asset_lookup"]["results"][0]["assets"]],
            ["Lab Microscope", "Lab Oscilloscope"],
        )

    def test_lab_technician_dashboard_lab_asset_lookup_is_available_from_account_dashboard(self):
        technician = User.objects.create_user("labtechlookup", password="pass12345Strong")
        technician.profile.department = self.department
        technician.profile.role = "lab_technician"
        technician.profile.user_type = "staff"
        technician.profile.employee_id = "TECH-LAB-001"
        technician.profile.staff_location = self.lab_location
        technician.profile.save()

        lab_asset = Asset.objects.create(
            name="Chemistry Balance",
            category=self.category,
            description="Bench equipment for shared lab use.",
            purchase_date=datetime.date(2026, 3, 12),
            purchase_cost=1800,
            supplier=self.supplier,
            current_location=self.lab_location,
            created_by=self.admin,
            status="available",
        )

        self.client.force_login(technician)
        response = self.client.get("/dashboard/", {"lab_asset_search": "balance"})

        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.context["default_dashboard_section"], "lab-asset-lookup")
        self.assertContains(response, "Lab Asset Lookup")
        self.assertContains(response, "Search Lab Assets")
        self.assertContains(response, "Chemistry Balance")
        self.assertContains(response, lab_asset.asset_id)
        self.assertContains(response, "Held in lab inventory")
        self.assertContains(response, "Lab Assets")
        self.assertTrue(response.context["can_view_lab_asset_lookup"])
        self.assertEqual(
            [item["asset"].name for item in response.context["lab_asset_lookup"]["results"][0]["assets"]],
            ["Chemistry Balance"],
        )

    def test_admin_help_center_links_to_user_asset_lookup(self):
        admin_user = User.objects.create_user("helpadmin", password="pass12345Strong")
        admin_user.profile.department = self.department
        admin_user.profile.role = "admin"
        admin_user.profile.user_type = "staff"
        admin_user.profile.employee_id = "ADM-HELP-001"
        admin_user.profile.save()
        self.client.force_login(admin_user)

        response = self.client.get(reverse("assets:help_center"), {"q": "user assets"})

        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "Search a user and review assigned assets")
        self.assertContains(response, f'{reverse("assets:dashboard")}#user-asset-lookup', html=False)
        self.assertContains(response, "Available to your account")

    def test_admin_resource_manager_includes_search_toolbar(self):
        self.client.force_login(self.admin)

        response = self.client.get(reverse("admin:manage_resource", kwargs={"resource": "assets"}))

        self.assertEqual(response.status_code, 200)
        self.assertContains(response, 'id="resource-search-input"', html=False)
        self.assertContains(response, "Search assets")
        self.assertContains(response, "Clear Search")
        self.assertContains(response, "Record Workspace")
        self.assertContains(response, "Quick help")
        self.assertContains(response, "Required fields are marked with *.")
        self.assertContains(response, "Restore Last Clear")
        self.assertContains(response, "Allocate To User")
        self.assertContains(response, reverse("admin:manage_resource", kwargs={"resource": "allocations"}))

    def test_admin_allocation_manager_only_shows_condition_in_for_return_flow(self):
        self.client.force_login(self.admin)

        response = self.client.get(reverse("admin:manage_resource", kwargs={"resource": "allocations"}))

        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "Allocate To")
        self.assertContains(response, 'field-recipient_mode', html=False)
        self.assertContains(response, "toggleAllocationFieldVisibility")
        self.assertContains(response, "Allocation Type")
        self.assertContains(response, 'field-expected_return_date', html=False)
        self.assertContains(response, 'field-condition_in', html=False)

    def test_admin_asset_manager_shows_ksh_purchase_cost_prefix(self):
        self.client.force_login(self.admin)

        response = self.client.get(reverse("admin:manage_resource", kwargs={"resource": "assets"}))

        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "Purchase Cost")
        self.assertContains(response, "KSH")


class AssetBarcodeTests(TestCase):
    def setUp(self):
        faculty = Faculty.objects.create(name="Faculty of Computing")
        department = Department.objects.create(code="COMP", name="Computer Science", faculty=faculty)
        self.other_department = Department.objects.create(code="MATH", name="Mathematics", faculty=faculty)
        self.category = Category.objects.create(name="Electronics")
        self.supplier = Supplier.objects.create(name="Barcode Supplier")
        self.location = Location.objects.create(
            department=department,
            building="Tech Block",
            floor="1",
            room="103",
            room_type="lab",
        )
        self.other_location = Location.objects.create(
            department=self.other_department,
            building="Math Block",
            floor="2",
            room="201",
            room_type="lab",
        )
        self.admin = User.objects.create_superuser("barcodeadmin", "barcodeadmin@example.com", "pass12345Strong")

    def test_asset_model_auto_generates_barcode_from_asset_id(self):
        asset = Asset.objects.create(
            name="Switch",
            category=self.category,
            description="Managed network switch",
            purchase_date=datetime.date(2026, 4, 1),
            purchase_cost=1500,
            supplier=self.supplier,
            current_location=self.location,
            created_by=self.admin,
        )

        self.assertTrue(asset.asset_id)
        self.assertTrue(asset.asset_id.startswith("COMP-26-"))
        self.assertEqual(asset.barcode, asset.asset_id)

    def test_asset_model_preserves_explicit_barcode(self):
        asset = Asset.objects.create(
            name="Router",
            category=self.category,
            description="Core router",
            purchase_date=datetime.date(2026, 4, 1),
            purchase_cost=2200,
            supplier=self.supplier,
            current_location=self.location,
            created_by=self.admin,
            barcode="CUSTOM-BARCODE-001",
        )

        self.assertEqual(asset.barcode, "CUSTOM-BARCODE-001")
        self.assertTrue(asset.asset_id)

    def test_asset_id_sequence_is_unique_per_department(self):
        comp_asset_one = Asset.objects.create(
            name="Switch A",
            category=self.category,
            description="Department asset",
            purchase_date=datetime.date(2026, 4, 1),
            purchase_cost=1500,
            supplier=self.supplier,
            current_location=self.location,
            created_by=self.admin,
        )
        comp_asset_two = Asset.objects.create(
            name="Switch B",
            category=self.category,
            description="Department asset",
            purchase_date=datetime.date(2026, 4, 2),
            purchase_cost=1600,
            supplier=self.supplier,
            current_location=self.location,
            created_by=self.admin,
        )
        math_asset = Asset.objects.create(
            name="Math Switch",
            category=self.category,
            description="Other department asset",
            purchase_date=datetime.date(2026, 4, 3),
            purchase_cost=1700,
            supplier=self.supplier,
            current_location=self.other_location,
            created_by=self.admin,
        )

        self.assertEqual(comp_asset_one.asset_id, "COMP-26-00001")
        self.assertEqual(comp_asset_two.asset_id, "COMP-26-00002")
        self.assertEqual(math_asset.asset_id, "MATH-26-00001")
