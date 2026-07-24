"""Eccezioni di dominio dell'ingestione.

Perche' esistono: il servizio deve distinguere un errore ATTESO e imputabile al
documento o alla sua configurazione — un PDF scansionato, un file corrotto, un
duplicato, una strategia non realizzabile — da un guasto del sistema. I primi
finiscono in Document.error_message e portano il documento in stato «Fallito»,
che e' un esito PREVISTO (RF-06, RF-10, CA-8) e non un incidente; i secondi
restano eccezioni inattese, vengono comunque persistite (RNF-04) ma anche
registrate nel log con lo stack completo.

Tutti i messaggi sono scritti per essere letti da un amministratore
nell'admin Django, non da uno sviluppatore in un file di log.
"""


class IngestionError(Exception):
    """Base delle condizioni imputabili al documento o alla configurazione."""


class PdfIllegibile(IngestionError):
    """Il file non e' apribile come PDF: corrotto, vuoto o protetto."""


class PdfSenzaTesto(IngestionError):
    """Nessun testo estraibile: probabile scansione senza OCR (RF-10)."""


class DocumentoDuplicato(IngestionError):
    """Lo stesso file e' gia' presente in questa base di conoscenza (RF-09)."""

    def __init__(self, messaggio: str, *, esistente_id: int | None = None) -> None:
        super().__init__(messaggio)
        self.esistente_id = esistente_id


class ConfigurazioneNonSupportata(IngestionError):
    """La configurazione e' una riga di database valida ma non realizzabile.

    Esempio: ChunkingProfile.Splitter.TOKEN, che richiederebbe tiktoken.
    Non e' un errore dell'utente ne' un guasto: e' un limite dichiarato.
    """
