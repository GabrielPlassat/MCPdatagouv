# MCPdatagouv

POC d'un assistant conversationnel connecté au portail open data français via le [MCP data.gouv.fr](https://github.com/datagouv/datagouv-mcp).

## Comment ça marche ?

L'application utilise :
- **Claude (Anthropic)** comme moteur de raisonnement
- **Le MCP data.gouv.fr** (hébergé à `https://mcp.data.gouv.fr/mcp`) pour accéder aux datasets
- **Streamlit** pour l'interface

Le MCP permet à Claude de **rechercher des jeux de données**, **lire leurs métadonnées** et **interroger leur contenu** directement depuis la conversation.

## Déploiement sur Streamlit Cloud

### 1. Forker ce repo sur GitHub

### 2. Ajouter votre clé API 

### 3. Déployer l'app

Pointez Streamlit Cloud sur votre repo, branch `main`, fichier `app.py`.

## Outils MCP disponibles

Le MCP data.gouv.fr expose ces outils à Claude :

| Outil | Description |
|-------|-------------|
| `search_datasets` | Recherche de jeux de données par mots-clés |
| `get_dataset_info` | Infos détaillées sur un dataset |
| `list_dataset_resources` | Liste les fichiers d'un dataset |
| `get_resource_info` | Infos sur un fichier spécifique |
| `query_resource_data` | Interroge les données via l'API Tabulaire |
| `download_and_parse_resource` | Télécharge et parse un fichier CSV/JSON |
| `get_metrics` | Statistiques de consultation d'un dataset |

## Exemples de questions

- *"Quels jeux de données sont disponibles sur les prix de l'immobilier ?"*
- *"Trouve des données sur la population des communes françaises"*
- *"Montre-moi les 5 premières lignes du dataset DVF"*
- *"Quels datasets parlent de la qualité de l'air ?"*

