from django.db import migrations, models

def mark_latest_as_current(apps, schema_editor):
    ProprietaryEvaluation = apps.get_model("dashboard", "ProprietaryEvaluation")
    Account = apps.get_model("dashboard", "ProprietaryAccount")
    for account in Account.objects.all().iterator():
        qs = ProprietaryEvaluation.objects.filter(account_id=account.id).order_by("-evaluated_at", "-id")
        latest = qs.first()
        if latest:
            qs.update(is_current=False)
            latest.is_current = True
            latest.save(update_fields=["is_current"])

class Migration(migrations.Migration):
    dependencies = [("dashboard", "0009_proprietary_start_date")]
    operations = [
        migrations.AddField(model_name="proprietaryevaluation", name="is_current", field=models.BooleanField(db_index=True, default=True)),
        migrations.AddIndex(model_name="proprietaryevaluation", index=models.Index(fields=["account", "-is_current", "-evaluated_at"], name="prop_eval_current_idx")),
        migrations.RunPython(mark_latest_as_current, migrations.RunPython.noop),
    ]
