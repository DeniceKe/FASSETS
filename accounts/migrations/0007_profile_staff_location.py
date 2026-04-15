from django.db import migrations, models
import django.db.models.deletion


class Migration(migrations.Migration):

    dependencies = [
        ("accounts", "0006_alter_profile_role_internal_auditor"),
        ("assets", "0011_supplier_remove_asset_department_and_more"),
    ]

    operations = [
        migrations.AddField(
            model_name="profile",
            name="staff_location",
            field=models.ForeignKey(
                blank=True,
                null=True,
                on_delete=django.db.models.deletion.SET_NULL,
                related_name="staff_profiles",
                to="assets.location",
            ),
        ),
    ]
