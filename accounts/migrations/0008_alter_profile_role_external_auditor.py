from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ("accounts", "0007_profile_staff_location"),
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
                    ("internal_auditor", "External Auditor"),
                ],
                max_length=30,
            ),
        ),
    ]
