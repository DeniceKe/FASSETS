from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ("allocations", "0006_assetrequest_issue_person_details"),
    ]

    operations = [
        migrations.AddField(
            model_name="allocation",
            name="allocation_type",
            field=models.CharField(
                choices=[("temporary", "Temporary"), ("permanent", "Permanent")],
                default="temporary",
                max_length=20,
            ),
        ),
        migrations.AlterField(
            model_name="allocation",
            name="expected_return_date",
            field=models.DateField(blank=True, null=True),
        ),
    ]
