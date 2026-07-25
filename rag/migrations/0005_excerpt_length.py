"""L'ultima costante di comportamento diventa configurazione (RF-22).

Prima migrazione dell'app `rag` dopo P1, e la ragione per cui esiste sta fuori
dal modello: fino a P5 la lunghezza della citazione mostrata accanto a ogni
fonte era `LUNGHEZZA_ESTRATTO = 300`, scritta in `rag/services/query.py`. Era
l'unica violazione sopravvissuta del requisito centrale della traccia — nessun
parametro di comportamento nel codice — ed era dichiarata per iscritto nel
report di P5 fra le voci aperte. P6 la sposta su
`RetrievalProfile.excerpt_length`, dove l'amministratore la modifica come
`top_k` o `score_threshold`.

Additiva e con `default=300`: le righe esistenti — compresi i profili creati
dalla 0004 — prendono il valore con cui P3, P4 e P5 hanno misurato, quindi
nessun estratto gia' mostrato cambia e nessuna misura riportata nei report
diventa incomparabile. Non c'e' nulla da fare sui dati, e la migrazione e'
reversibile senza perdite: `RemoveField` toglie una colonna il cui unico
consumatore e' la citazione.

Generata con `makemigrations`, non scritta a mano (T-40).
"""

import django.core.validators
from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('rag', '0004_configurazione_predefinita'),
    ]

    operations = [
        migrations.AddField(
            model_name='retrievalprofile',
            name='excerpt_length',
            field=models.PositiveIntegerField(default=300, help_text="Caratteri della citazione mostrata accanto a ogni fonte. NON cambia il contesto passato all'LLM, che riceve sempre il segmento intero: e' una scelta di leggibilita' della risposta. Sta qui e non nel codice perche' RF-22 non ammette valori di comportamento fuori dal database.", validators=[django.core.validators.MinValueValidator(50)], verbose_name="lunghezza dell'estratto"),
        ),
    ]
