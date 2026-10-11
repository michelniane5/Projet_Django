from django.contrib import admin, messages
from django.db import transaction

from .models import Prestataire, Reservation, Service
from .notifications import envoyer_notification_reservation


class ServiceInline(admin.TabularInline):
    model = Service
    extra = 1


@admin.register(Prestataire)
class PrestataireAdmin(admin.ModelAdmin):
    list_display = ("nom", "metier", "ville", "quartier", "telephone", "actif")
    list_filter = ("ville", "metier", "actif")
    search_fields = ("nom", "metier", "quartier")
    inlines = [ServiceInline]


def _traiter_demandes(modeladmin, request, queryset, nouveau_statut, introduction):
    with transaction.atomic():
        demandes = list(
            queryset.filter(statut="en_attente")
            .select_for_update()
            .select_related("service", "service__prestataire")
        )
        ids = [demande.pk for demande in demandes]
        nombre = Reservation.objects.filter(
            pk__in=ids,
            statut="en_attente",
        ).update(statut=nouveau_statut)
        reservations_modifiees = list(
            Reservation.objects.filter(pk__in=ids)
            .select_related("service", "service__prestataire")
        )

    mails_envoyes = 0
    for reservation in reservations_modifiees:
        mails_envoyes += envoyer_notification_reservation(
            reservation,
            request,
            f"Mise à jour de votre réservation — SunuRéservation",
            introduction,
        )

    modeladmin.message_user(
        request,
        f"{nombre} demande(s) mise(s) à jour ; {mails_envoyes} notification(s) e-mail envoyée(s).",
        messages.SUCCESS,
    )


def confirmer_demandes(modeladmin, request, queryset):
    _traiter_demandes(
        modeladmin,
        request,
        queryset,
        "confirmee",
        "Le prestataire a confirmé votre demande.",
    )


confirmer_demandes.short_description = "Confirmer les demandes sélectionnées"


def refuser_demandes(modeladmin, request, queryset):
    _traiter_demandes(
        modeladmin,
        request,
        queryset,
        "refusee",
        "Le prestataire n’a pas pu accepter votre demande.",
    )


refuser_demandes.short_description = "Refuser les demandes sélectionnées"


@admin.register(Reservation)
class ReservationAdmin(admin.ModelAdmin):
    list_display = (
        "nom_client",
        "service",
        "date_heure",
        "statut",
        "telephone_client",
        "cree_le",
    )
    list_filter = ("statut", "date_heure", "service__prestataire")
    search_fields = (
        "nom_client",
        "telephone_client",
        "email_client",
        "service__nom",
        "service__prestataire__nom",
    )
    date_hierarchy = "date_heure"
    ordering = ("date_heure",)
    readonly_fields = ("confirmation_token", "cree_le")
    actions = (confirmer_demandes, refuser_demandes)
