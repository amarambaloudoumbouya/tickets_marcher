from django.core.exceptions import ValidationError
from django.db import IntegrityError, migrations, transaction


def creer_comptes(apps, schema_editor):
    from recensement.comptes import assurer_compte_commercant
    from recensement.models import Commercant

    for commercant in Commercant.objects.filter(user__isnull=True, supprime_le__isnull=True).select_related('marche'):
        try:
            with transaction.atomic():
                user, _mot_de_passe = assurer_compte_commercant(commercant, tolere_conflit=True)
        except (ValidationError, IntegrityError) as exc:
            print(f'Compte non créé pour {commercant.nom} ({commercant.telephone}) : {exc}')
            continue
        if user and user.username != commercant.telephone:
            print(
                f'Compte de {commercant.nom} : identifiant {user.username}, '
                f'mot de passe initial {commercant.telephone} '
                f'(le numéro est déjà utilisé par un autre compte).'
            )


class Migration(migrations.Migration):

    dependencies = [
        ('recensement', '0002_suppression_commercant'),
        ('accounts', '0003_paiement_retrait'),
    ]

    operations = [
        migrations.RunPython(creer_comptes, migrations.RunPython.noop),
    ]
