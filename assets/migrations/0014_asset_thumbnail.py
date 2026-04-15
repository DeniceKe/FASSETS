from django.db import migrations, models
import assets.models


class Migration(migrations.Migration):

    dependencies = [
        ("assets", "0013_alter_asset_barcode"),
    ]

    operations = [
        migrations.AddField(
            model_name="asset",
            name="thumbnail",
            field=models.ImageField(blank=True, null=True, upload_to=assets.models.asset_thumbnail_upload_path),
        ),
    ]
