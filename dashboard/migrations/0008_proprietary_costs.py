from django.db import migrations, models


class Migration(migrations.Migration):
    dependencies = [("dashboard", "0007_proprietary_accounts")]

    operations = [
        migrations.AddField(
            model_name="proprietaryaccount",
            name="mini_index_fee",
            field=models.DecimalField(decimal_places=2, default=0.35, max_digits=10, verbose_name="Taxa Mini-Índice por contrato"),
        ),
        migrations.AddField(
            model_name="proprietaryaccount",
            name="mini_dollar_fee",
            field=models.DecimalField(decimal_places=2, default=1.35, max_digits=10, verbose_name="Taxa Mini-Dólar por contrato"),
        ),
        migrations.AddField(
            model_name="proprietaryevaluation",
            name="gross_result",
            field=models.DecimalField(decimal_places=2, default=0, max_digits=15),
        ),
        migrations.AddField(
            model_name="proprietaryevaluation",
            name="operational_costs",
            field=models.DecimalField(decimal_places=2, default=0, max_digits=15),
        ),
    ]
