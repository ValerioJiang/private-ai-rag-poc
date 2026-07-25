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
]
