import os
from datetime import timedelta
from unittest import skipUnless

from django.contrib.auth import get_user_model
from django.core import mail
from django.core.mail import send_mail
from django.test import Client, SimpleTestCase, TestCase, override_settings
from django.urls import reverse
from django.utils import timezone

from .models import Prestataire, Reservation, Service


@override_settings(EMAIL_BACKEND="django.core.mail.backends.locmem.EmailBackend")
class ReservationWorkflowIntegrationTests(TestCase):
    """Parcourt la demande client, la décision admin et l’annulation client."""

    def setUp(self):
        self.prestataire = Prestataire.objects.create(
            nom="Awa",
            metier="Coiffeuse",
            telephone="770000000",
            quartier="Médina",
        )
        self.service = Service.objects.create(
            prestataire=self.prestataire,
            nom="Tresses",
            prix_fcfa=5000,
            duree_minutes=60,
        )

    def _creer_demande(self, nom, date_heure):
        response = self.client.post(
            reverse("reservations:reserver", args=[self.service.pk]),
            {
                "nom_client": nom,
                "telephone_client": "771234567",
                "email_client": "client@example.com",
                "date_heure": date_heure.strftime("%Y-%m-%dT%H:%M"),
            },
        )
        reservation = Reservation.objects.get(nom_client=nom)
        self.assertRedirects(
            response,
            reverse(
                "reservations:confirmation",
                kwargs={"token": reservation.confirmation_token},
            ),
            fetch_redirect_response=False,
        )
        return reservation

    def test_parcours_complet_demande_confirmation_et_annulation(self):
        premiere_date = (timezone.now() + timedelta(days=2)).replace(
            second=0,
            microsecond=0,
        )
        reservation = self._creer_demande("Client 1", premiere_date)
        self.assertEqual(len(mail.outbox), 1)
        self.assertIn(str(reservation.confirmation_token), mail.outbox[0].body)

        page_suivi = self.client.get(
            reverse(
                "reservations:confirmation",
                kwargs={"token": reservation.confirmation_token},
            )
        )
        self.assertContains(page_suivi, "Client 1")
        self.assertContains(page_suivi, "Annuler ma demande")

        admin = get_user_model().objects.create_superuser(
            username="integration-admin",
            email="admin@example.com",
            password="test-password-securise",
        )
        admin_client = Client(HTTP_HOST="testserver")
        admin_client.force_login(admin)
        admin_response = admin_client.post(
            reverse("admin:reservations_reservation_changelist"),
            {
                "action": "confirmer_demandes",
                "_selected_action": [str(reservation.pk)],
            },
            follow=True,
        )
        self.assertEqual(admin_response.status_code, 200)

        reservation.refresh_from_db()
        self.assertEqual(reservation.statut, "confirmee")
        self.assertEqual(len(mail.outbox), 2)
        self.assertIn("confirmé", mail.outbox[1].body)
        page_confirmee = self.client.get(
            reverse(
                "reservations:confirmation",
                kwargs={"token": reservation.confirmation_token},
            )
        )
        self.assertContains(page_confirmee, "Confirmée")
        self.assertNotContains(page_confirmee, "Annuler ma demande")

        # Une demande confirmée ne doit pas être annulable depuis le lien client.
        self.client.post(
            reverse(
                "reservations:annuler_reservation",
                kwargs={"token": reservation.confirmation_token},
            )
        )
        reservation.refresh_from_db()
        self.assertEqual(reservation.statut, "confirmee")
        self.assertEqual(len(mail.outbox), 2)

        seconde_date = (timezone.now() + timedelta(days=5)).replace(
            second=0,
            microsecond=0,
        )
        seconde_reservation = self._creer_demande("Client 2", seconde_date)
        self.assertEqual(len(mail.outbox), 3)
        annulation = self.client.post(
            reverse(
                "reservations:annuler_reservation",
                kwargs={"token": seconde_reservation.confirmation_token},
            )
        )
        self.assertEqual(annulation.status_code, 302)
        seconde_reservation.refresh_from_db()
        self.assertEqual(seconde_reservation.statut, "annulee")
        self.assertEqual(len(mail.outbox), 4)
        self.assertIn("annulée", mail.outbox[3].body)


@override_settings(
    EMAIL_BACKEND="django.core.mail.backends.smtp.EmailBackend",
    EMAIL_HOST=os.getenv("EMAIL_HOST", "127.0.0.1"),
    EMAIL_PORT=int(os.getenv("EMAIL_PORT", "1025")),
    EMAIL_HOST_USER=os.getenv("EMAIL_HOST_USER", ""),
    EMAIL_HOST_PASSWORD=os.getenv("EMAIL_HOST_PASSWORD", ""),
    EMAIL_USE_TLS=os.getenv("EMAIL_USE_TLS", "False").lower() == "true",
    EMAIL_USE_SSL=os.getenv("EMAIL_USE_SSL", "False").lower() == "true",
)
@skipUnless(
    os.getenv("RUN_SMTP_INTEGRATION") == "1",
    "Activer RUN_SMTP_INTEGRATION=1 avec un serveur SMTP de test (Mailpit).",
)
class SMTPTransportIntegrationTests(SimpleTestCase):
    """Vérifie que Django remet réellement un message au serveur SMTP configuré."""

    def test_smtp_accepte_un_message_de_test(self):
        nombre_envoye = send_mail(
            subject="SunuRéservation — test SMTP automatique",
            message="Message de test sans donnée personnelle.",
            from_email=None,
            recipient_list=["ci-test@example.invalid"],
            fail_silently=False,
        )
        self.assertEqual(nombre_envoye, 1)
