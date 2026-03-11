from rest_framework import generics
from rest_framework.permissions import IsAuthenticated

from assets.models import Asset
from .serializers import AssetSerializer

class AssetListCreateAPIView(generics.ListCreateAPIView):
    serializer_class = AssetSerializer
    permission_classes = [IsAuthenticated]

    def get_queryset(self):
        qs = Asset.objects.select_related("category", "supplier", "current_location", "current_location__department")
        user = self.request.user

        if user.is_superuser:
            return qs

        if getattr(user, "profile", None) and user.profile.department:
            return qs.filter(current_location__department=user.profile.department)

        return qs.none()

    def perform_create(self, serializer):
        serializer.save(created_by=self.request.user)