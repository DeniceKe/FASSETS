from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ("allocations", "0004_assetrequest_requested_schedule_and_location"),
    ]

    operations = [
        migrations.AddField(
            model_name="assetrequest",
            name="handover_location",
            field=models.CharField(blank=True, max_length=255),
        ),
    ]
