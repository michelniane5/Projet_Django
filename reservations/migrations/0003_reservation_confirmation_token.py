import uuid

from django.db import migrations, models


def populate_confirmation_tokens(apps, schema_editor):
    Reservation = apps.get_model("reservations", "Reservation")
    for reservation in Reservation.objects.filter(confirmation_token__isnull=True).iterator():
        reservation.confirmation_token = uuid.uuid4()
        reservation.save(update_fields=["confirmation_token"])


class Migration(migrations.Migration):
    dependencies = [
        ("reservations", "0002_reservation_email_client"),
    ]

    operations = [
        migrations.AddField(
            model_name="reservation",
            name="confirmation_token",
            field=models.UUIDField(null=True, editable=False),
        ),
        migrations.RunPython(
            populate_confirmation_tokens,
            reverse_code=migrations.RunPython.noop,
        ),
        migrations.AlterField(
            model_name="reservation",
            name="confirmation_token",
            field=models.UUIDField(default=uuid.uuid4, editable=False, unique=True),
        ),
    ]
