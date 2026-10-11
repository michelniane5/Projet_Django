# SunuRéservation

Application Django en français permettant aux clients de trouver des prestataires locaux et de demander un rendez-vous. Les prestataires et les réservations sont gérés depuis l’administration Django. Fuseau horaire : `Africa/Dakar`.

## Fonctionnalités

### Parcours client

- Catalogue des prestataires actifs et de leurs services, avec recherche par nom, métier, ville ou quartier.
- Liens d’appel et de contact WhatsApp.
- Demande de rendez-vous avec coordonnées client et e-mail facultatif.
- Validation des numéros de téléphone (7 à 15 chiffres, séparateurs usuels acceptés), du prix strictement positif et de la durée du service (de 1 à 1 440 minutes).
- Validation des dates futures et détection des chevauchements sur tous les services d’un même prestataire. Les créneaux en attente ou confirmés sont réservés ; les demandes refusées ou annulées libèrent le créneau.
- E-mail de réception de demande, de confirmation/refus par le prestataire et d’annulation par le client, si le client a indiqué une adresse e-mail.
- Page de suivi protégée par un UUID aléatoire. Le client peut annuler une demande encore en attente avec un POST protégé contre les attaques CSRF.

### Administration

- Gestion des prestataires et de leurs services dans `/admin/`.
- Recherche, filtre par date/statut/prestataire et actions groupées pour confirmer ou refuser les demandes en attente.
- Notification e-mail automatique au client après une décision prise depuis l’administration.
- L’administration est réservée aux utilisateurs Django disposant des droits appropriés.

## Sécurité et cohérence des réservations

- L’URL de suivi utilise un UUID imprévisible, jamais l’identifiant séquentiel de base de données. Le lien est un **jeton porteur** : toute personne qui le possède peut accéder aux informations de cette réservation. Le lien est également inclus dans les e-mails envoyés à l’adresse fournie par le client ; il doit rester privé.
- La page de suivi est non-cacheable, exclue de l’indexation et renvoie `Referrer-Policy: no-referrer`.
- Les paramètres secrets et de production viennent de variables d’environnement ; `DEBUG=False` sans clé secrète définie fait échouer le démarrage.
- La création d’une réservation est transactionnelle. Un verrou du prestataire sérialise les vérifications concurrentes ; PostgreSQL est recommandé en production. SQLite convient au développement et aux petits tests, pas à un service de réservation soumis à une forte concurrence.
- Une panne de courrier est consignée dans les journaux, mais n’annule pas une réservation déjà enregistrée.
- Les actions d’administration agissent uniquement sur les demandes encore en attente.

## Prérequis

- Python 3.12 ou plus récent
- pip
- SQLite pour le développement ; PostgreSQL et un serveur PostgreSQL pour un déploiement concurrent en production

## Installation locale

À la racine du projet (dossier contenant `manage.py`) :

### Windows PowerShell

```powershell
py -m venv .venv
.\.venv\Scripts\Activate.ps1
python -m pip install --upgrade pip
pip install -r requirements.txt
Copy-Item .env.example .env
python manage.py migrate
python manage.py createsuperuser
python manage.py runserver
```

### Linux ou macOS

```bash
python3 -m venv .venv
source .venv/bin/activate
python -m pip install --upgrade pip
pip install -r requirements.txt
cp .env.example .env
python manage.py migrate
python manage.py createsuperuser
python manage.py runserver
```

Ouvrez le site à l’adresse <http://127.0.0.1:8000/>. L’environnement `.venv` est local à la machine et ne doit pas être copié entre systèmes. Le fichier `.env` est ignoré par Git ; ne le publiez pas.

### Liens locaux de l’application

Après avoir lancé `python manage.py runserver`, utilisez les liens suivants :

- [Accueil et catalogue des prestataires](http://127.0.0.1:8000/)
- [Administration Django](http://127.0.0.1:8000/admin/)
- Réserver un service : `http://127.0.0.1:8000/reserver/<service_id>/` (remplacez `<service_id>` par l’identifiant numérique du service)
- Suivre une réservation : `http://127.0.0.1:8000/confirmation/<uuid>/` (l’UUID est fourni après la demande et dans l’e-mail de notification)
- Annuler une demande en attente : `http://127.0.0.1:8000/confirmation/<uuid>/annuler/` (action POST protégée par CSRF ; utilisez le bouton de la page de suivi)

Pour accéder à `/admin/`, créez d’abord un compte administrateur avec `python manage.py createsuperuser`, puis connectez-vous. Les réservations et les services peuvent ensuite être gérés depuis cette interface.

### Dépannage : erreur CSRF 403 « Origin checking failed - null »

Cette erreur signifie que le navigateur a envoyé `Origin: null` (souvent parce que la page est ouverte depuis `file://`, une iframe/aperçu isolé ou une origine opaque). **N’ajoutez pas `null` à `CSRF_TRUSTED_ORIGINS` et ne désactivez pas `CsrfViewMiddleware`** : cela affaiblirait la protection.

- Ouvrez le site par son adresse HTTP(S) réelle, et non en ouvrant directement un fichier HTML ni depuis un aperçu isolé. En local utilisez `http://127.0.0.1:8000/` ou `http://localhost:8000/`, puis rechargez le formulaire avant l’envoi.
- Pour un déploiement, définissez dans les variables d’environnement `DJANGO_CSRF_TRUSTED_ORIGINS` sur l’origine complète utilisée par le navigateur, avec son schéma et éventuellement son port, par exemple `https://reservation.example.com`. La valeur doit correspondre exactement au domaine d’accès public ; ne mettez pas de chemin (`/admin/`) ni `null`.
- `DJANGO_ALLOWED_HOSTS` doit également contenir le nom d’hôte correspondant, par exemple `reservation.example.com` (sans `https://`). Redémarrez le serveur Django après toute modification de configuration.
- Si l’erreur continue, vérifiez dans les outils réseau du navigateur la valeur de l’en-tête `Origin` du POST et l’URL affichée dans la barre d’adresse. Pour `Origin: null`, corrigez l’origine de navigation ou l’intégration de l’iframe côté hébergement ; il ne faut pas faire confiance à cette valeur dans Django.

## Configuration de production

Configurez ces valeurs dans le gestionnaire de secrets de l’hébergeur (ne commitez pas `.env`) :

```dotenv
DJANGO_DEBUG=False
DJANGO_SECRET_KEY=<clé aléatoire privée>
DJANGO_ALLOWED_HOSTS=reservation.example.com
DJANGO_CSRF_TRUSTED_ORIGINS=https://reservation.example.com
DJANGO_SECURE_SSL_REDIRECT=True
DJANGO_SECURE_HSTS_SECONDS=31536000
DB_ENGINE=postgresql
DB_NAME=sunureservation
DB_USER=sunureservation
DB_PASSWORD=<mot de passe privé>
DB_HOST=<hôte PostgreSQL>
DB_PORT=5432
EMAIL_BACKEND=django.core.mail.backends.smtp.EmailBackend
EMAIL_HOST=<serveur SMTP>
EMAIL_PORT=587
EMAIL_HOST_USER=<compte SMTP>
EMAIL_HOST_PASSWORD=<mot de passe SMTP>
EMAIL_USE_TLS=True
DEFAULT_FROM_EMAIL=SunuRéservation <noreply@example.com>
```

Générez une clé, par exemple avec `python -c "from django.core.management.utils import get_random_secret_key; print(get_random_secret_key())"`. Activez `DJANGO_SECURE_HSTS_INCLUDE_SUBDOMAINS=True` et `DJANGO_SECURE_HSTS_PRELOAD=True` seulement si le domaine et tous les sous-domaines concernés fonctionnent durablement en HTTPS. Si Django se trouve derrière un reverse proxy de confiance qui écrase l’en-tête `X-Forwarded-Proto`, vous pouvez aussi activer `DJANGO_TRUST_PROXY_SSL_HEADER=True` ; ne l’activez pas si les clients peuvent fournir cet en-tête directement.

Configurez les sauvegardes PostgreSQL, le serveur HTTPS/proxy et la collecte des fichiers statiques (`python manage.py collectstatic`). Le pilote PostgreSQL est inclus dans `requirements.txt`.

En local, le backend e-mail console écrit les courriers dans la sortie du serveur. Les notifications SMTP de production exigent un serveur et des identifiants valides. Si le client ne fournit pas d’adresse e-mail, aucune notification n’est envoyée.

## Routes principales

| Route | Méthode | Fonction |
| --- | --- | --- |
| `/` | GET | Catalogue et recherche |
| `/reserver/<service_id>/` | GET, POST | Formulaire de réservation |
| `/confirmation/<uuid>/` | GET | Suivi protégé par UUID |
| `/confirmation/<uuid>/annuler/` | POST | Annulation d’une réservation en attente |
| `/admin/` | GET/POST | Administration Django |

Les actions groupées sont celles de l’admin Django standard, sans route personnalisée.

## Tests et vérifications

```bash
python manage.py test
python manage.py check
python manage.py makemigrations --check --dry-run
```

Pour une revue de configuration de production, définissez les variables comme ci-dessus puis exécutez `python manage.py check --deploy`. Les contrôles HSTS portant sur tous les sous-domaines et le préchargement dépendent de l’infrastructure ; n’activez ces options que si elles sont adaptées à votre domaine.

La suite comporte des tests des règles métier, des actions admin et des e-mails avec la boîte mémoire de Django. Un test de parcours traverse la demande client, le suivi UUID, la confirmation admin, puis une annulation client distincte. Le test de concurrence s’exécute sur les moteurs supportant `select_for_update` (dont PostgreSQL) et est ignoré sous SQLite.

Le test SMTP conditionnel remet un message à un serveur SMTP configuré, sans destinataire réel. Pour le lancer localement, démarrez Mailpit puis exécutez :

```bash
EMAIL_BACKEND=django.core.mail.backends.smtp.EmailBackend \
EMAIL_HOST=127.0.0.1 EMAIL_PORT=1025 \
EMAIL_USE_TLS=False EMAIL_USE_SSL=False \
RUN_SMTP_INTEGRATION=1 \
python manage.py test reservations.test_workflows.SMTPTransportIntegrationTests
```

Le workflow GitHub Actions `.github/workflows/tests.yml` lance les contrôles sur SQLite et PostgreSQL, démarre Mailpit pour le test de transport SMTP, et vérifie `check --deploy`. Il s’exécute sur `push`, `pull_request` et à la demande. Mailpit prouve que le serveur accepte le message et le capture ; cela ne remplace pas un test de délivrabilité auprès du fournisseur SMTP de production.

## Migrations

Après mise à jour du code :

```bash
python manage.py migrate
```

La migration `0003` attribue les jetons UUID aux anciennes réservations ; `0004` ajoute le statut d’annulation client ; `0005` ajoute le verrou de réservation par prestataire ; `0006` ajoute les validations de téléphone, de prix et de durée des services.

## Structure

```text
config/                  Paramètres et routes Django
reservations/            Modèles, notifications, formulaires, vues, admin, tests
reservations/migrations/  Évolutions de la base de données
manage.py                Commandes Django
requirements.txt         Dépendances Python épinglées
.env.example             Exemple de configuration locale/production
README.md                Documentation
```
#   P r o j e t _ D j a n g o  
 