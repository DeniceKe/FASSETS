from django.urls import path
from . import views

urlpatterns = [
    path("assets/", views.AssetListCreateAPIView.as_view(), name="api_assets"),
]