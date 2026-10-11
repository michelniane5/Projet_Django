from datetime import timedelta
import threading
from concurrent.futures import ThreadPoolExecutor
from unittest.mock import patch

from django.contrib.auth import get_user_model
from django.core.exceptions import ValidationError
from django.core import mail
from django.db import close_old_connections, connections
from django.test import Client, TestCase, TransactionTestCase, override_settings, skipUnlessDBFeature
from django.urls import reverse
from django.utils import timezone

from .models import Prestataire, Reservation, Service


@override_settings(EMAIL_BACKEND="django.core.mail.backends.locmem.EmailBackend")
class ReservationTests(TestCase):
    def setUp(self):
        self.prestataire = Prestataire.objects.create(
            nom="Awa",
            metier="Coiffeuse",
            telephone="770000000",
            ville="Dakar",
            quartier="Médina",
            actif=True,
        )
        self.service = Service.objects.create(
            prestataire=self.prestataire,
            nom="Tresses",
            prix_fcfa=5000,
            duree_minutes=60,
        )
        self.autre_service = Service.objects.create(
            prestataire=self.prestataire,
            nom="Brushing",
            prix_fcfa=3000,
            duree_minutes=30,
        )

    def _poster_reservation(self, service, date_heure, client=None, email=None):
        data = {
            "nom_client": "Mamadou",
            "telephone_client": "771234567",
            "date_heure": date_heure.strftime("%Y-%m-%dT%H:%M"),
        }
        if email:
            data["email_client"] = email
        return (client or self.client).post(
            reverse("reservations:reserver", args=[service.id]),
            data,
        )

    def test_accueil_affiche_prestataire_actif(self):
        response = self.client.get(reverse("reservations:accueil"))

        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "Awa")
        self.assertContains(response, "Tresses")
        self.assertContains(response, reverse("reservations:reserver", args=[self.service.pk]))

    def test_formulaire_refuse_un_numero_de_telephone_invalide(self):
        date_future = (timezone.now() + timedelta(days=2)).replace(second=0, microsecond=0)
        response = self.client.post(
            reverse("reservations:reserver", args=[self.service.pk]),
            {
                "nom_client": "Mamadou",
                "telephone_client": "pas-un-numero",
                "date_heure": date_future.strftime("%Y-%m-%dT%H:%M"),
            },
        )

        self.assertEqual(response.status_code, 200)
        self.assertEqual(Reservation.objects.count(), 0)
        self.assertContains(response, "numéro de téléphone valide")

    def test_service_refuse_un_prix_nul_ou_une_duree_excessive(self):
        self.service.prix_fcfa = 0
        with self.assertRaises(ValidationError):
            self.service.full_clean()

        self.service.prix_fcfa = 5000
        self.service.duree_minutes = 1441
        with self.assertRaises(ValidationError):
            self.service.full_clean()

    def test_recherche_accueil_filtre_sur_quartier(self):
        response = self.client.get(reverse("reservations:accueil"), {"q": "Médina"})

        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "Awa")

    def test_client_peut_envoyer_une_demande_future(self):
        date_future = (timezone.now() + timedelta(days=2)).replace(second=0, microsecond=0)

        response = self._poster_reservation(self.service, date_future)

        self.assertEqual(Reservation.objects.count(), 1)
        reservation = Reservation.objects.get()
        self.assertEqual(reservation.statut, "en_attente")
        self.assertEqual(reservation.nom_client, "Mamadou")
        self.assertEqual(response.status_code, 302)
        self.assertEqual(
            response.url,
            reverse(
                "reservations:confirmation",
                kwargs={"token": reservation.confirmation_token},
            ),
        )
        self.prestataire.refresh_from_db()
        self.assertEqual(self.prestataire.reservation_lock_version, 1)

    def test_demande_envoie_un_email_avec_le_lien_de_suivi(self):
        date_future = (timezone.now() + timedelta(days=2)).replace(second=0, microsecond=0)

        response = self._poster_reservation(
            self.service,
            date_future,
            email="client@example.com",
        )

        reservation = Reservation.objects.get()
        self.assertEqual(response.status_code, 302)
        self.assertEqual(len(mail.outbox), 1)
        self.assertEqual(mail.outbox[0].to, ["client@example.com"])
        self.assertIn(str(reservation.confirmation_token), mail.outbox[0].body)
        self.assertIn("en attente", mail.outbox[0].body)

    def test_panne_smtp_ne_supprime_pas_la_reservation(self):
        date_future = (timezone.now() + timedelta(days=2)).replace(second=0, microsecond=0)

        with self.assertLogs("reservations.notifications", level="ERROR"):
            with patch(
                "reservations.notifications.send_mail",
                side_effect=OSError("SMTP indisponible"),
            ):
                response = self._poster_reservation(
                    self.service,
                    date_future,
                    email="client@example.com",
                )

        self.assertEqual(response.status_code, 302)
        self.assertEqual(Reservation.objects.count(), 1)

    def test_une_date_passee_est_refusee(self):
        response = self._poster_reservation(
            self.service,
            timezone.now() - timedelta(days=1),
        )

        self.assertEqual(response.status_code, 200)
        self.assertEqual(Reservation.objects.count(), 0)
        self.assertContains(response, "Choisissez une date et une heure dans le futur")

    def test_confirmation_est_accessible_avec_le_jeton_uuid(self):
        reservation = Reservation.objects.create(
            service=self.service,
            nom_client="Mamadou",
            telephone_client="771234567",
            date_heure=timezone.now() + timedelta(days=2),
        )

        response = self.client.get(
            reverse(
                "reservations:confirmation",
                kwargs={"token": reservation.confirmation_token},
            )
        )

        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "Mamadou")
        self.assertContains(response, "Annuler ma demande")
        self.assertContains(response, "Réserver ce service à nouveau")
        self.assertContains(response, "Contacter sur WhatsApp")
        self.assertContains(response, f"tel:{self.prestataire.telephone}")
        self.assertEqual(
            response["Cache-Control"],
            "max-age=0, no-cache, no-store, must-revalidate, private",
        )
        self.assertEqual(response["Referrer-Policy"], "no-referrer")
        self.assertEqual(response["X-Robots-Tag"], "noindex, nofollow")

    def test_uuid_inconnu_ne_revele_aucune_reservation(self):
        response = self.client.get(
            "/confirmation/00000000-0000-0000-0000-000000000000/"
        )

        self.assertEqual(response.status_code, 404)

    def test_ancien_lien_avec_id_numerique_ne_donne_pas_acces(self):
        reservation = Reservation.objects.create(
            service=self.service,
            nom_client="Mamadou",
            telephone_client="771234567",
            date_heure=timezone.now() + timedelta(days=2),
        )

        response = self.client.get(f"/confirmation/{reservation.id}/")

        self.assertEqual(response.status_code, 404)
        self.assertNotContains(response, "Mamadou", status_code=404)

    def test_demande_chevauchant_un_autre_service_du_prestataire_est_refusee(self):
        debut = (timezone.now() + timedelta(days=3)).replace(second=0, microsecond=0)
        Reservation.objects.create(
            service=self.service,
            nom_client="Fatou",
            telephone_client="778888888",
            date_heure=debut,
            statut="en_attente",
        )

        response = self._poster_reservation(
            self.autre_service,
            debut + timedelta(minutes=30),
        )

        self.assertEqual(response.status_code, 200)
        self.assertEqual(Reservation.objects.count(), 1)
        self.assertContains(response, "chevauche un autre rendez-vous")

    def test_un_creneau_annule_peut_etre_reutilise(self):
        debut = (timezone.now() + timedelta(days=4)).replace(second=0, microsecond=0)
        Reservation.objects.create(
            service=self.service,
            nom_client="Fatou",
            telephone_client="778888888",
            date_heure=debut,
            statut="annulee",
        )

        response = self._poster_reservation(self.autre_service, debut)

        self.assertEqual(response.status_code, 302)
        self.assertEqual(Reservation.objects.count(), 2)

    def test_deux_rendez_vous_contigus_sont_autorises(self):
        debut = (timezone.now() + timedelta(days=5)).replace(second=0, microsecond=0)
        Reservation.objects.create(
            service=self.service,
            nom_client="Fatou",
            telephone_client="778888888",
            date_heure=debut,
            statut="confirmee",
        )

        response = self._poster_reservation(
            self.autre_service,
            debut + timedelta(minutes=self.service.duree_minutes),
        )

        self.assertEqual(response.status_code, 302)
        self.assertEqual(Reservation.objects.count(), 2)

    def test_client_peut_annuler_une_demande_et_est_notifie(self):
        reservation = Reservation.objects.create(
            service=self.service,
            nom_client="Mamadou",
            telephone_client="771234567",
            email_client="client@example.com",
            date_heure=timezone.now() + timedelta(days=2),
        )

        response = self.client.post(
            reverse(
                "reservations:annuler_reservation",
                kwargs={"token": reservation.confirmation_token},
            )
        )

        reservation.refresh_from_db()
        self.assertEqual(response.status_code, 302)
        self.assertEqual(reservation.statut, "annulee")
        self.assertEqual(len(mail.outbox), 1)
        self.assertIn("annulée", mail.outbox[0].body)

    def test_annulation_est_post_uniquement_et_protegee_par_csrf(self):
        reservation = Reservation.objects.create(
            service=self.service,
            nom_client="Mamadou",
            telephone_client="771234567",
            date_heure=timezone.now() + timedelta(days=2),
        )
        url = reverse(
            "reservations:annuler_reservation",
            kwargs={"token": reservation.confirmation_token},
        )

        self.assertEqual(Client().get(url).status_code, 405)
        client_avec_csrf = Client(enforce_csrf_checks=True)
        page = client_avec_csrf.get(
            reverse(
                "reservations:confirmation",
                kwargs={"token": reservation.confirmation_token},
            )
        )
        self.assertEqual(page.status_code, 200)
        self.assertEqual(client_avec_csrf.post(url).status_code, 403)

    def test_reservation_confirmee_ne_peut_pas_etre_annulee_par_le_client(self):
        reservation = Reservation.objects.create(
            service=self.service,
            nom_client="Mamadou",
            telephone_client="771234567",
            date_heure=timezone.now() + timedelta(days=2),
            statut="confirmee",
        )

        self.client.post(
            reverse(
                "reservations:annuler_reservation",
                kwargs={"token": reservation.confirmation_token},
            )
        )

        reservation.refresh_from_db()
        self.assertEqual(reservation.statut, "confirmee")


@override_settings(EMAIL_BACKEND="django.core.mail.backends.locmem.EmailBackend")
class ReservationAdminTests(TestCase):
    def setUp(self):
        prestataire = Prestataire.objects.create(
            nom="Awa",
            metier="Coiffeuse",
            telephone="770000000",
            quartier="Médina",
        )
        service = Service.objects.create(
            prestataire=prestataire,
            nom="Tresses",
            prix_fcfa=5000,
            duree_minutes=60,
        )
        self.en_attente = Reservation.objects.create(
            service=service,
            nom_client="Client attente",
            telephone_client="771111111",
            email_client="client@example.com",
            date_heure=timezone.now() + timedelta(days=2),
        )
        self.autre_statut = Reservation.objects.create(
            service=service,
            nom_client="Client confirmé",
            telephone_client="772222222",
            date_heure=timezone.now() + timedelta(days=3),
            statut="confirmee",
        )
        User = get_user_model()
        admin = User.objects.create_superuser(
            username="admin",
            email="admin@example.com",
            password="test-password-securise",
        )
        self.client.force_login(admin)
        self.url = reverse("admin:reservations_reservation_changelist")

    def _action(self, action, reservation):
        return self.client.post(
            self.url,
            {
                "action": action,
                "_selected_action": [str(reservation.pk)],
            },
            follow=True,
        )

    def test_action_admin_confirme_et_notifie_une_demande(self):
        response = self._action("confirmer_demandes", self.en_attente)

        self.en_attente.refresh_from_db()
        self.autre_statut.refresh_from_db()
        self.assertEqual(response.status_code, 200)
        self.assertEqual(self.en_attente.statut, "confirmee")
        self.assertEqual(self.autre_statut.statut, "confirmee")
        self.assertEqual(len(mail.outbox), 1)
        self.assertIn("confirmé", mail.outbox[0].body)

    def test_action_admin_refuse_et_notifie_une_demande(self):
        response = self._action("refuser_demandes", self.en_attente)

        self.en_attente.refresh_from_db()
        self.assertEqual(response.status_code, 200)
        self.assertEqual(self.en_attente.statut, "refusee")
        self.assertEqual(len(mail.outbox), 1)
        self.assertIn("accepter", mail.outbox[0].body)


@skipUnlessDBFeature("has_select_for_update")
class ReservationConcurrencyTests(TransactionTestCase):
    """Le test de concurrence s’exécute sur PostgreSQL (pas SQLite)."""

    reset_sequences = True

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
        self.date_heure = (timezone.now() + timedelta(days=8)).replace(
            second=0,
            microsecond=0,
        )

    def test_deux_requetes_simultanees_ne_reservent_pas_le_meme_creneau(self):
        barriere = threading.Barrier(2)

        def envoyer_demande(nom):
            close_old_connections()
            try:
                barriere.wait(timeout=10)
                return Client(HTTP_HOST="localhost").post(
                    reverse("reservations:reserver", args=[self.service.pk]),
                    {
                        "nom_client": nom,
                        "telephone_client": "771234567",
                        "date_heure": self.date_heure.strftime("%Y-%m-%dT%H:%M"),
                    },
                ).status_code
            finally:
                connections.close_all()

        with ThreadPoolExecutor(max_workers=2) as executor:
            statuts_http = sorted(
                executor.map(envoyer_demande, ["Client A", "Client B"])
            )

        self.assertEqual(statuts_http, [200, 302])
        self.assertEqual(
            Reservation.objects.filter(
                service__prestataire=self.prestataire,
                date_heure=self.date_heure,
                statut="en_attente",
            ).count(),
            1,
        )
