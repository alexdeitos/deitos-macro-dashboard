from decimal import Decimal
from django.db import migrations


def normalize_legacy_fees(apps, schema_editor):
    Account = apps.get_model("dashboard", "ProprietaryAccount")
    # Older versions of proprietary.js converted 0.35 -> 35 and 1.35 -> 135.
    Account.objects.filter(mini_index_fee=Decimal("35.00")).update(mini_index_fee=Decimal("0.35"))
    Account.objects.filter(mini_dollar_fee=Decimal("135.00")).update(mini_dollar_fee=Decimal("1.35"))


def noop(apps, schema_editor):
    pass


class Migration(migrations.Migration):
    dependencies = [("dashboard", "0010_proprietary_current_evaluation")]
    operations = [migrations.RunPython(normalize_legacy_fees, noop)]
