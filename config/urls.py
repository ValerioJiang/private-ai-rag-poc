from django.conf import settings
from django.conf.urls.static import static
from django.contrib import admin
from django.urls import include, path

# L'intestazione dell'admin mostra «Visualizza sito» con un collegamento alla
# radice. Finche' la radice non era instradata quel collegamento portava a un
# 404, e stava percio' a `None` — che lo fa sparire del tutto. Ora la radice
# c'e' e smista per ruolo, ma il collegamento punta direttamente a /chiedi/:
# per chi amministra «vedere il sito» significa vedere cio' che vede l'utente,
# non essere rimandato all'admin da cui e' appena uscito.
admin.site.site_url = "/chiedi/"
admin.site.site_header = "Interrogazione documentale — gestione"
admin.site.site_title = "Gestione"
admin.site.index_title = "Configurazione e documenti"

urlpatterns = [
    path("admin/", admin.site.urls),
    path("", include("rag.urls")),
]

# Solo in sviluppo: in produzione i media li serve il web server.
urlpatterns += static(settings.MEDIA_URL, document_root=settings.MEDIA_ROOT)
