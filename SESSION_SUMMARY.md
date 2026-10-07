# Session du 24/08/2026 — Résumé complet (pour reprise)

## Contexte
- Projet : Virunga Smart Energy — TFC bac4 Génie Informatique (ULPGL), simulation
  académique inspirée de Virunga Energies (Goma/Rutshuru, RDC).
- Prompt d'ingénierie de référence : `C:\Users\pc\Desktop\vrai memoire\idee chat\application\2_Virunga_Prompt_Ingenierie.docx`
  (stack imposée Django/DRF/Channels, HTTPS POST signé 5 s sans MQTT, JWT
  access+refresh, RBAC serveur, contrat de télémétrie strict, 2 scénarios de
  recharge, règles anti-hallucination, 10 phases avec gates).
- Projet corrigé : `C:\Users\pc\Downloads\virunga-smart-energy`
  (la copie du Bureau `...\idee chat\application\virunga-smart-energy` N'A PAS
  les correctifs — réintégrer si besoin).

## Ce qui a été fait

### 1. Audit vs prompt (première partie de session)
- Constat : fondation conforme (Django/DRF/Channels, HMAC, RBAC, mode DEMO)
  mais phases 7-10 non terminées et 2 bugs critiques :
  - `backend/manage.py` ABSENT (le Dockerfile échouait)
  - `backend/energy/migrations/__init__.py` ABSENT → aucune migration chargée,
    seed ALFAJIRI jamais appliqué (prouvé : "Migrations détectées: []")

### 2. Correctifs backend (tous vérifiés par exécution)
- manage.py + __init__.py créés → migrations OK, seed ALFAJIRI appliqué
- Contrat télémétrie aligné sur le prompt : message_id (UUID), device_timestamp,
  voltage/current/power/energy_consumed, relay_status (bool), signal_strength,
  device_status, firmware_version + validation stricte (bornes, cohérence
  P=V×I×1,15, fenêtre temporelle ±10 min, unicité message_id → 409)
- Signature HMAC vérifiée sur le payload BRUT reçu (bug trouvé à l'essai : le
  compteur signe ce qu'il envoie, pas la version re-sérialisée par DRF)
- JWT access (8 h) + refresh (7 j) avec rotation jti + `/api/auth/token/refresh/`
- Scénario B : token revendeur HMAC (VSE.<payload>.<sig>) lié meter_id +
  séquence, anti-rejeu persistant, réconciliation SAISIE_MANUELLE
  (applied_at/synced_at distincts) — endpoints manual/issue (admin) + apply
- Scénario A : initiation PawaPay sandbox (CDF, providers RDC documentés) et
  Flutterwave (USD) ; 503 explicite sans clé (aucun succès simulé) ; webhook
  Flutterwave signé + idempotent (PaymentEvent) + complétion automatique
  (bug d'arguments inversés corrigé : `pending_recharge_by_reference(tx_ref)`)
- Reçu PDF RÉEL (générateur pur Python, zéro dépendance) au lieu du PDF factice
- Agent IA contextuel sur données réelles (règles + templates, refus explicite
  hors périmètre)
- Anomalies : surtension >253 V, sous-tension <207 V, surconsommation >5 kW,
  solde bas <5 kWh, solde épuisé, budget, perte de communication (heartbeat
  2 min) — dédupliquées 15 min
- Coupure/rétablissement AUTO du relais selon le solde (vérifié en réel)
- Admin `/api/admin/overview/` sans métriques fabriquées (suppression du "or 32")
- Dashboard PERSISTED avec données réelles : consommation horaire (diff
  d'énergie cumulée, clés datées), recharges, alertes, estimation de durée
- SQLite par défaut (prompt) ; PostgreSQL via DATABASE_URL (après phase Business)
- SQLite concurrent : timeout 20 s + 503 explicite au lieu de 500
- Simulateur `manage.py simulate_meter` : POST signé 5 s via le pipeline réel,
  compteur is_demo=True (mode DEMO affiché), historique 24 h pré-rempli pour
  le graphique (profil réaliste), option --no-seed-history ; correctif
  W→kWh (÷1000) sur la consommation temps réel (bug 1000×)

### 3. Essai réel (tout vérifié en direct)
- 30/30 tests Django + 15/15 tests frontend Vitest — exécutés, verts
- Serveur + simulateur lancés : login ALFAJIRI (access+refresh), dashboard
  live (mode DEMO), token manuel (issue 201 → apply 202 +10 kWh → rejeu 409
  → RBAC 403), reçu PDF valide, webhook Flutterwave (PENDING → APPLIED,
  rejeu idempotent, 401 mauvaise signature), paiement sans clé → 503,
  surtension → alerte CRITICAL, solde 0 → relay_command OFF
- Frontend : pnpm install (2 min 28 s) + pnpm build (32 s, 1759 modules) +
  vérifié servi par Django (titre "Virunga Énergie — Compteur intelligent",
  JS/CSS 200) + vitest 15/15
- Bugs trouvés PENDANT la démo et corrigés : HMAC sur payload brut, webhook
  (args inversés), SQLite lock, boucle infinie simulateur sur erreur,
  conversion W→kWh, graphique vide (historique seed + calcul diff cumulé)

### 4. État final
- Base SQLite propre réinitialisée (seed ALFAJIRI) ; docs à jour
  (IMPLEMENTATION_STATUS.md, todo.md) ; frontend buildé dans dist/public
- Tout tourne : Daphne (ASGI, WebSocket) sur 127.0.0.1:8000 + simulateur
  (tant que la session démo est active)

## Comment relancer (rapide)
```
cd C:\Users\pc\Downloads\virunga-smart-energy\backend
export VIRUNGA_IOT_HMAC_SECRET=votre-secret   # obligatoire pour l'ingestion
# venv prêt : %LOCALAPPDATA%\Temp\vse-venv (python 3.11)
python manage.py migrate
python -m daphne -b 127.0.0.1 -p 8000 config.asgi:application   # HTTP+WS
python manage.py simulate_meter --meter VSF-DEMO-ALF-001          # données DEMO
```
Compte démo : Prénom `Ndabereye` / Nom `ALFAJIRI` / code `16985283257989916672`

## Reste à faire (documenté, pas bloquant)
- Clés sandbox réelles PawaPay (`PAWAPAY_SANDBOX_TOKEN`) / Flutterwave
  (`FLUTTERWAVE_SECRET_KEY`, `FLW_SECRET_HASH`) pour un vrai paiement en ligne
- PostgreSQL après la phase Business (le code lit déjà DATABASE_URL ;
  psycopg2-binary à ajouter au requirements)
- WebSocket : InMemoryChannelLayer en dev → channels-redis si multi-workers
- Réintégrer les correctifs dans la copie du Bureau si elle doit rester la
  version de référence
- Le VRAI matériel (ESP32/GSM) reste à tester ; les commandes relais sont
  fournies dans la réponse de télémétrie (relay_command)

## Notes d'environnement
- Windows 10, git-bash (MSYS) : utiliser `C:/...` pour les outils natifs
- Réseau instable (pip/npm timeouts) → privilégier zéro dépendance (stdlib)
- Python : python=3.11.16 (venv dans %LOCALAPPDATA%\Temp\vse-venv),
  python3=3.14 sans pip ; pnpm 10.4.1 installé globalement (corepack cassé)
- Tests : `DJANGO_TESTING=true python manage.py test energy`
