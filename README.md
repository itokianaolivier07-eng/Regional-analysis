# Analyse régionale - Corse

Application d'analyse composée d'une interface React, d'une API FastAPI en lecture seule et d'un pipeline Python qui alimente MongoDB.

## Architecture Docker

- `frontend` construit l'application React puis la sert avec Nginx.
- `api` sert les routes FastAPI sur le réseau interne Compose. Nginx relaie `/api/*` vers ce service.
- `gateway` expose le site et gère HTTPS automatiquement avec Caddy lorsque `SITE_ADDRESS` est un nom de domaine public.
- `pipeline` partage l'image Python de l'API, mais s'exécute séparément et n'est pas lancé par défaut.
- MongoDB reste externe à Compose pour éviter de remplacer ou masquer une base existante. Il doit être joignable depuis les conteneurs.

Le pipeline effectue les étapes 0 à 4 : normalisation, micro-synthèse, méso-synthèse, bilan transversal et synthèse finale. Les utilisateurs ouvrent seulement l'adresse du serveur. L'API et le serveur statique du front ne sont pas publiés directement.

## Démarrage avec Docker Compose

1. Installer Docker Engine et le plugin Docker Compose.
2. Créer le fichier local d'environnement :

   ```sh
   cp .env.example .env
   ```

3. Renseigner dans `.env` l'URI MongoDB réellement accessible depuis Docker ainsi que les clés LLM requises pour le pipeline. Ne jamais publier ce fichier.
4. Construire et démarrer le front et l'API :

   ```sh
   docker compose up --build -d
   ```

5. Ouvrir `http://localhost` pour un essai local.

Pour un accès depuis le réseau local, remplacer `localhost` par l'adresse IP du serveur et autoriser le port 80. Pour un déploiement Internet en HTTPS, définir `SITE_ADDRESS=app.ton-domaine.fr` dans `.env`, faire pointer le DNS vers le serveur et autoriser les ports 80 et 443 dans le pare-feu. Caddy obtiendra et renouvellera automatiquement le certificat TLS. Le domaine doit être publiquement joignable pour cette émission automatique.

### Accès à MongoDB depuis Docker

La valeur d'exemple `mongodb://host.docker.internal:27017/` convient si MongoDB tourne sur la machine hôte et accepte les connexions depuis le réseau Docker. Sur Linux, Compose résout `host.docker.internal` vers la passerelle de l'hôte. Si MongoDB n'écoute que sur `127.0.0.1`, les conteneurs ne pourront pas s'y connecter : configurez plutôt une URI MongoDB privée joignable par les conteneurs et limitez l'accès réseau à cette base. Ne rendez pas MongoDB accessible publiquement.

Pour une base distante, remplacez `MONGO_URI` dans `.env` par son URI privée. Le service `api` doit pouvoir lire les collections d'historique, de pipeline, de synthèse et de runs.

### Lancer le pipeline ponctuellement

Le pipeline est exclu du démarrage normal afin qu'un redémarrage de l'interface ne lance pas une nouvelle analyse :

```sh
docker compose --profile pipeline run --rm pipeline
```

Il accepte les mêmes arguments que `main.py`, par exemple :

```sh
docker compose --profile pipeline run --rm pipeline --stage all --mois 2026-08
```

### Arrêter les services

```sh
docker compose down
```

Les logs du pipeline et ses checkpoints sont conservés dans `./logs` et `./.checkpoint`.

## Développement sans Docker

Lancer l'API depuis la racine du dépôt :

```sh
uvicorn api:app --reload --host 0.0.0.0 --port 8000
```

Puis lancer le front :

```sh
cd frontend
npm ci
npm run dev
```

Vite relaie `/api/*` vers `http://localhost:8000`. Configurez `MONGO_URI` dans `.env` pour une base accessible depuis le processus API.

## Configuration et vérifications

- `SITE_ADDRESS` choisit l'adresse servie par Caddy : `:80` par défaut, ou un nom de domaine public pour activer HTTPS.
- `MONGO_URI` doit être joignable depuis les conteneurs API et pipeline.
- `API_CORS_ORIGINS` sert uniquement aux clients navigateur qui appelleraient directement l'API depuis une autre origine. Avec le proxy Nginx prévu ici, le navigateur utilise la même origine et CORS n'est pas nécessaire.

Vérifications du front :

```sh
cd frontend
npm run build
npm run lint
```

L'API expose également sa documentation OpenAPI sous `/docs` (accessible via `http://localhost:8080/api/docs` en passant par le front).
