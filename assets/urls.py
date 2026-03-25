from django.urls import path
from . import views

app_name = "assets"

urlpatterns = [
    path("", views.about, name="about"),
    path("dashboard/", views.dashboard, name="dashboard"),
    path("assets/", views.asset_list, name="asset_list"),
    path("assets/<int:asset_id>/request/", views.request_asset, name="request_asset"),
]
