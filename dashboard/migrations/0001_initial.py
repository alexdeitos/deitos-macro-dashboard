# Generated for the project template.
from django.db import migrations, models
import django.db.models.deletion


class Migration(migrations.Migration):
    initial = True
    dependencies = []

    operations = [
        migrations.CreateModel(
            name="CollectionRun",
            fields=[
                ("id", models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name="ID")),
                ("task_id", models.CharField(blank=True, db_index=True, max_length=64)),
                ("status", models.CharField(choices=[("running", "Executando"), ("success", "Sucesso"), ("partial", "Parcial"), ("failed", "Falhou")], default="running", max_length=16)),
                ("started_at", models.DateTimeField(auto_now_add=True)),
                ("finished_at", models.DateTimeField(blank=True, null=True)),
                ("source_status", models.JSONField(blank=True, default=dict)),
                ("error", models.TextField(blank=True)),
            ],
            options={"ordering": ["-started_at"]},
        ),
        migrations.CreateModel(
            name="MarketPoint",
            fields=[
                ("id", models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name="ID")),
                ("observed_at", models.DateTimeField(db_index=True)),
                ("symbol", models.CharField(db_index=True, max_length=40)),
                ("name", models.CharField(max_length=120)),
                ("category", models.CharField(db_index=True, max_length=40)),
                ("value", models.DecimalField(blank=True, decimal_places=8, max_digits=24, null=True)),
                ("change_percent", models.DecimalField(blank=True, decimal_places=6, max_digits=12, null=True)),
                ("source", models.CharField(db_index=True, max_length=50)),
                ("metadata", models.JSONField(blank=True, default=dict)),
                ("created_at", models.DateTimeField(auto_now_add=True)),
            ],
            options={"ordering": ["observed_at"]},
        ),
        migrations.CreateModel(
            name="MarketSnapshot",
            fields=[
                ("id", models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name="ID")),
                ("collected_at", models.DateTimeField(db_index=True)),
                ("payload", models.JSONField(default=dict)),
                ("source_status", models.JSONField(default=dict)),
                ("is_complete", models.BooleanField(default=False)),
                ("duration_ms", models.PositiveIntegerField(default=0)),
                ("created_at", models.DateTimeField(auto_now_add=True)),
                ("run", models.OneToOneField(blank=True, null=True, on_delete=django.db.models.deletion.SET_NULL, related_name="snapshot", to="dashboard.collectionrun")),
            ],
            options={"ordering": ["-collected_at"]},
        ),
        migrations.AddConstraint(
            model_name="marketpoint",
            constraint=models.UniqueConstraint(fields=("observed_at", "symbol", "source"), name="unique_market_point"),
        ),
        migrations.AddIndex(
            model_name="marketpoint",
            index=models.Index(fields=["symbol", "observed_at"], name="dashboard_m_symbol_eb67e1_idx"),
        ),
        migrations.AddIndex(
            model_name="marketpoint",
            index=models.Index(fields=["category", "observed_at"], name="dashboard_m_categor_7c896a_idx"),
        ),
        migrations.AddIndex(
            model_name="marketsnapshot",
            index=models.Index(fields=["-collected_at"], name="dashboard_m_collect_9e7df0_idx"),
        ),
    ]
