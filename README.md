# Application Web - Compteur Intelligent et Prépayé (Cas de Virunga Energies)

Application web développée dans le cadre de mon Travail de Fin de Cycle (TFC) pour la gestion des compteurs intelligents et prépayés inspirée par Virunga Energies.

Simulation académique indépendante : aucun compteur physique n'est requis, un simulateur logiciel emprunte le même pipeline qu'un compteur ESP32 + GSM.

## 🚀 Technologies utilisées
* **Backend :** Django 5.2 / Django REST Framework / Django Channels (Python 3.11 à 3.14)
* **Frontend :** TypeScript / React 19 / Vite / Tailwind
* **Base de données :** SQLite (PostgreSQL possible via `DATABASE_URL`)

## Fonctionnement

```
Compteur (ou simulateur)                 Backend Django                    Navigateur
  télémétrie signée HMAC  ── POST ──▶  /api/iot/telemetry
  toutes les 5 s          ◀── réponse   crédit des recharges (credit_kwh)
                                        ordre de relais (relay_command)
                                        /api/dashboard/  ◀── JWT ──────  tableau de bord abonné
                                        /ws/telemetry/   ── WebSocket ─▶ rafraîchissement temps réel
```

* Le compteur rapporte son solde local. Les recharges appliquées côté serveur lui sont proposées dans chaque réponse de télémétrie (`credits`, avec leur identifiant) jusqu'à ce qu'il les accuse dans une télémétrie suivante (`credit_acks`) : une réponse perdue ne fait perdre aucun crédit, et l'identifiant empêche de l'appliquer deux fois.
* Le relais suit le solde (coupure à 0 kWh) puis la dernière commande de l'abonné : un isolement demandé reste en vigueur jusqu'à ce que l'abonné demande le rétablissement.
* Un paiement en ligne n'est crédité qu'après confirmation serveur à serveur du prestataire (statut, référence, montant et devise).
* Alertes dégressives : quand le crédit descend à 15 %, puis 10 %, 5 %, 3 % et 1 % du dernier plein (solde le plus haut depuis la dernière recharge), une alerte `CREDIT_SEUIL_<n>` est créée — une seule par seuil et par cycle de recharge — et envoyée à l'abonné par e-mail, SMS et WhatsApp sur les canaux configurés.

## Démarrage

### Backend

```bash
cd backend
python -m venv .venv
.venv\Scripts\pip install -r requirements.txt      # Linux/macOS : .venv/bin/pip
copy .env.example .env                              # puis renseigner les secrets
.venv\Scripts\python manage.py migrate
.venv\Scripts\python manage.py runserver            # API + WebSocket sur http://127.0.0.1:8000
```

Dans un second terminal, le compteur de démonstration :

```bash
.venv\Scripts\python manage.py simulate_meter --meter VSF-DEMO-ALF-001
```

Compte de démonstration (créé par les migrations) : prénom `Ndabereye`, nom `ALFAJIRI`, code compteur `16985283257989916672`.

Compte administrateur (supervision et émission de tokens revendeur, page `/admin`) :

```bash
.venv\Scripts\python manage.py createsuperuser
```

### Frontend

```bash
pnpm install
pnpm build        # produit dist/public, servi ensuite par Django sur /
```

### Variables d'environnement (`backend/.env`)

| Variable | Rôle |
| --- | --- |
| `DJANGO_SECRET_KEY` | Signe les JWT. **Obligatoire en production** : sans elle une clé aléatoire est tirée à chaque démarrage (sessions perdues). |
| `VIRUNGA_IOT_HMAC_SECRET` | Secret partagé compteur ↔ backend. Sans lui, toute télémétrie est rejetée (401). |
| `DJANGO_DEBUG`, `DJANGO_ALLOWED_HOSTS` | `true` en développement ; liste d'hôtes séparés par des virgules. |
| `PAWAPAY_SANDBOX_TOKEN` | Mobile money. Sans token : initiation refusée (503), aucun crédit possible. |
| `FLUTTERWAVE_SECRET_KEY`, `FLW_SECRET_HASH` | Carte bancaire : initiation + vérification, et signature du webhook. |
| `EMAIL_HOST_USER`, `EMAIL_HOST_PASSWORD` | Alertes par e-mail (Gmail SMTP, mot de passe d'application). |
| `TWILIO_ACCOUNT_SID`, `TWILIO_AUTH_TOKEN`, `TWILIO_SMS_FROM` | Alertes par SMS (Twilio). |
| `TWILIO_WHATSAPP_FROM` ou `WHATSAPP_CLOUD_TOKEN` + `WHATSAPP_PHONE_NUMBER_ID` | Alertes WhatsApp (Twilio, ou Meta Cloud API prioritaire). |
| `DEEPSEEK_API_KEY` | Assistant IA. Sans clé : moteur de règles sur les données réelles du compteur. |
| `DATABASE_URL` | `postgres://…` pour PostgreSQL (ajouter `psycopg2-binary`). |

## Tests

```bash
cd backend
set DJANGO_TESTING=true && .venv\Scripts\python manage.py test energy     # 58 tests
cd ..
pnpm check && pnpm test                                                    # typage + Vitest
```

## Limites connues

* Paiements : intégrations écrites d'après la documentation PawaPay et Flutterwave, jamais exercées avec de vraies clés sandbox.
* Notifications : les envois Gmail, Twilio et Meta sont écrits d'après leur documentation et testés avec des réponses simulées ; aucun message réel n'a été envoyé faute d'identifiants. Le bouton « Envoyer un message d'essai » du tableau de bord rapporte le résultat réel de chaque canal.
* Le journal des envois est écrit dans les logs du serveur, pas en base (structure de la base inchangée).
* Un firmware de compteur réel doit mémoriser les identifiants de crédit déjà appliqués et les accuser (`credit_acks`), comme le fait le simulateur ; aucun compteur physique n'a été testé.
* La session administrateur dure 8 h, sans renouvellement automatique.
* Temps réel : `InMemoryChannelLayer`, donc un seul processus serveur (sinon `channels-redis`).

L'état détaillé des fonctionnalités est décrit dans `IMPLEMENTATION_STATUS.md`.
