from django.db import migrations, models

import accounts.models


class Migration(migrations.Migration):

    dependencies = [
        ("accounts", "0003_profile_phone_number_profile_registration_number_and_more"),
    ]

    operations = [
        migrations.AddField(
            model_name="profile",
            name="photo",
            field=models.ImageField(blank=True, null=True, upload_to=accounts.models.profile_photo_upload_path),
        ),
    ]
