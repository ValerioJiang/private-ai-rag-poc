from django.conf import settings
from django.conf.urls.static import static
from django.contrib import admin
from django.urls import include, path

# L'intestazione dell'admin mostra «Visualizza sito» con un collegamento alla
# radice, che qui non e' instradata: le sole rotte sono `/admin/`, `/health` e
# le quattro sotto `/api/`. Il collegamento portava quindi a un 404, e a
# `None` il collegamento non viene proprio reso. E' cosmetica, ma in una
# dimostrazione un link morto nell'interfaccia si legge come un guasto.
admin.site.site_url = None

urlpatterns = [
    path("admin/", admin.site.urls),
    path("", include("rag.urls")),
]

# Solo in sviluppo: in produzione i media li serve il web server.
urlpatterns += static(settings.MEDIA_URL, document_root=settings.MEDIA_ROOT)
