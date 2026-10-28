from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('accounts', '0001_initial'),
    ]

    operations = [
        migrations.AlterField(
            model_name='customuser',
            name='role',
            field=models.CharField(
                choices=[
                    ('admin_general', 'Admin général'),
                    ('admin_commune', 'Admin commune'),
                    ('maire', 'Maire'),
                    ('admin_marche', 'Admin marché'),
                    ('collecteur', 'Collecteur'),
                    ('controleur', 'Contrôleur'),
                    ('regisseur', 'Régisseur'),
                    ('commercant', 'Commerçant'),
                ],
                default='collecteur',
                max_length=20,
            ),
        ),
    ]
