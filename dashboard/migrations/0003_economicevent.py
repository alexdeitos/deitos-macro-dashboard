from django.db import migrations, models


class Migration(migrations.Migration):
    dependencies = [("dashboard", "0002_marketnews")]

    operations = [
        migrations.CreateModel(
            name="EconomicEvent",
            fields=[
                ("id", models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name="ID")),
                ("external_id", models.CharField(max_length=64, unique=True)),
                ("event_at", models.DateTimeField(db_index=True)),
                ("country", models.CharField(db_index=True, max_length=80)),
                ("country_code", models.CharField(db_index=True, max_length=4)),
                ("category", models.CharField(blank=True, db_index=True, max_length=100)),
                ("event", models.CharField(max_length=320)),
                ("reference", models.CharField(blank=True, max_length=60)),
                ("importance", models.PositiveSmallIntegerField(db_index=True, default=1)),
                ("actual", models.CharField(blank=True, max_length=80)),
                ("previous", models.CharField(blank=True, max_length=80)),
                ("revised", models.CharField(blank=True, max_length=80)),
                ("consensus", models.CharField(blank=True, max_length=80)),
                ("forecast", models.CharField(blank=True, max_length=80)),
                ("url", models.URLField(blank=True, max_length=1000)),
                ("metadata", models.JSONField(blank=True, default=dict)),
                ("collected_at", models.DateTimeField(auto_now_add=True)),
                ("updated_at", models.DateTimeField(auto_now=True)),
            ],
            options={"ordering": ["event_at", "-importance", "country_code"]},
        ),
        migrations.AddIndex(
            model_name="economicevent",
            index=models.Index(fields=["event_at", "country_code"], name="dashboard_e_at_country_idx"),
        ),
        migrations.AddIndex(
            model_name="economicevent",
            index=models.Index(fields=["importance", "event_at"], name="dashboard_e_imp_at_idx"),
        ),
    ]
