import logging

from django.conf import settings
from django.core.mail import send_mail
from django.urls import reverse
from django.utils import timezone

logger = logging.getLogger(__name__)


def envoyer_notification_reservation(reservation, request, sujet, introduction):
    """Envoie une notification simple si le client a donné une adresse e-mail.

    L’échec SMTP est journalisé mais ne doit pas annuler une réservation déjà
    enregistrée ni transformer une action d’administration réussie en erreur 500.
    Le lien inclus est un jeton porteur : le destinataire doit le garder privé.
    """
    if not reservation.email_client:
        return False

    url_suivi = request.build_absolute_uri(
        reverse(
            "reservations:confirmation",
            kwargs={"token": reservation.confirmation_token},
        )
    )
    date_heure = timezone.localtime(reservation.date_heure).strftime("%d/%m/%Y à %H:%M")
    corps = "\n".join(
        [
            f"Bonjour {reservation.nom_client},",
            "",
            introduction,
            f"Service : {reservation.service.nom}",
            f"Prestataire : {reservation.service.prestataire.nom}",
            f"Créneau : {date_heure}",
            f"Statut : {reservation.get_statut_display()}",
            "",
            f"Suivre cette réservation : {url_suivi}",
            "Ce lien est personnel. Ne le transférez pas.",
            "",
            "SunuRéservation",
        ]
    )

    try:
        send_mail(
            subject=sujet,
            message=corps,
            from_email=settings.DEFAULT_FROM_EMAIL,
            recipient_list=[reservation.email_client],
            fail_silently=False,
        )
    except Exception:
        logger.exception(
            "Échec d’envoi de la notification e-mail pour la réservation %s",
            reservation.pk,
        )
        return False
    return True
