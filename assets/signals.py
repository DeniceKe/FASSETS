from django.db.models.signals import post_save, pre_save
from django.dispatch import receiver
from django.utils import timezone

from .models import Asset
from .services import sync_asset_depreciation


def _department_asset_prefix(instance: Asset, year: int) -> str:
    department_code = getattr(getattr(instance.current_location, "department", None), "code", "") or "AST"
    normalized_code = "".join(
        char for char in str(department_code).upper().strip() if char.isalnum() or char == "-"
    ).strip("-")[:10] or "AST"
    return f"{normalized_code}-{year % 100:02d}-"


@receiver(pre_save, sender=Asset)
def set_asset_id(sender, instance: Asset, **kwargs):
    if instance.asset_id:
        if not instance.barcode:
            instance.barcode = instance.asset_id
        return

    year = (instance.purchase_date.year if instance.purchase_date else timezone.now().year)
    prefix = _department_asset_prefix(instance, year)
    last = (
        Asset.objects
        .filter(asset_id__startswith=prefix)
        .order_by('-asset_id')
        .values_list('asset_id', flat=True)
        .first()
    )

    if last:
        last_num = int(last.split('-')[-1])
        next_num = last_num + 1
    else:
        next_num = 1

    instance.asset_id = f"{prefix}{next_num:05d}"

    if not instance.barcode:
        instance.barcode = instance.asset_id


@receiver(post_save, sender=Asset)
def sync_depreciation_records(sender, instance: Asset, **kwargs):
    sync_asset_depreciation(instance)
