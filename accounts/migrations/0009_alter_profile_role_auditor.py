from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ("accounts", "0008_alter_profile_role_external_auditor"),
    ]

    operations = [
        migrations.AlterField(
            model_name="profile",
            name="role",
            field=models.CharField(
                blank=True,
                choices=[
                    ("admin", "Admin"),
                    ("dean", "Dean"),
                    ("cod", "COD"),
                    ("lecturer", "Lecturer"),
                    ("lab_technician", "Lab Technician"),
                    ("internal_auditor", "Auditor"),
                ],
                max_length=30,
            ),
        ),
    ]
