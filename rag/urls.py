from django.contrib.auth.views import LogoutView
from django.urls import path

from . import views

urlpatterns = [
    path("health", views.health, name="health"),
    # Le API stanno sotto /api/; health NO, perche' e' citata dal
    # docker-compose e dal README e spostarla romperebbe entrambi.
    path("api/documents/", views.documenti, name="api-documents"),
    path("api/documents/<int:pk>/", views.documento, name="api-document"),
    path("api/ask/", views.ask, name="api-ask"),
    path("api/pipelines/", views.pipelines, name="api-pipelines"),
    # Le rotte che servono HTML. La radice smista per ruolo e non rende nulla;
    # /accedi/ e' la porta d'ingresso per TUTTI, non solo per chi amministra.
    path("", views.radice, name="radice"),
    path("accedi/", views.Accesso.as_view(), name="accedi"),
    # LogoutView vuole POST da Django 5: nei template e' un form, non un <a>.
    path("esci/", LogoutView.as_view(), name="esci"),
    path("chiedi/", views.chiedi, name="chiedi"),
]
