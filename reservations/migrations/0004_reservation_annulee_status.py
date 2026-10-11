from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ("reservations", "0003_reservation_confirmation_token"),
    ]

    operations = [
        migrations.AlterField(
            model_name="reservation",
            name="statut",
            field=models.CharField(
                choices=[
                    ("en_attente", "En attente"),
                    ("confirmee", "Confirmée"),
                    ("refusee", "Refusée"),
                    ("annulee", "Annulée par le client"),
                ],
                default="en_attente",
                max_length=20,
            ),
        ),
    ]
