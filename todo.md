# Project TODO

- [x] Mettre en place l’authentification et le contrôle d’accès avec validation RBAC côté serveur pour les rôles abonné et administrateur
- [x] Ajouter les modèles de compteurs, secteurs, télémétries, recharges, tokens, alertes, messages et paramètres de budget
- [x] Implémenter l’ingestion de télémétrie IoT via HTTPS POST signé avec validation stricte et unicité du message_id
- [x] Ajouter le simulateur logiciel de télémétrie utilisant le pipeline backend réel
- [x] Ajouter la supervision temps réel des métriques tension, courant, puissance, énergie, solde, relais et signal GSM
- [x] Afficher le solde simultanément en kWh, CDF et USD
- [x] Ajouter l’estimation de durée restante avant épuisement du crédit
- [x] Construire le dashboard abonné responsive avec statut du compteur et indicateurs critiques
- [x] Construire l’historique de consommation avec graphiques et annotations de recharge
- [x] Afficher les sources de recharge avec les libellés exacts APP_PAIEMENT et SAISIE_MANUELLE
- [x] Préserver distinctement applied_at et synced_at dans le modèle et l’interface
- [x] Générer et télécharger un reçu PDF après chaque recharge
- [x] Implémenter le scénario de recharge en ligne avec adaptateurs PawaPay Sandbox et Flutterwave Sandbox, sans inventer de contrat non vérifié
- [x] Implémenter le webhook Flutterwave signé, idempotent et traçable côté serveur
- [x] Implémenter la saisie manuelle d’un token avec validation HMAC-SHA256, anti-rejeu et réconciliation offline côté serveur
- [x] Implémenter les commandes de coupure et de rétablissement automatique selon le solde
- [x] Ajouter la détection d’anomalies : surtension, sous-tension, perte de communication, surconsommation, absence de heartbeat, solde bas et dépassement du budget
- [x] Ajouter la supervision administrateur des compteurs par secteur et les statistiques en lecture seule
- [x] Ajouter la génération de messages de diffusion à partir d’une information brute administrateur et leur publication contrôlée
- [x] Ajouter l’agent IA contextualisé sur les données réelles de l’abonné connecté, sans invention de données
- [x] Documenter explicitement les fonctionnalités simulées, les limites et les hypothèses
- [x] Écrire ou mettre à jour les tests Vitest pour chaque fonctionnalité livrée
- [x] Vérifier le typage, le formatage, les tests et le rendu responsive avant la livraison
- [x] Créer un checkpoint final uniquement après validation de tous les éléments terminés

## Écarts à corriger après vérification

- [x] Implémenter une authentification JWT réelle avec access token et refresh token, puis aligner les rôles backend sur abonné et administrateur
- [x] Ajouter les modèles manquants pour tokens, secteurs et paramètres de budget, avec usage réel
- [x] Sécuriser l’ingestion IoT par signature HMAC côté serveur et unicité persistée de message_id
- [x] Ajouter un mécanisme temps réel réel au dashboard, sans simple changement d’état frontend
- [x] Afficher applied_at et synced_at simultanément dans l’historique
- [x] Implémenter la détection réelle des anomalies demandées
- [x] Construire l’interface du dashboard administrateur en lecture seule
- [x] Ajouter des tests Vitest couvrant les fonctionnalités actuellement marquées comme livrées
- [x] Exécuter le formatage et vérifier explicitement le rendu responsive

## Derniers écarts de contextualisation et de preuve

- [x] Connecter l’agent IA aux données de l’abonné réellement authentifié et distinguer explicitement DEMO des données persistées
- [x] Faire remonter les anomalies calculées dans le snapshot affiché, y compris le dépassement du budget
- [x] Ajouter les tests Vitest pour l’agent IA, le dashboard administrateur, applied_at/synced_at et le rafraîchissement périodique
- [x] Effectuer une vérification responsive mobile distincte avec capture

## Écarts IoT et recharge à corriger

- [x] Créer un endpoint machine-à-machine dédié à l’ingestion IoT, sans session admin, avec authentification par signature et journalisation des rejets
- [x] Persister les tokens manuels et leur anti-rejeu en base, puis réconcilier réellement le solde, l’historique et applied_at/synced_at
- [x] Associer un reçu PDF à chaque recharge individuelle dans l’interface et le backend
- [x] Étendre la validation temporelle IoT aux messages trop anciens et à l’ordre des messages, avec journalisation des rejets

## Derniers écarts fonctionnels à traiter

- [x] Relier les procédures payments.\* à une interface de recharge utilisable et rendre les erreurs sandbox visibles
- [x] Appliquer le rétablissement/coupure du relais dans tous les parcours de crédit/débit pertinents
- [x] Contextualiser aiAssistant avec télémétrie, solde, alertes et historique persistés du compteur associé
- [x] Gérer explicitement les doublons/rejeux SQL des tokens et distinguer une vraie réconciliation offline avec applied_at différent de synced_at

## Écarts finaux de production à corriger

- [x] Aligner réellement le RBAC backend sur les rôles `abonné` et `administrateur` dans le schéma, les gardes serveur et les parcours UI/API
- [x] Brancher les JWT access/refresh au middleware d’authentification réel et vérifier le flux complet côté client et serveur
- [x] Utiliser réellement `sectors` et `budgetSettings` dans les requêtes métier, le dashboard et la détection d’anomalies
- [x] Faire reposer la détection d’anomalies sur les données persistées et les paramètres SQL, avec tests de dépassement du budget

## Refonte demandée par l’utilisateur — backend et frontend

- [x] Remplacer le backend applicatif actuel par Python avec Django, Django REST Framework et Django Channels
- [x] Conserver exclusivement la communication compteur → backend par HTTPS POST signé toutes les cinq secondes, sans broker MQTT
- [x] Vérifier la structure et les références visuelles du document exempleasuivre.docx
- [x] Remplacer les graphiques actuels par des graphiques circulaires/donut professionnels avec couleurs distinctes et légende lisible
- [x] Refaire le front avec une hiérarchie visuelle professionnelle, des cartes propres et une présentation cohérente avec Virunga Énergie
- [x] Ajouter des publications visuelles dédiées à Goma, Rutshuru, Matebe et la centrale, sans présenter de scènes générées comme des preuves documentaires
- [x] Ajouter des visuels sur la conservation de la nature de Virunga, notamment gorilles et singes, avec contexte respectueux
- [x] Ajouter des visuels expliquant les problèmes énergétiques ciblés à Goma et Rutshuru sans inventer de statistiques
- [x] Créer une identité visuelle/logo Virunga Énergie utilisable dans le frontend
- [x] Ajouter une publication visuelle illustrant l’avantage d’un compteur électrique intelligent et la recharge simple
- [x] Migrer les contrats backend/frontend et les tests vers la nouvelle architecture réellement disponible
- [x] Vérifier desktop et mobile, puis créer un nouveau checkpoint final après validation

## Écarts de migration effective à corriger

- [x] Basculer réellement le runtime applicatif et le frontend vers Django/DRF/Channels, sans laisser le dashboard dépendre de `trpc.*` en production
- [x] Désactiver le pipeline IoT Node en production via le Dockerfile Daphne et réserver le serveur Node au preview géré du template
- [x] Ajouter dans l’UI une mention explicite que les visuels générés sont des illustrations éditoriales et non des preuves photographiques documentaires
- [x] Remplacer les appels `trpc.*` du dashboard par des appels aux endpoints DRF et au canal Channels réellement utilisés
- [x] Ajouter des tests d’intégration ciblés pour les endpoints DRF/Channels et créer un checkpoint après cette migration effective

## Preuves finales de migration à produire

- [x] Faire tourner réellement l’application sur le runtime Django/DRF/Channels ou fournir une preuve de bascule effective et désactiver le backend Node applicatif restant en production
- [x] Brancher un vrai client WebSocket frontend sur Django Channels pour les rafraîchissements temps réel, tout en gardant l’ingestion compteur en HTTPS POST signé
- [x] Ajouter des tests d’intégration Django pour `/api/dashboard/`, `/api/assistant/`, `/api/admin/overview/`, `/api/receipts/...` et un test WebSocket Channels
- [x] Créer un nouveau checkpoint après validation effective de la migration Python

## Refonte UI publique, connexion et dashboard industriel

- [x] Créer une page publique Virunga Énergies avec navigation Accueil, Impact Social, Actualités et CTA Espace Abonné
- [x] Préparer les visuels régionaux pour Matebe, Rutshuru, Goma, les techniciens réseau et les familles utilisant l’énergie prépayée
- [x] Ajouter les cartes institutionnelles sur l’énergie durable, la conservation et le comptage intelligent
- [x] Construire une connexion frontend avec Nom, Prénom et code compteur strictement limité à 20 chiffres, avec validation claire
- [x] Isoler le dashboard abonné dans une direction Industrial Dark Command Center, sans photos ni bannières publiques
- [x] Afficher identité, compteur, statut live et indicateur HMAC dans l’en-tête du dashboard sécurisé
- [x] Reconcevoir les KPI et graphiques de consommation avec un contraste industriel, des indicateurs précis et des logs structurés
- [x] Ajouter le panneau relais avec statut et modal de confirmation frontend sans modifier la logique backend
- [x] Vérifier l’expérience responsive public, connexion et dashboard, puis écrire les tests frontend associés

## Vérifications complémentaires de la refonte UI

- [x] Ajouter un visuel explicite de techniciens réseau intervenant sur des poteaux et vérifier la présence de Matebe, Rutshuru, Goma et des familles prépayées
- [x] Vérifier visuellement le modal de connexion et le dashboard post-login en format desktop et mobile
- [x] Ajouter des tests frontend couvrant les parcours public, connexion, dashboard industriel et confirmation relais
- [x] Capturer explicitement le modal de connexion ouvert sur desktop et mobile avant livraison

## Évolutions Django, relais et actualités demandées

- [x] Vérifier le contrat Django d’authentification abonné et associer Nom, Prénom et code compteur de 20 chiffres au dashboard sécurisé
- [x] Implémenter une commande relais temps réel côté Django avec état Connected/Disconnected, sans inventer de protocole ESP32 absent
- [x] Ajouter un modèle, des endpoints et une section frontend pour les actualités locales Virunga Energies dynamiques
- [x] Tester les flux d’authentification, de commande relais et d’actualités, puis vérifier le responsive de la vitrine et du dashboard

## Accès abonné de démonstration demandé

- [x] Vérifier le schéma et les compteurs disponibles avant de créer l’accès ALFAJIRI Ndabereye
- [x] Appliquer la migration de données qui associe le code compteur unique au compteur de démonstration
- [x] Vérifier la connexion de l’abonné ALFAJIRI Ndabereye sur l’application déployée et communiquer les consignes d’utilisation
- [x] Corriger le service des fichiers statiques frontend par Django afin de rétablir le rendu de production (build `dist/public` produit et vérifié servi par Django le 24/08/2026)

## Correctifs appliqués le 24/08/2026 (audit vs prompt d'ingénierie)

- [x] Ajouter `backend/manage.py` (absent de l'archive — le Dockerfile échouait)
- [x] Ajouter `backend/energy/migrations/__init__.py` (les migrations n'étaient jamais chargées ; le seed ALFAJIRI ne s'appliquait pas)
- [x] Aligner le contrat de télémétrie sur le prompt (message_id UUID, device_timestamp, voltage/current/power/energy_consumed, relay_status booléen, signal_strength, device_status, firmware_version)
- [x] Vérifier la signature HMAC sur le payload brut reçu (le compteur signe ce qu'il envoie)
- [x] Ajouter le refresh token JWT (rotation + jti) et `/api/auth/token/refresh/`
- [x] Implémenter le scénario B complet (token HMAC lié meter_id + séquence, anti-rejeu persistant, réconciliation SAISIE_MANUELLE applied_at/synced_at)
- [x] Implémenter l'initiation PawaPay/Flutterwave (sandbox documentées, 503 explicite sans clé) et le webhook Flutterwave signé idempotent avec complétion de recharge (bug d'arguments inversés corrigé)
- [x] Remplacer le reçu PDF factice par un vrai PDF (générateur pur Python, sans dépendance)
- [x] Agent IA contextuel sur données réelles (refus explicite hors périmètre)
- [x] Détection d'anomalies (surtension, sous-tension, surconsommation, solde bas/épuisé, budget, perte de communication) avec déduplication
- [x] Coupure/rétablissement automatique du relais selon le solde (vérifié en réel)
- [x] `/api/admin/overview/` sans métriques fabriquées (suppression du `or 32`)
- [x] SQLite par défaut (prompt) ; PostgreSQL via `DATABASE_URL` après la phase Business
- [x] Gestion des écritures concurrentes SQLite (timeout + 503 explicite au lieu de 500)
- [x] Simulateur `manage.py simulate_meter` utilisant le pipeline réel (POST signé 5 s, compteur is_demo)
- [x] Tests : 30/30 verts (dont complétion webhook, anti-rejeu, PDF, RBAC, anomalies) ; test statique Windows corrigé (fermeture de la réponse)

## Ajouts du 24/08/2026 (après-midi) — camemberts consommation

- [x] API `/api/dashboard/` : `consumption_daily` (4 périodes Nuit/Matin/Après-midi/Soirée sur 24 h) et `consumption_weekly` (7 jours calendaires, max−min d'énergie cumulée, jours sans relevé à 0) — calculées depuis les télémétries persistées, aucune valeur inventée
- [x] Dashboard abonné : deux camemberts SVG (zéro dépendance) « Consommation journalière » et « Consommation hebdomadaire » avec légende kWh/%, total au centre et badge DONNÉES DEMO en mode démo
- [x] Seed simulateur étendu à 7 jours (168 points) avec profil jour/nuit + boost week-end, et RATTRAPAGE de l'état réel du compteur (énergie cumulée et balance finissent à la valeur actuelle, le temps réel reprend à la suite) — corrige le jour courant aberrant (mélange seed/temps réel)
- [x] Tests : +2 Django (agrégations déterministes + contrat API) → 32/32 ; +1 Vitest (rendu des donuts et totaux) → 16/16

## Correctifs du 07/10/2026 (relecture complète du dépôt)

- [x] Démarrage : suppression de `import pymysql` dans `backend/config/__init__.py` (paquet absent de `requirements.txt` → aucune commande `manage.py` ne se lançait, Docker compris)
- [x] Django 5.2 / DRF 3.16 (Django 5.1 n'est plus maintenu et plante sous Python 3.14) ; `daphne` dans `INSTALLED_APPS` pour que `runserver` serve aussi le WebSocket
- [x] Recharge écrasée : la télémétrie suivante remplaçait le solde serveur par le solde local du compteur. Les crédits non transmis sont ajoutés et renvoyés au compteur (`credit_kwh`, champ `Recharge.delivered_at`, migration 0006)
- [x] Commande relais de l'abonné : elle n'était jamais envoyée au compteur et la règle de solde l'annulait. Elle part dans `relay_command` et l'isolement tient jusqu'au rétablissement demandé ; rétablissement refusé (409) à solde nul
- [x] Simulateur : applique `credit_kwh` et `relay_command`, ne consomme plus relais ouvert, redémarre dans l'état connu du backend
- [x] Paiements — crédit gratuit possible : `/api/payments/flutterwave/verify/?status=successful` et le callback PawaPay créditaient sans preuve. Confirmation serveur à serveur obligatoire (statut, référence, montant, devise) ; webhook Flutterwave contrôlé sur le montant
- [x] PawaPay : `depositId` au format UUID (exigé par l'API), dépôt refusé marqué FAILED, le polling de statut s'arrête quand le callback a déjà crédité
- [x] `POST /api/budget/` renvoyait 500 (`detect_anomalies` appelé sans télémétrie)
- [x] JWT : un refresh token (7 jours) était accepté comme jeton d'accès ; clé par défaut connue remplacée par une clé aléatoire hors mode debug ; `.env` chargé avant la lecture de `DJANGO_SECRET_KEY` / `DJANGO_DEBUG` / `DJANGO_ALLOWED_HOSTS`
- [x] Token revendeur : la réponse affichait l'ancien solde ; marquage et crédit dans la même transaction ; numéro de recharge sur le reçu PDF
- [x] Frontend : suppression du faux jeton `token-session-…`, « Coût estimé aujourd'hui » calculé sur la consommation (affichait le solde), « Dernière communication » réelle, retrait des chiffres inventés (disponibilité 99,8 %, latence 39 ms), reconnexion automatique par le cookie `vse_refresh`, déconnexion qui efface ce cookie
- [x] Dépôt : `__pycache__` et le raccourci Windows retirés du suivi Git, `backend/.env.example`, README complété
- [x] Tests : Django 53/53 (+12), Vitest 18/18 (+2), `tsc --noEmit` sans erreur ; essai de bout en bout serveur + simulateur (recharge conservée, relais OFF/ON exécuté par le compteur)

## Points restants traités le 07/10/2026 (suite)

- [x] Connexion administrateur Django : `POST /api/auth/admin/login/` (compte `is_staff` créé par `createsuperuser`, limité à 10 essais/minute), jeton `domain_role=administrateur` honoré seulement si le compte est réellement administrateur
- [x] Page `/admin` refaite sur l'API Django (elle dépendait de l'ancienne authentification Node) : connexion, supervision réelle actualisée toutes les 15 s, alertes ouvertes, émission de token revendeur
- [x] Crédit au compteur fiabilisé : la réponse de télémétrie liste les crédits (`credits`) tant que le compteur ne les a pas accusés (`credit_acks`) — plus de perte si une réponse s'égare, pas de double crédit
- [x] Modèle DeepSeek par défaut : `deepseek-flash` (l'ancien nom `deepseek-v4-flash-vision-exp` est retiré)
- [x] Tests : Django 54/54, Vitest 20/20 (+2 pour la page administrateur), `tsc --noEmit` sans erreur

## Mission débogage & UI/UX du 07/10/2026

- [x] Connexion : lecture défensive de la réponse (`?.`), plus de `Cannot read properties of undefined (reading 'first_name')` ; contrat `/api/auth/subscriber/login/` vérifié par test (`access_token` + `subscriber.first_name/last_name/meter_id`)
- [x] Session : toutes les requêtes abonné passent par `authorizedFetch` (en-tête `Authorization: Bearer`), renouvellement automatique sur 401 par le cookie `vse_refresh` ; l'API répond désormais 401 (et non 403) à un jeton expiré
- [x] Modal de connexion compact et centré (la classe `sm:max-w-lg` du composant l'emportait sur `max-w-md`), Nom/Prénom côte à côte, validation par Entrée
- [x] Graphiques : courbe lissée à dégradé et halo, infobulles au survol/toucher (LiveChart, WeeklyBars), jauge colorée selon le niveau de crédit, animations d'apparition
- [x] Carrousel animé (fondu, défilement automatique suspendu au survol, puces de navigation) ; effet d'onde lumineuse au clic sur tous les boutons (`useButtonRipple`, désactivé si « réduire les animations »)
- [x] Boutons : « Voir le rapport » télécharge le rapport CSV, « Voir tout » déplie les alertes, « Marquer lue » acquitte via `POST /api/alerts/<id>/ack/`, chaque entrée du menu latéral pointe vers son panneau ; un test vérifie qu'aucun bouton du tableau de bord n'est sans action
- [x] Alertes dégressives 15 / 10 / 5 / 3 / 1 % (`CREDIT_SEUIL_<n>`), une par seuil et par cycle de recharge, sans changement de base de données
- [x] Notifications e-mail (Gmail SMTP), SMS (Twilio) et WhatsApp (Twilio ou Meta Cloud API) dans `energy/notifications.py`, envoyées hors du fil de la télémétrie ; canal non configuré = signalé, jamais simulé
- [x] Tableau de bord : carte « Niveau de crédit » avec les seuils franchis, panneau « Alertes de crédit » (coordonnées via `/api/profile/`, état des canaux, message d'essai via `/api/notifications/test/`) ; les alertes critiques s'affichent enfin en rouge (`CRITICAL` n'était pas reconnu)
- [x] Tests : Django 58/58, Vitest 22/22, `tsc --noEmit` sans erreur, build de production réussi
