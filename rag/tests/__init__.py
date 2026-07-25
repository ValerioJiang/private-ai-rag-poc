"""Suite di test (P6, T-36 → T-38, CA-10).

Tre file, uno per attivita': segmentazione e factory (T-36), macchina a stati
dell'ingestione (T-37), API di interrogazione (T-38).

DUE PRESUPPOSTI, entrambi deliberati e dichiarati nel README.

1. SERVE POSTGRESQL. La migrazione 0001 esegue CREATE EXTENSION vector, che
   su SQLite non esiste, e le 19 migrazioni di django_tasks_db sono reali.
   Sostituire il database significherebbe provare un sistema diverso da
   quello che si consegna.
2. NON SERVE OLLAMA. Tutto cio' che parla con la rete passa da
   rag/services/factories.py, che e' la cerniera dell'architettura: i test
   sostituiscono quei quattro nomi NEL MODULO CHE LI CHIAMA e nient'altro.
"""
