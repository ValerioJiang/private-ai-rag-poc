"""Estrazione del testo dai PDF (T-14, RF-03, RF-10).

Promosso da scripts/spike_rag.py::load_pdf(), che ARCHITECTURE §7.10 indica
come l'unico codice dello spike da non buttare via.

Si importa `pymupdf` e non `fitz`: dalla 1.24 il nome canonico del modulo e'
`pymupdf` e `fitz` resta come alias di compatibilita'. Verificato sulla 1.28.0
installata.
"""

from __future__ import annotations

from dataclasses import dataclass

import pymupdf
from langchain_core.documents import Document as LCDocument

from .exceptions import PdfIllegibile, PdfSenzaTesto


@dataclass(frozen=True)
class PdfEstratto:
    """Esito dell'estrazione.

    page_count e' il totale delle pagine del FILE, non delle pagine con testo:
    un PDF di 50 pagine di cui 3 contengono testo va indicizzato, ma l'admin
    deve mostrare 50 (criterio CA-2).
    """

    pagine: list[LCDocument]
    page_count: int


def load_pdf(path: str, *, metadata_extra: dict | None = None) -> PdfEstratto:
    """Estrae il testo pagina per pagina conservando il numero di pagina.

    Il numero di pagina e' 1-based perche' finisce nelle citazioni mostrate
    all'utente (RF-13): «pagina 0» non si scrive in una risposta.

    Solleva:
        PdfIllegibile: file inesistente, corrotto, vuoto o protetto.
        PdfSenzaTesto: nessuna pagina contiene testo estraibile (RF-10).
    """
    try:
        documento = pymupdf.open(path)
    except pymupdf.FileNotFoundError as exc:
        # ATTENZIONE: pymupdf.FileNotFoundError OMBREGGIA l'omonima builtin e
        # NON la sottoclassa — deriva da RuntimeError. Verificato sulla 1.28.0:
        # scrivere `except FileNotFoundError` qui NON la catturerebbe, e
        # l'eccezione sfuggirebbe al servizio come guasto inatteso. L'ordine
        # delle clausole conta: va prima di FileDataError.
        raise PdfIllegibile(f"File non trovato: {path}") from exc
    except pymupdf.FileDataError as exc:
        # EmptyFileError e' sottoclasse di FileDataError (verificato), quindi
        # una sola clausola copre file corrotto e file di zero byte. Entrambe
        # derivano da RuntimeError e non da OSError: catturarle per nome e'
        # l'unico modo di distinguerle da un guasto vero.
        raise PdfIllegibile(
            f"Il file non e' un PDF leggibile ({type(exc).__name__}). "
            "Verificare che non sia corrotto o troncato."
        ) from exc

    with documento:
        if documento.needs_pass:
            raise PdfIllegibile(
                "Il PDF e' protetto da password: non e' possibile estrarne il testo."
            )

        page_count = documento.page_count
        pagine: list[LCDocument] = []
        for numero, pagina in enumerate(documento, start=1):
            testo = pagina.get_text().strip()
            if not testo:
                continue
            metadata = {"page": numero, "source": path}
            if metadata_extra:
                metadata.update(metadata_extra)
            pagine.append(LCDocument(page_content=testo, metadata=metadata))

    if not pagine:
        raise PdfSenzaTesto(
            f"Nessun testo estraibile dalle {page_count} pagine del documento. "
            "E' probabilmente una scansione senza OCR: l'OCR e' dichiarato fuori "
            "ambito (REQUIREMENTS §8), quindi questo file non e' indicizzabile."
        )
    return PdfEstratto(pagine=pagine, page_count=page_count)
