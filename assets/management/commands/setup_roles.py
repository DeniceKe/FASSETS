from django.core.management.base import BaseCommand
from django.contrib.auth.models import Group, Permission
from django.contrib.contenttypes.models import ContentType

from assets.models import Department, AssetCategory, Asset, AssetAssignment, MaintenanceRecord


class Command(BaseCommand):
    help = "Create default roles (groups) and assign permissions for the Asset Management System."

    def handle(self, *args, **options):
        # Content types
        ct_department = ContentType.objects.get_for_model(Department)
        ct_category = ContentType.objects.get_for_model(AssetCategory)
        ct_asset = ContentType.objects.get_for_model(Asset)
        ct_assignment = ContentType.objects.get_for_model(AssetAssignment)
        ct_maint = ContentType.objects.get_for_model(MaintenanceRecord)

        def perms(model_ct, actions):
            """
            actions: list like ["add", "change", "delete", "view"]
            """
            codenames = [f"{a}_{model_ct.model}" for a in actions]
            return Permission.objects.filter(content_type=model_ct, codename__in=codenames)

        # --- Create groups ---
        dean, _ = Group.objects.get_or_create(name="Dean of Faculty")
        fac_admin, _ = Group.objects.get_or_create(name="Faculty Administrator")
        chair, _ = Group.objects.get_or_create(name="Chair of Department")
        lecturer, _ = Group.objects.get_or_create(name="Lecturer")

        # Clear old perms (safe reset)
        for g in [dean, fac_admin, chair, lecturer]:
            g.permissions.clear()

        # --- Permission policy (editable) ---
        # Dean: view everything (and optionally change)
        dean.permissions.add(
            *perms(ct_department, ["view"]),
            *perms(ct_category, ["view"]),
            *perms(ct_asset, ["view"]),
            *perms(ct_assignment, ["view"]),
            *perms(ct_maint, ["view"]),
        )

        # Faculty Administrator: full management of all tables
        fac_admin.permissions.add(
            *perms(ct_department, ["add", "change", "delete", "view"]),
            *perms(ct_category, ["add", "change", "delete", "view"]),
            *perms(ct_asset, ["add", "change", "delete", "view"]),
            *perms(ct_assignment, ["add", "change", "delete", "view"]),
            *perms(ct_maint, ["add", "change", "delete", "view"]),
        )

        # Chair: view everything, can manage assets & assignments for department operations
        chair.permissions.add(
            *perms(ct_department, ["view"]),
            *perms(ct_category, ["view"]),
            *perms(ct_asset, ["add", "change", "view"]),
            *perms(ct_assignment, ["add", "change", "view"]),
            *perms(ct_maint, ["add", "change", "view"]),
        )

        # Lecturer: view assets, create maintenance requests, view own assignments (we’ll enforce “own” later in API)
        lecturer.permissions.add(
            *perms(ct_department, ["view"]),
            *perms(ct_category, ["view"]),
            *perms(ct_asset, ["view"]),
            *perms(ct_assignment, ["view"]),
            *perms(ct_maint, ["add", "view"]),
        )

        self.stdout.write(self.style.SUCCESS("Roles created and permissions assigned."))
