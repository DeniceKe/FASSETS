from decimal import Decimal

from django.utils import timezone

from .models import AssetMovement, DepreciationRecord


def record_asset_movement(*, asset, from_location, to_location, moved_by, notes=""):
    if not from_location or not to_location or from_location.pk == to_location.pk or not moved_by:
        return None

    return AssetMovement.objects.create(
        asset=asset,
        from_location=from_location,
        to_location=to_location,
        moved_by=moved_by,
        notes=notes,
    )


def sync_asset_depreciation(asset):
    if not asset.purchase_date or asset.purchase_cost is None or not asset.category_id:
        return

    start_year = asset.purchase_date.year
    useful_life = max(int(asset.category.depreciation_years or 1), 1)
    current_year = timezone.localdate().year
    end_year = min(current_year, start_year + useful_life - 1)
    purchase_cost = Decimal(asset.purchase_cost)
    yearly_amount = (purchase_cost / Decimal(useful_life)).quantize(Decimal("0.01"))

    kept_years = []
    accumulated = Decimal("0.00")

    for year in range(start_year, end_year + 1):
        kept_years.append(year)
        if year == start_year + useful_life - 1:
            depreciation_amount = purchase_cost - accumulated
        else:
            depreciation_amount = yearly_amount

        accumulated = min(purchase_cost, accumulated + depreciation_amount)
        net_book_value = max(Decimal("0.00"), purchase_cost - accumulated)

        DepreciationRecord.objects.update_or_create(
            asset=asset,
            year=year,
            defaults={
                "depreciation_amount": depreciation_amount,
                "accumulated_depreciation": accumulated,
                "net_book_value": net_book_value,
            },
        )

    if kept_years:
        DepreciationRecord.objects.filter(asset=asset).exclude(year__in=kept_years).delete()
