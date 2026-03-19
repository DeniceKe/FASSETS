from django.contrib.auth.decorators import login_required
from django.db.models import Count, Q
from django.shortcuts import render

from .models import Asset, Category, Location
from allocations.models import Allocation
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

    if not request.user.is_superuser and department and role not in {"admin", "dean"}:
        assets_qs = assets_qs.filter(current_location__department=department)
        allocations_qs = allocations_qs.filter(asset__current_location__department=department)
        maintenance_qs = maintenance_qs.filter(asset__current_location__department=department)

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
        "department_distribution": department_distribution,
        "user_role": role.replace("_", " ").title() if role else "Unassigned",
        "user_department": department,
    })


@login_required
def asset_list(request):
    qs = Asset.objects.select_related("category", "current_location", "current_location__department")

    # Department isolation (basic): non-superuser sees only own dept assets (if profile has dept)
    if not request.user.is_superuser and getattr(request.user, "profile", None) and request.user.profile.department:
        qs = qs.filter(current_location__department=request.user.profile.department)

    q = request.GET.get("q", "").strip()
    category = request.GET.get("category", "").strip()
    status = request.GET.get("status", "").strip()

    if q:
        qs = qs.filter(Q(asset_id__icontains=q) | Q(name__icontains=q) | Q(description__icontains=q))

    if category:
        qs = qs.filter(category_id=category)

    if status:
        qs = qs.filter(status=status)

    return render(request, "assets/list.html", {
        "assets": qs.order_by("-created_at")[:200],
        "categories": Category.objects.all().order_by("name"),
        "total_results": qs.count(),
        "q": q,
        "category": category,
        "status": status,
    })
