from django.contrib.auth.decorators import login_required
from django.contrib.admin.views.decorators import staff_member_required
from django.contrib import messages
from django.db.models import Count
from django.shortcuts import get_object_or_404, redirect, render
from django.views.decorators.http import require_POST

from .models import Asset
from allocations.models import Allocation, AssetRequest
from maintenance.models import Maintenance
from accounts.roles import infer_user_role


def about(request):
    return render(request, "about.html")


@login_required
def dashboard(request):
    assets_qs = Asset.objects.select_related(
        "category",
        "current_location",
        "current_location__department",
        "supplier",
    )
    allocations_qs = Allocation.objects.select_related("asset", "allocated_to", "allocated_to_lab")
    maintenance_qs = Maintenance.objects.select_related("asset", "technician", "reported_by")

    profile = getattr(request.user, "profile", None)
    department = getattr(profile, "department", None)
    role = infer_user_role(request.user)

    if not request.user.is_superuser and role not in {"admin", "dean"}:
        if department:
            assets_qs = assets_qs.filter(current_location__department=department)
            allocations_qs = allocations_qs.filter(asset__current_location__department=department)
            maintenance_qs = maintenance_qs.filter(asset__current_location__department=department)
        else:
            assets_qs = assets_qs.none()
            allocations_qs = allocations_qs.none()
            maintenance_qs = maintenance_qs.none()

    total_assets = assets_qs.count()
    available = assets_qs.filter(status="available").count()
    allocated = assets_qs.filter(status="allocated").count()
    maintenance = assets_qs.filter(status="maintenance").count()
    disposed = assets_qs.filter(status="disposed").count()
    active_allocations = allocations_qs.filter(status__in=["active", "overdue"]).count()
    open_maintenance = maintenance_qs.filter(status__in=["scheduled", "in_progress"]).count()

    department_distribution = (
        assets_qs.values("current_location__department__name", "current_location__department__code")
        .annotate(total=Count("id"))
        .order_by("-total", "current_location__department__name")[:6]
    )

    department_assets = assets_qs.order_by("name")[:100]
    request_status_by_asset = {
        request.asset_id: request.status
        for request in AssetRequest.objects.filter(
            requested_by=request.user,
            asset__in=department_assets,
            status="pending",
        )
    }
    recent_requests = AssetRequest.objects.select_related("asset", "reviewed_by").filter(
        requested_by=request.user,
    )[:6]

    return render(request, "dashboard.html", {
        "total_assets": total_assets,
        "available": available,
        "allocated": allocated,
        "maintenance": maintenance,
        "disposed": disposed,
        "active_allocations": active_allocations,
        "open_maintenance": open_maintenance,
        "recent_assets": assets_qs.order_by("-created_at")[:5],
        "recent_allocations": allocations_qs.order_by("-allocation_date")[:5],
        "recent_maintenance": maintenance_qs.order_by("-scheduled_date")[:5],
        "department_assets": department_assets,
        "request_status_by_asset": request_status_by_asset,
        "recent_requests": recent_requests,
        "department_distribution": department_distribution,
        "user_role": role.replace("_", " ").title() if role else "Unassigned",
        "user_department": department,
    })


@staff_member_required
def asset_list(request):
    query_string = request.META.get("QUERY_STRING", "")
    target = "/admin/inventory/"
    if query_string:
        target = f"{target}?{query_string}"
    return redirect(target)


@login_required
@require_POST
def request_asset(request, asset_id):
    asset = get_object_or_404(
        Asset.objects.select_related("current_location", "current_location__department"),
        pk=asset_id,
    )

    profile = getattr(request.user, "profile", None)
    department = getattr(profile, "department", None)

    if not request.user.is_superuser and department and asset.current_location.department_id != department.id:
        messages.error(request, "You can only request assets from your department.")
        return redirect("assets:dashboard")

    if asset.status != "available":
        messages.error(request, "This asset is not currently available for requests.")
        return redirect("assets:dashboard")

    existing_request = AssetRequest.objects.filter(asset=asset, requested_by=request.user, status="pending").first()
    if existing_request:
        messages.info(request, "You already have a pending request for this asset.")
        return redirect("assets:dashboard")

    AssetRequest.objects.create(
        asset=asset,
        requested_by=request.user,
        message=f"Request submitted by {request.user.get_full_name() or request.user.username}.",
    )
    messages.success(request, f"Your request for {asset.name} has been submitted.")
    return redirect("assets:dashboard")
