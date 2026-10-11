from uuid import uuid4
import re

from django.core.exceptions import ValidationError
from django.db import models
from django.core.validators import MaxValueValidator, MinValueValidator


def validate_phone(value):
    """Accepte les formats téléphoniques courants sans imposer un pays précis."""
    if not re.fullmatch(r"\+?[0-9().\s-]+", value or ""):
        raise ValidationError("Saisissez un numéro de téléphone valide.")
    digits = re.sub(r"\D", "", value)
    if not 7 <= len(digits) <= 15:
        raise ValidationError("Le numéro doit contenir entre 7 et 15 chiffres.")


class Prestataire(models.Model):
    nom = models.CharField(max_length=100)
    metier = models.CharField(max_length=100)
    telephone = models.CharField(max_length=20, validators=[validate_phone])
    ville = models.CharField(max_length=100, default="Dakar")
    quartier = models.CharField(max_length=100)
    description = models.TextField(blank=True)
    actif = models.BooleanField(default=True)
    # Incrémenté dans une transaction pour sérialiser les nouvelles réservations.
    reservation_lock_version = models.PositiveBigIntegerField(default=0, editable=False)

    @property
    def whatsapp_number(self):
        """Retourne le téléphone au format international attendu par WhatsApp."""
        numero = re.sub(r"\D", "", self.telephone)

        if numero.startswith("221"):
            return numero
        if numero.startswith("0"):
            numero = numero[1:]
        if len(numero) == 9:
            return f"221{numero}"
        return numero

    def __str__(self):
        return f"{self.nom} — {self.metier}"


class Service(models.Model):
    prestataire = models.ForeignKey(
        Prestataire,
        on_delete=models.CASCADE,
        related_name="services",
    )
    nom = models.CharField(max_length=100)
    prix_fcfa = models.PositiveIntegerField(validators=[MinValueValidator(1)])
    duree_minutes = models.PositiveIntegerField(
        default=30,
        validators=[MinValueValidator(1), MaxValueValidator(1440)],
    )

    def __str__(self):
        return f"{self.nom} — {self.prix_fcfa} FCFA"


class Reservation(models.Model):
    STATUTS = [
        ("en_attente", "En attente"),
        ("confirmee", "Confirmée"),
        ("refusee", "Refusée"),
        ("annulee", "Annulée par le client"),
    ]

    service = models.ForeignKey(
        Service,
        on_delete=models.CASCADE,
        related_name="reservations",
    )
    # Jeton porteur secret utilisé pour autoriser la consultation de la confirmation.
    confirmation_token = models.UUIDField(
        default=uuid4,
        unique=True,
        editable=False,
    )
    nom_client = models.CharField(max_length=100)
    telephone_client = models.CharField(max_length=20, validators=[validate_phone])
    email_client = models.EmailField("Adresse e-mail", blank=True)
    date_heure = models.DateTimeField()
    statut = models.CharField(
        max_length=20,
        choices=STATUTS,
        default="en_attente",
    )
    cree_le = models.DateTimeField(auto_now_add=True)

    def __str__(self):
        return f"{self.nom_client} — {self.date_heure:%d/%m/%Y %H:%M}"
