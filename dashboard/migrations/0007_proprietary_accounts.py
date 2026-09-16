from django.db import migrations, models
import django.db.models.deletion

class Migration(migrations.Migration):
    dependencies = [("dashboard", "0006_performance_validation")]
    operations = [
        migrations.CreateModel(
            name="ProprietaryAccount",
            fields=[
                ("id", models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name="ID")),
                ("name", models.CharField(max_length=120, unique=True)),
                ("firm", models.CharField(default="MIDE", max_length=120)),
                ("plan_name", models.CharField(blank=True, max_length=120)),
                ("plan_value", models.DecimalField(decimal_places=2, default=0, max_digits=15)),
                ("starting_balance", models.DecimalField(decimal_places=2, default=0, max_digits=15)),
                ("max_loss", models.DecimalField(decimal_places=2, default=0, max_digits=15)),
                ("approval_target", models.DecimalField(decimal_places=2, default=0, max_digits=15)),
                ("max_contracts_day", models.PositiveIntegerField(default=0)),
                ("notes", models.TextField(blank=True)),
                ("is_active", models.BooleanField(db_index=True, default=True)),
                ("created_at", models.DateTimeField(auto_now_add=True)),
                ("updated_at", models.DateTimeField(auto_now=True)),
            ],
            options={"ordering": ["-is_active", "name"]},
        ),
        migrations.CreateModel(
            name="ProprietaryEvaluation",
            fields=[
                ("id", models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name="ID")),
                ("status", models.CharField(choices=[("in_progress", "Em avaliação"), ("approved", "Meta atingida"), ("eliminated", "Eliminada"), ("invalid", "Dados insuficientes")], db_index=True, default="invalid", max_length=20)),
                ("current_result", models.DecimalField(decimal_places=2, default=0, max_digits=15)),
                ("remaining_to_target", models.DecimalField(decimal_places=2, default=0, max_digits=15)),
                ("remaining_loss_buffer", models.DecimalField(decimal_places=2, default=0, max_digits=15)),
                ("max_daily_loss", models.DecimalField(decimal_places=2, default=0, max_digits=15)),
                ("max_trade_loss", models.DecimalField(decimal_places=2, default=0, max_digits=15)),
                ("max_contracts_observed", models.PositiveIntegerField(default=0)),
                ("trade_count", models.PositiveIntegerField(default=0)),
                ("performance_ok", models.BooleanField(default=False)),
                ("contract_limit_ok", models.BooleanField(default=False)),
                ("risk_ok", models.BooleanField(default=False)),
                ("risk_ratio_percent", models.DecimalField(decimal_places=2, default=0, max_digits=10)),
                ("guidance", models.JSONField(blank=True, default=list)),
                ("metrics", models.JSONField(blank=True, default=dict)),
                ("evaluated_at", models.DateTimeField(auto_now_add=True)),
                ("account", models.ForeignKey(on_delete=django.db.models.deletion.CASCADE, related_name="evaluations", to="dashboard.proprietaryaccount")),
                ("report", models.ForeignKey(on_delete=django.db.models.deletion.CASCADE, related_name="proprietary_evaluations", to="dashboard.performancereport")),
            ],
            options={"ordering": ["-evaluated_at", "-id"]},
        ),
        migrations.AddIndex(model_name="proprietaryevaluation", index=models.Index(fields=["account", "-evaluated_at"], name="prop_eval_account_date_idx")),
        migrations.AddIndex(model_name="proprietaryevaluation", index=models.Index(fields=["status", "-evaluated_at"], name="prop_eval_status_date_idx")),
    ]
