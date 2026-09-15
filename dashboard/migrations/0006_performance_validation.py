from django.db import migrations, models
import django.db.models.deletion


class Migration(migrations.Migration):
    dependencies = [
        ("dashboard", "0005_capturepoint"),
    ]

    operations = [
        migrations.CreateModel(
            name="PerformanceReport",
            fields=[
                ("id", models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name="ID")),
                ("filename", models.CharField(max_length=255)),
                ("account_label", models.CharField(blank=True, max_length=120)),
                ("holder_label", models.CharField(blank=True, max_length=240)),
                ("period_start", models.DateField(blank=True, null=True)),
                ("period_end", models.DateField(blank=True, null=True)),
                ("imported_at", models.DateTimeField(auto_now_add=True)),
                ("total_rows", models.PositiveIntegerField(default=0)),
                ("total_result", models.DecimalField(decimal_places=2, default=0, max_digits=15)),
                ("metadata", models.JSONField(blank=True, default=dict)),
            ],
            options={"ordering": ["-imported_at", "-id"]},
        ),
        migrations.CreateModel(
            name="PerformanceTrade",
            fields=[
                ("id", models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name="ID")),
                ("row_number", models.PositiveIntegerField()),
                ("symbol", models.CharField(db_index=True, max_length=40)),
                ("opened_at", models.DateTimeField(db_index=True)),
                ("closed_at", models.DateTimeField(blank=True, null=True)),
                ("duration_label", models.CharField(blank=True, max_length=40)),
                ("buy_qty", models.IntegerField(default=0)),
                ("sell_qty", models.IntegerField(default=0)),
                ("side", models.CharField(blank=True, max_length=2)),
                ("buy_price", models.DecimalField(blank=True, decimal_places=4, max_digits=16, null=True)),
                ("sell_price", models.DecimalField(blank=True, decimal_places=4, max_digits=16, null=True)),
                ("market_price", models.DecimalField(blank=True, decimal_places=4, max_digits=16, null=True)),
                ("gross_interval", models.DecimalField(blank=True, decimal_places=2, max_digits=15, null=True)),
                ("gross_interval_pct", models.DecimalField(blank=True, decimal_places=4, max_digits=12, null=True)),
                ("result", models.DecimalField(decimal_places=2, default=0, max_digits=15)),
                ("result_pct", models.DecimalField(blank=True, decimal_places=4, max_digits=12, null=True)),
                ("tet", models.CharField(blank=True, max_length=40)),
                ("cumulative_total", models.DecimalField(blank=True, decimal_places=2, max_digits=15, null=True)),
                ("justification", models.TextField(blank=True)),
                ("validation_score", models.PositiveSmallIntegerField(default=0)),
                ("setup_note", models.CharField(blank=True, max_length=120)),
                ("created_at", models.DateTimeField(auto_now_add=True)),
                ("updated_at", models.DateTimeField(auto_now=True)),
                ("diary_trade", models.OneToOneField(blank=True, null=True, on_delete=django.db.models.deletion.SET_NULL, related_name="performance_import", to="dashboard.trade")),
                ("metadata", models.JSONField(blank=True, default=dict)),
                ("report", models.ForeignKey(on_delete=django.db.models.deletion.CASCADE, related_name="trades", to="dashboard.performancereport")),
            ],
            options={"ordering": ["-opened_at", "-id"]},
        ),
        migrations.AddIndex(
            model_name="performancetrade",
            index=models.Index(fields=["report", "opened_at"], name="perftrade_report_open_idx"),
        ),
        migrations.AddIndex(
            model_name="performancetrade",
            index=models.Index(fields=["symbol", "opened_at"], name="perftrade_symbol_open_idx"),
        ),
    ]
