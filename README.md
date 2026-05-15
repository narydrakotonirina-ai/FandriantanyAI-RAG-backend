# FandriantanyAI-RAG-backend

FandriantanyAI-RAG-backend est une API FastAPI implémentant un pipeline RAG (Retrieval-Augmented Generation) pour l’assistance juridique foncière à Madagascar.

Le système combine recherche vectorielle (Supabase + pgvector) et génération de réponses structurées via Groq (Qwen).

Ce projet permet de répondre à des questions juridiques en s'appuyant exclusivement sur des textes légaux (lois foncières, code du travail, etc.) en combinant recherche vectorielle et génération par LLM.

Il permet de répondre à des questions juridiques en s'appuyant sur :
- 🔎 Recherche hybride (vectorielle + texte)
- 🧠 LLM Groq (Qwen)
- 🗄️ Base vectorielle Supabase (pgvector)

---

# 🚀 Fonctionnalités

✅ Recherche sémantique sur corpus juridique  
✅ Pipeline RAG complet (triage → retrieval → génération)

✅ Réponses structurées :
- Situation
- Risques
- Démarches

✅ Cache des réponses  
✅ Gestion des erreurs et fallback  
✅ Optimisation coûts LLM (limite tokens)

---

# 🏗️ Architecture

```text
┌─────────────────────┐
│     Frontend UI     │
│  (chat utilisateur) │
└─────────┬───────────┘
          │
          ▼
┌─────────────────────┐
│     FastAPI API     │
│   /ask   /search    │
└─────────┬───────────┘
┌─────────┼───────────┐
▼                     ▼
┌─────────────┐   ┌──────────────┐
│  Supabase   │   │    Groq      │
│ PostgreSQL  │   │  Qwen LLM    │
│  + pgvector │   │              │
└─────────────┘   └──────────────┘
```
# 🔄 Pipeline RAG

## 1️⃣ Triage (LLM - Groq)
- classification du type de problème
- détection hors périmètre
- reformulation de la requête

## 2️⃣ Retrieval (Supabase)
- recherche vectorielle (pgvector)
- top_k = 5 chunks
- filtre de qualité : `score >= 0.15`

# 📦 Stack technique

- ⚡ FastAPI
- 🗄️ Supabase (PostgreSQL + pgvector)
- 🤖 Groq (Qwen LLM)
- 🔎 SentenceTransformers (embeddings)
- ⚙️ Cachetools (cache mémoire)
- 🚀 Railway (déploiement)

# 📁 Structure du projet
backend/
├── main.py
├── requirements.txt

# ⚙️ Installation locale

## 1. Cloner

```bash
git clone https://github.com/TON_USERNAME/FandriantanyAI-RAG-backend.git
cd FandriantanyAI-RAG-backend 
```
## 2. Installer les dépendances
pip install -r requirements.txt

## 3. Configurer les variables d’environnement
Créer .env :
Plain Textenv n’est pas entièrement prise en charge. La coloration syntaxique est basée sur Plain Text.SUPABASE_URL=your_urlSUPABASE_KEY=your_service_keyGROQ_API_KEY=your_groq_keyAfficher plus de lignes

## 4. Lancer le serveur
Shelluvicorn main:app --reloadAfficher plus de lignes

# 📡 Endpoints API

✅ POST /ask
Pipeline RAG complet
Request
JSON{  "question": "Comment calculer l’indemnité de licenciement ?"}Afficher plus de lignes

Response
JSON{  "answer": "...",  "sources": [...]}``Afficher plus de lignes

✅ POST /search
Recherche vectorielle simple
JSON{  "question": "licenciement économique"}``Afficher plus de lignes

#🧠 Fonctionnement interne
✔️ Cache
TTL = 1h
évite appels LLM inutiles

✔️ Limitation contexte
max ~4000 caractères
évite overflow tokens

✔️ Retry LLM
3 tentatives si erreur

✔️ Sécurité
blocage hors périmètre
seuil de pertinence

# 🚀 Déploiement (Railway)
## 1. Push GitHub
Shellgit add .git commit -m "deploy"git pushAfficher plus de lignes

## 2. Sur Railway
Create Project → GitHub Repo
sélectionner le repo

## 3. Variables
Plain Textenv n’est pas entièrement prise en charge. La coloration syntaxique est basée sur Plain Text.SUPABASE_URL=...SUPABASE_KEY=...GROQ_API_KEY=...Afficher plus de lignes

## 4. Commande de démarrage
Shelluvicorn main:app --host 0.0.0.0 --port $PORT``Afficher plus de lignes

# 🗄️ Base de données (Supabase)
Table chunks
SQLcreate extension if not exists vector;create table chunks (  id text primary key,  loi text,  article text,  categorie text,  priorite text,  texte text,  embedding vector(768));Afficher plus de lignes

# ⚠️ Sécurité
❗ Ne jamais exposer :
SUPABASE_KEY
GROQ_API_KEY

✅ Toujours utiliser des variables d’environnement

# 📈 Roadmap
✅ Hybrid search (FTS + vector fusion α=0.5)
✅ Citation automatique dans réponse
✅ UI chatbot frontend
✅ Cache Redis distribué
✅ monitoring des requêtes

# ⚖️ Disclaimer
Cet outil est fourni à titre informatif uniquement.
Il ne constitue pas un conseil juridique personnalisé.

# 🤝 Contribution
Les contributions sont les bienvenues :

# 📚 Licence
Usage libre à des fins éducatives et informatives
