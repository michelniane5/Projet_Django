from django import forms
from .models import Reservation


class ReservationForm(forms.ModelForm):
    class Meta:
        model = Reservation
        fields = ["nom_client", "telephone_client", "email_client", "date_heure"]
        labels = {
            "nom_client": "Votre nom",
            "telephone_client": "Votre numéro de téléphone",
            "email_client": "Votre adresse e-mail (facultatif)",
            "date_heure": "Date et heure souhaitées",
        }
        widgets = {
            "date_heure": forms.DateTimeInput(
                attrs={"type": "datetime-local"},
                format="%Y-%m-%dT%H:%M",
            ),
        }

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.fields["date_heure"].input_formats = ["%Y-%m-%dT%H:%M"]
