"""Gestione uniforme degli errori dell'API (T-34, RNF-04).

Il problema che chiude: prima di P5 un guasto INATTESO in una vista produceva
una pagina HTML — di debug in sviluppo, la 500 di Django in produzione — a un
client che aveva chiesto JSON e che quel corpo non sa leggerlo. Le condizioni
PREVISTE erano gia' tradotte una per una dalle viste (400, 409, 503) e restano
di loro competenza: questo modulo e' la rete di sicurezza sotto, non la cura.

RISPONDE JSON ANCHE CON DEBUG=True, e togliere la pagina di debug sulle rotte
/api/ e' una scelta, non una svista: un client di un'API deve poter leggere
OGNI risposta, e lo stack completo finisce comunque sulla console attraverso
logger.exception(). Chi sviluppa non perde nulla; chi consuma l'API guadagna
un contratto senza eccezioni.

IL 404 IN ITALIANO. get_object_or_404() solleva Http404 con un messaggio in
inglese che DRF PROPAGA come argomento di NotFound, scavalcando il proprio
«Non trovato.» gia' tradotto (causa verificata in P4 sul sorgente). Il
risultato era «No Document matches the given query.» in un'API per il resto
interamente italiana. Qui si sostituisce il testo; le viste che sanno DI CHE
COSA parlano dicono di meglio, sollevando NotFound con un messaggio proprio.
"""

import logging

from django.http import Http404
from rest_framework import status
from rest_framework.response import Response
from rest_framework.views import exception_handler as gestore_di_drf

logger = logging.getLogger(__name__)


def gestore_eccezioni(exc, context):
    """EXCEPTION_HANDLER di DRF: ogni risposta e' JSON, ogni guasto e' nel log."""
    risposta = gestore_di_drf(exc, context)

    if risposta is None:
        # Non e' un'eccezione di DRF: e' un guasto inatteso. Lo stack serve a
        # chi sviluppa e va nel log per intero; al client si dice che e'
        # successo e dove guardare, senza esporre l'interno del sistema.
        #
        # Si registrano METODO e PERCORSO, non context["view"]: le viste di
        # questo progetto sono funzioni decorate con @api_view, e DRF le
        # avvolge tutte nella stessa classe generata — «WrappedAPIView» per
        # ognuna, che non direbbe quale ha fallito.
        richiesta = context.get("request")
        dove = f"{richiesta.method} {richiesta.path}" if richiesta is not None else "?"
        logger.exception("Guasto inatteso su %s: %s", dove, exc)
        return Response(
            {
                "detail": (
                    "Errore interno del server. Il motivo e' registrato nel "
                    "log dell'applicazione."
                )
            },
            status=status.HTTP_500_INTERNAL_SERVER_ERROR,
        )

    if isinstance(exc, Http404):
        # DRF ha gia' convertito in NotFound, ma con il testo inglese di
        # get_object_or_404 come argomento: cfr. l'intestazione del modulo.
        risposta.data = {"detail": "Risorsa non trovata."}

    return risposta
