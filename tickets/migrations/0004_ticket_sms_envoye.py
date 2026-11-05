from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('tickets', '0003_numero_initiales_place'),
    ]

    operations = [
        migrations.AddField(
            model_name='ticket',
            name='sms_envoye',
            field=models.BooleanField(default=False),
        ),
    ]
