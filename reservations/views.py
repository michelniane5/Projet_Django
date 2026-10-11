from datetime import timedelta

from django.contrib import messages
from django.db import transaction
from django.db.models import F, Q
from django.http import Http404
from django.shortcuts import get_object_or_404, redirect, render
from django.utils import timezone
from django.views.decorators.cache import never_cache
from django.views.decorators.http import require_POST

from .forms import ReservationForm
from .models import Prestataire, Reservation, Service
from .notifications import envoyer_notification_reservation


STATUTS_OCCUPANT_UN_CRENEAU = ("en_attente", "confirmee")


def accueil(request):
    recherche = request.GET.get("q", "").strip()

    prestataires = (
        Prestataire.objects
        .filter(actif=True)
        .prefetch_related("services")
        .order_by("nom")
    )

    if recherche:
        prestataires = prestataires.filter(
            Q(nom__icontains=recherche)
            | Q(metier__icontains=recherche)
            | Q(ville__icontains=recherche)
            | Q(quartier__icontains=recherche)
        )

    return render(
        request,
        "reservations/accueil.html",
        {"prestataires": prestataires, "recherche": recherche},
    )


def _chevauchement_pour_prestataire(service, debut, fin):
    """Détecte un chevauchement sur n’importe quel service du prestataire."""
    reservations = (
        Reservation.objects
        .filter(
            service__prestataire=service.prestataire,
            statut__in=STATUTS_OCCUPANT_UN_CRENEAU,
            date_heure__lt=fin,
        )
        .select_related("service")
    )

    for existante in reservations:
        fin_existante = existante.date_heure + timedelta(
            minutes=existante.service.duree_minutes
        )
        if existante.date_heure < fin and debut < fin_existante:
            return True
    return False


def reserver(request, service_id):
    service = get_object_or_404(
        Service.objects.select_related("prestataire"),
        id=service_id,
        prestataire__actif=True,
    )

    if request.method == "POST":
        form = ReservationForm(request.POST)
        if form.is_valid():
            reservation = form.save(commit=False)
            reservation.service = service
            debut = reservation.date_heure
            fin = debut + timedelta(minutes=service.duree_minutes)

            if debut <= timezone.now():
                form.add_error(
                    "date_heure",
                    "Choisissez une date et une heure dans le futur.",
                )
            else:
                # Le UPDATE prend un verrou d’écriture SQLite ; select_for_update
                # protège aussi le chemin PostgreSQL. Le contrôle et le save restent
                # dans la même transaction pour éviter les doubles réservations.
                with transaction.atomic():
                    verrou = Prestataire.objects.filter(
                        pk=service.prestataire_id,
                        actif=True,
                    )
                    if not verrou.update(
                        reservation_lock_version=F("reservation_lock_version") + 1
                    ):
                        raise Http404("Ce prestataire n’est plus disponible.")
                    verrou.select_for_update().get()

                    if _chevauchement_pour_prestataire(service, debut, fin):
                        form.add_error(
                            "date_heure",
                            "Ce créneau chevauche un autre rendez-vous du prestataire. Choisissez une autre heure.",
                        )
                    else:
                        reservation.save()

                if reservation.pk:
                    envoyer_notification_reservation(
                        reservation,
                        request,
                        "Demande de réservation reçue — SunuRéservation",
                        "Votre demande a bien été enregistrée. Le rendez-vous reste en attente de confirmation.",
                    )
                    return redirect(
                        "reservations:confirmation",
                        token=reservation.confirmation_token,
                    )
    else:
        form = ReservationForm()

    return render(
        request,
        "reservations/reserver.html",
        {"form": form, "service": service},
    )


def _confirmation_response(request, token):
    reservation = get_object_or_404(
        Reservation.objects.select_related("service", "service__prestataire"),
        confirmation_token=token,
    )
    response = render(
        request,
        "reservations/confirmation.html",
        {"reservation": reservation},
    )
    response["Referrer-Policy"] = "no-referrer"
    response["X-Robots-Tag"] = "noindex, nofollow"
    return response


@never_cache
def confirmation(request, token):
    """Affiche une réservation uniquement avec son UUID secret non devinable."""
    return _confirmation_response(request, token)


@require_POST
@never_cache
def annuler_reservation(request, token):
    """Annule atomiquement une demande encore en attente via son jeton secret."""
    reservation = get_object_or_404(
        Reservation.objects.select_related("service", "service__prestataire"),
        confirmation_token=token,
    )
    with transaction.atomic():
        annulee = Reservation.objects.filter(
            pk=reservation.pk,
            statut="en_attente",
        ).update(statut="annulee")

    if annulee:
        reservation.refresh_from_db()
        messages.success(request, "Votre demande de réservation a été annulée.")
        envoyer_notification_reservation(
            reservation,
            request,
            "Réservation annulée — SunuRéservation",
            "Votre demande de réservation a été annulée à votre demande.",
        )
    else:
        messages.info(
            request,
            "Cette réservation ne peut plus être annulée depuis ce lien.",
        )
    return redirect("reservations:confirmation", token=token)
