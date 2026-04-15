from django.urls import path
from . import views

app_name = "assets"

urlpatterns = [
    path("", views.about, name="about"),
    path("help/", views.help_center, name="help_center"),
    path("dashboard/", views.dashboard, name="dashboard"),
    path("reports/", views.reports_center, name="reports_center"),
    path("workspace/<slug:resource>/", views.workspace_resource, name="workspace_resource"),
    path("assets/", views.asset_list, name="asset_list"),
    path("assets/<int:asset_id>/request/", views.request_asset, name="request_asset"),
    path("assets/<int:asset_id>/report-issue/", views.report_asset_issue, name="report_asset_issue"),
    path("allocations/<int:allocation_id>/mark-returned/", views.mark_user_asset_returned, name="mark_user_asset_returned"),
    path("requests/<int:request_id>/cancel/", views.cancel_request, name="cancel_request"),
]
