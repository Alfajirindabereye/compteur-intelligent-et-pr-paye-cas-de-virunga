# Virunga Smart Energy — État d'implémentation

## Résumé

Plateforme web de monitoring et de gestion de la consommation électrique pour
abonnés prépayés (simulation académique inspirée de Virunga Energies). Backend
Django / DRF / Django Channels, frontend React / TypeScript / Vite / Tailwind,
communication compteur → backend par HTTPS POST signé (HMAC-SHA256) toutes les
5 secondes, sans broker MQTT. Base SQLite en développement, PostgreSQL prévu
après la phase Business (via `DATABASE_URL`).

Ce document décrit l'état RÉEL, vérifié par exécution (tests et essai de bout
en bout le 24/08/2026). Toute donnée simulée est identifiable : le simulateur
marque les compteurs `is_demo=True` et l'interface affiche le mode DEMO.

## Fonctionnalités présentes et vérifiées

- Ingestion télémétrie conforme au contrat du prompt : `message_id` (UUID),
  `meter_id`, `device_timestamp`, `voltage`, `current`, `power`,
  `energy_consumed`, `balance_kwh`, `relay_status` (booléen), `signal_strength`,
  `device_status`, `firmware_version`. Validation stricte : types, bornes
  physiques (300 V / 100 A / 30 kW), cohérence puissance-tension-courant,
  cohérence temporelle (±10 min), unicité persistée du `message_id` (409).
- Signature HMAC-SHA256 vérifiée sur le payload brut reçu (`X-Virunga-Signature`).
- Simulateur logiciel (`manage.py simulate_meter`) : envoie une télémétrie
  signée via le pipeline réel toutes les 5 s, crée/active un compteur
  `is_demo=True`, pré-remplit un historique de démonstration de 24 h
  (points horaires, profil de charge réaliste) pour le graphique, décrémente
  le solde, coupe le relais à solde nul. Vérifié : HTTP 202 accepté à chaque
  envoi. Correctif appliqué : conversion W→kWh (÷1000) dans la consommation
  temps réel (le bug gonflait la consommation de 1000×).
- Temps réel : WebSocket Django Channels `/ws/telemetry/` (annonce
  `mqtt:false`), rafraîchissement périodique 5 s du dashboard.
- Authentification JWT : paire access (8 h) + refresh (7 j, rotation avec
  `jti`), endpoint `/api/auth/token/refresh/`, RBAC vérifié côté serveur
  (`is_staff` pour l'admin, `domain_role` dans le JWT).
- Scénario B de recharge (revendeur / saisie manuelle) : émission de token
  signé HMAC-SHA256 lié au `meter_id` + numéro de séquence
  (`/api/recharges/manual/issue/`, admin), application avec anti-rejeu
  persistant (`/api/recharges/manual/apply/`), réconciliation
  `source=SAISIE_MANUELLE` avec `applied_at` et `synced_at` distincts.
  Vérifié : issue 201, apply 202 (+10 kWh), rejeu 409, RBAC 403.
- Scénario A de recharge (en ligne) : initiation PawaPay sandbox (CDF,
  providers RDC documentés) et checkout Flutterwave (USD), recharge PENDING
  traçable par référence ; webhook Flutterwave signé (`flutterwave-signature`),
  idempotent (`PaymentEvent`, clé `flutterwave:<eventId>`), complétion
  automatique de la recharge au statut `successful`. Vérifié de bout en bout
  avec un hash local : APPLIED +10 kWh, rejeu sans double crédit, 401 sur
  signature invalide. Sans clés sandbox fournies, l'initiation renvoie 503
  explicite — aucun succès n'est simulé.
- Reçu PDF réel après chaque recharge (`/api/receipts/<id>/`), généré sans
  dépendance externe, réservé au propriétaire de la recharge ou à l'admin.
  Vérifié : PDF 1.4 valide (entête, objets, xref, `%%EOF`).
- Coupure / rétablissement automatique du relais selon le solde : à chaque
  télémétrie, `balance_kwh <= 0` → relais OFF (commande renvoyée au compteur),
  solde positif → relais ON. Vérifié en réel (solde 0 → `relay_command` OFF,
  relais OFF dans le dashboard).
- Détection d'anomalies : surtension (>253 V), sous-tension (<207 V),
  surconsommation (>5 kW), solde bas (<5 kWh), solde épuisé, dépassement
  d'approche de budget, perte de communication (heartbeat > 2 min). Alerte
  dédupliquée par type ouvert (15 min). Vérifié : surtension 265 V → alerte
  CRITICAL visible dans le dashboard.
- Dashboard abonné (mode DEMO explicite pour les compteurs simulés, sinon
  PERSISTED) : tension/courant/puissance/énergie, solde kWh/CDF/USD,
  estimation de durée restante, consommation horaire 24 h annotée des
  recharges, recharges récentes avec source, alertes ouvertes, commande relais.
- Administration lecture seule : `/api/admin/overview/` avec uniquement des
  métriques réelles (compteurs, en ligne, solde bas, par secteur, alertes
  ouvertes) — aucune valeur fabriquée (le `or 32` d'origine a été supprimé).
- Agent IA contextuel : répond uniquement à partir des données réelles du
  compteur associé (solde, durée, consommation, recharges, alertes, relais) ;
  refuse explicitement toute question hors de son périmètre de données.
- Actualités locales : modèle, endpoints, publication contrôlée par l'admin,
  lecture publique des articles publiés uniquement.
- Commandes relais : mise en PENDING, acquittement à la télémétrie suivante
  correspondante, supersession des commandes obsolètes.

## Tests

`DJANGO_TESTING=true python manage.py test energy` : 30 tests, tous verts.
Couverture : contrat de télémétrie (acceptation/rejets), signature HMAC,
unicité message_id, relais auto (coupure + rétablissement), scénario B complet
avec anti-rejeu et token falsifié, webhook Flutterwave (signature,
idempotence, complétion), initiation sans clé (503), reçu PDF réel + contrôle
d'appartenance, agent IA, RBAC admin/abonné, actualités, WebSocket,
statistiques admin sans fabrication.

## Limites non masquées (documentées, conformément au prompt)

- Paiements en ligne : les intégrations PawaPay et Flutterwave sont
  implémentées selon leur documentation officielle (endpoints sandbox,
  signatures, providers RDC), mais AUCUNE clé sandbox / compte marchand n'a
  été fourni. L'initiation renvoie 503 explicite ; le webhook est testable
  avec `FLW_SECRET_HASH`. Aucun paiement n'est simulé comme réussi.
- Agent IA : moteur de règles contextuel sur données réelles (pas de LLM
  externe). Il ne répond jamais avec une donnée hors de la base.
- Temps réel : canal en mémoire (`InMemoryChannelLayer`) ; pour plusieurs
  workers, utiliser `channels-redis` (déjà dans requirements).
- Base de données : SQLite en développement (comme imposé) ; bascule
  PostgreSQL prévue après la phase Business — le code lit déjà `DATABASE_URL`.
- Frontend : le code React appelle exclusivement l'API Django (fichier
  `client/src/lib/djangoEnergy.ts`) ; le build de production (`dist/public`)
  a été produit (`pnpm build`, 1759 modules) et vérifié servi par Django :
  `/` renvoie le `index.html` (titre « Virunga Énergie — Compteur
  intelligent »), les assets JS/CSS répondent en 200, les tests frontend
  Vitest passent (15/15).
- Matériel : aucun compteur physique (ESP32/GSM) n'a été testé ; le
  simulateur reproduit le pipeline réel. Les commandes relais sont fournies
  au compteur dans la réponse de télémétrie (`relay_command`).

## Démarrage

```
cd backend
python -m venv .venv && .venv/Scripts/pip install -r requirements.txt
export VIRUNGA_IOT_HMAC_SECRET=votre-secret   # obligatoire (signature IoT)
python manage.py migrate
python manage.py runserver                    # API + WebSocket (daphne en prod)
python manage.py simulate_meter --meter VSF-DEMO-ALF-001   # données DEMO
```

Compte de démonstration (seed de migration) : prénom `Ndabereye`, nom
`ALFAJIRI`, code compteur `16985283257989916672` → compteur
`VSF-DEMO-ALF-001` (is_demo).
