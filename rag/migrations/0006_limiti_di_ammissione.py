"""I limiti di ammissione dei PDF diventano configurazione (T-44, RF-22).

Tre campi additivi su KnowledgeBase, tutti con il default che DISATTIVA il
controllo: 0 per le due soglie intere, 0.0 per il rapporto. Le righe
esistenti — compresa la base di conoscenza creata dalla 0004 — mantengono
quindi esattamente il comportamento con cui P2 → P6 hanno misurato, e nessuna
cifra riportata nei report diventa incomparabile.

E' la stessa scelta della 0005, per la stessa ragione: una migrazione
additiva con default neutro non chiede nulla a chi aggiorna, e il
comportamento nuovo si attiva scegliendolo dall'admin.

Reversibile senza perdite: RemoveField toglie tre colonne i cui unici
consumatori sono i controlli di rag/services/validation.py.

Generata con makemigrations, non scritta a mano (T-40).
"""

import django.core.validators
from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('rag', '0005_excerpt_length'),
    ]

    operations = [
        migrations.AddField(
            model_name='knowledgebase',
            name='max_file_size_mb',
            field=models.PositiveIntegerField(default=0, help_text="Oltre questa dimensione il caricamento e' respinto subito, con 400 e senza creare ne' la riga ne' il file. Zero disattiva il controllo. La coda e' seriale: un file molto grande non fallisce, occupa il worker e ritarda tutti gli altri documenti.", verbose_name='dimensione massima (MB)'),
        ),
        migrations.AddField(
            model_name='knowledgebase',
            name='max_page_count',
            field=models.PositiveIntegerField(default=0, help_text="Oltre questo numero di pagine il caricamento e' respinto subito. Zero disattiva il controllo E il PDF non viene nemmeno aperto: con un limite attivo un file corrotto e' scoperto dalla POST invece che dal worker, ed e' un cambio di contratto dichiarato nel README. L'indicizzazione costa circa un secondo per segmento.", verbose_name='pagine massime'),
        ),
        migrations.AddField(
            model_name='knowledgebase',
            name='min_text_page_ratio',
            field=models.FloatField(default=0.0, help_text="Fra 0 e 1. Sotto questa quota di pagine con testo estraibile il documento e' marcato «Fallito» dal worker, con il conteggio nel motivo. Serve contro le scansioni PARZIALI: se NESSUNA pagina ha testo interviene gia' il controllo di RF-10. Zero disattiva. L'OCR resta fuori ambito (REQUIREMENTS §8).", validators=[django.core.validators.MinValueValidator(0.0), django.core.validators.MaxValueValidator(1.0)], verbose_name='rapporto minimo di pagine con testo'),
        ),
    ]
