from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ("allocations", "0005_assetrequest_handover_location"),
    ]

    operations = [
        migrations.AddField(
            model_name="assetrequest",
            name="issue_person_details",
            field=models.TextField(blank=True),
        ),
    ]
