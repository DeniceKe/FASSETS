from django.db import migrations


def _department_asset_prefix(department_code, year):
    normalized_code = "".join(
        char for char in str(department_code or "AST").upper().strip() if char.isalnum() or char == "-"
    ).strip("-")[:10] or "AST"
    return f"{normalized_code}-{year % 100:02d}-"


def _legacy_asset_year(asset):
    if asset.purchase_date:
        return asset.purchase_date.year

    parts = str(asset.asset_id or "").split("-")
    if len(parts) >= 3 and parts[1].isdigit():
        return int(parts[1])

    return 0


def backfill_department_asset_ids(apps, schema_editor):
    Asset = apps.get_model("assets", "Asset")

    counters = {}
    existing_barcodes = set(
        barcode for barcode in Asset.objects.exclude(barcode__isnull=True).exclude(barcode="").values_list("barcode", flat=True)
    )

    for existing_asset_id in Asset.objects.exclude(asset_id__startswith="AST-").values_list("asset_id", flat=True):
        parts = str(existing_asset_id or "").rsplit("-", 1)
        if len(parts) != 2 or not parts[1].isdigit():
            continue
        prefix = f"{parts[0]}-"
        counters[prefix] = max(counters.get(prefix, 0), int(parts[1]))

    legacy_assets = (
        Asset.objects.select_related("current_location__department")
        .filter(asset_id__startswith="AST-")
        .order_by("purchase_date", "created_at", "id")
    )

    for asset in legacy_assets:
        old_asset_id = asset.asset_id
        department_code = getattr(getattr(asset.current_location, "department", None), "code", "") or "AST"
        prefix = _department_asset_prefix(department_code, _legacy_asset_year(asset))
        next_number = counters.get(prefix, 0) + 1
        counters[prefix] = next_number
        new_asset_id = f"{prefix}{next_number:05d}"

        update_fields = ["asset_id"]
        asset.asset_id = new_asset_id

        if (not asset.barcode or asset.barcode == old_asset_id) and new_asset_id not in existing_barcodes:
            if asset.barcode:
                existing_barcodes.discard(asset.barcode)
            asset.barcode = new_asset_id
            existing_barcodes.add(new_asset_id)
            update_fields.append("barcode")

        asset.save(update_fields=update_fields)


class Migration(migrations.Migration):

    dependencies = [
        ("assets", "0016_alter_category_unique_together_alter_category_name_and_more"),
    ]

    operations = [
        migrations.RunPython(backfill_department_asset_ids, migrations.RunPython.noop),
    ]
