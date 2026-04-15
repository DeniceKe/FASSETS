from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ("allocations", "0003_assetrequest_decline_reason_and_review_fields"),
    ]

    operations = [
        migrations.AddField(
            model_name="assetrequest",
            name="requested_end_at",
            field=models.DateTimeField(blank=True, null=True),
        ),
        migrations.AddField(
            model_name="assetrequest",
            name="requested_start_at",
            field=models.DateTimeField(blank=True, null=True),
        ),
        migrations.AddField(
            model_name="assetrequest",
            name="usage_location",
            field=models.CharField(blank=True, max_length=200),
        ),
    ]
