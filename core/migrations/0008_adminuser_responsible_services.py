from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ("core", "0007_adminuser_theme_fields"),
    ]

    operations = [
        migrations.AddField(
            model_name="adminuser",
            name="responsible_services",
            field=models.ManyToManyField(
                blank=True, related_name="responsible_admins", to="core.servicedefinition"
            ),
        ),
    ]

