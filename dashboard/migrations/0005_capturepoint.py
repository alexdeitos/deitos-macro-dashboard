from django.db import migrations, models


class Migration(migrations.Migration):
    dependencies = [
        ("dashboard", "0004_tradesetup_tradingaccount_trade_tradeexit_and_more"),
    ]

    operations = [
        migrations.CreateModel(
            name="CapturePoint",
            fields=[
                ("id", models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name="ID")),
                ("observed_at", models.DateTimeField(db_index=True)),
                ("sheet_name", models.CharField(db_index=True, max_length=80)),
                ("symbol", models.CharField(db_index=True, max_length=40)),
                ("value", models.FloatField(blank=True, null=True)),
                ("change_percent", models.FloatField(blank=True, null=True)),
                ("trades", models.FloatField(blank=True, null=True)),
                ("volume", models.FloatField(blank=True, null=True)),
                ("metadata", models.JSONField(blank=True, default=dict)),
                ("created_at", models.DateTimeField(auto_now_add=True)),
            ],
            options={
                "ordering": ["observed_at", "symbol"],
            },
        ),
        migrations.AddIndex(
            model_name="capturepoint",
            index=models.Index(fields=["symbol", "observed_at"], name="dashboard_c_symbol_time_idx"),
        ),
        migrations.AddIndex(
            model_name="capturepoint",
            index=models.Index(fields=["sheet_name", "observed_at"], name="dashboard_c_sheet_time_idx"),
        ),
    ]
