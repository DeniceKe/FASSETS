from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ("assets", "0017_backfill_department_asset_ids"),
    ]

    operations = [
        migrations.AddField(
            model_name="asset",
            name="disposal_reason",
            field=models.TextField(blank=True),
        ),
        migrations.AddField(
            model_name="asset",
            name="disposal_reference",
            field=models.CharField(blank=True, max_length=100),
        ),
    ]
