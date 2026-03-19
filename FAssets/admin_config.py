from django.contrib.admin.apps import AdminConfig


class FAssetsAdminConfig(AdminConfig):
    default_site = "FAssets.admin_site.FAssetsAdminSite"
