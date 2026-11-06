from django.db import migrations


def creer_comptes(apps, schema_editor):
    from recensement.comptes import assurer_compte_commercant
    from recensement.models import Commercant

    for commercant in Commercant.objects.filter(user__isnull=True, supprime_le__isnull=True).select_related('marche'):
        assurer_compte_commercant(commercant)


class Migration(migrations.Migration):

    dependencies = [
        ('recensement', '0002_suppression_commercant'),
        ('accounts', '0003_paiement_retrait'),
    ]

    operations = [
        migrations.RunPython(creer_comptes, migrations.RunPython.noop),
    ]
