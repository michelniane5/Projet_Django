from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ("reservations", "0004_reservation_annulee_status"),
    ]

    operations = [
        migrations.AddField(
            model_name="prestataire",
            name="reservation_lock_version",
            field=models.PositiveBigIntegerField(default=0, editable=False),
        ),
    ]
