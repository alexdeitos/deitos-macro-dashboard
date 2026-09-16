from django.db import migrations, models


class Migration(migrations.Migration):
    dependencies = [("dashboard", "0008_proprietary_costs")]

    operations = [
        migrations.AddField(
            model_name="proprietaryaccount",
            name="start_date",
            field=models.DateField(blank=True, null=True, verbose_name="Data de início do plano"),
        ),
    ]
