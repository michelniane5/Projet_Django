from django.urls import path

from . import views

app_name = "reservations"

urlpatterns = [
    path("", views.accueil, name="accueil"),
    path("reserver/<int:service_id>/", views.reserver, name="reserver"),
    path(
        "confirmation/<uuid:token>/annuler/",
        views.annuler_reservation,
        name="annuler_reservation",
    ),
    path("confirmation/<uuid:token>/", views.confirmation, name="confirmation"),
]
