from django.contrib.auth.decorators import login_required
from django.db.models import Q
from django.shortcuts import render

from .models import Asset, Category, Location

@login_required
def dashboard(request):
    # simple starter dashboard
    total_assets = Asset.objects.count()
    available = Asset.objects.filter(status="available").count()
    allocated = Asset.objects.filter(status="allocated").count()
    maintenance = Asset.objects.filter(status="maintenance").count()

    return render(request, "dashboard.html", {
        "total_assets": total_assets,
        "available": available,
        "allocated": allocated,
        "maintenance": maintenance,
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
        "q": q,
        "category": category,
        "status": status,
    })