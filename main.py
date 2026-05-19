import os
import json
import asyncio
import hashlib
import re
from fastapi import FastAPI
from pydantic import BaseModel
from supabase import create_client
from cachetools import TTLCache
from fastembed import TextEmbedding
from groq import Groq
from fastapi.middleware.cors import CORSMiddleware

# ==============================
# CONFIG
# ==============================

SUPABASE_URL = os.getenv("SUPABASE_URL")
SUPABASE_KEY = os.getenv("SUPABASE_KEY")
GROQ_API_KEY = os.getenv("GROQ_API_KEY")

# Clients
sb = create_client(SUPABASE_URL, SUPABASE_KEY)
groq_client = Groq(api_key=GROQ_API_KEY)

# Embedding model (CPU)
model = TextEmbedding()

def embed(text):
    return list(model.embed([text]))[0].tolist()


# Cache (1h)
cache = TTLCache(maxsize=1000, ttl=3600)

app = FastAPI()

app.add_middleware(
    CORSMiddleware,
    allow_origins=
    [
        "http://localhost:3000",
        "https://foncier-ai.vercel.app",
    ],
    
 # ✅ accepte toutes les URLs Vercel (preview inclus)
    allow_origin_regex=r"https://.*\.vercel\.app",
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# ==============================
# SCHEMA
# ==============================

class QuestionRequest(BaseModel):
    question: str


# ==============================
# UTILS
# ==============================

def hash_question(q: str):
    return hashlib.md5(q.encode()).hexdigest()


def build_context(chunks, max_chars=4000):
    context = ""

    for c in chunks:
        txt = c["texte"]
        if len(context) + len(txt) > max_chars:
            break
        context += f"\n[{c['id']}]\n{txt}\n"

    return context


def filtrer_think(text: str) -> str:
    if not text:
        return ""

    # ✅ supprimer bloc <think>
    text = re.sub(r"<think>.*?</think>", "", text, flags=re.DOTALL)

    # ✅ essayer de garder à partir de "Situation"
    match = re.search(r"(Situation\s*:.*)", text, flags=re.DOTALL | re.IGNORECASE)
    if match:
        return match.group(1).strip()

    # ✅ sinon retourner tel quel (important !)
    return text.strip()




# ==============================
# TRIAGE GROQ
# ==============================

async def groq_triage(question: str):
    prompt = f"""
Analyse la question juridique suivante :

Retourne JSON strict :
{{
  "hors_perimetre": true/false,
  "type_probleme": "...",
  "requete_enrichie": "..."
}}

Question: {question}
"""

    try:
        res = groq_client.chat.completions.create(
            model="qwen/qwen3-32b",
            messages=[{"role": "user", "content": prompt}],
            max_tokens=200,
            temperature=0
        )

        content = res.choices[0].message.content.strip()


        # ✅ parsing sécurisé
        data = json.loads(content)

        return data


    except Exception as e:
        print(f"❌ triage error: {e}")
        return {
            "hors_perimetre": False,
            "type_probleme": "",
            "requete_enrichie": question
        }


# ==============================
# SEARCH (VECTOR)
# ==============================

async def hybrid_search(query: str, top_k=5):

    embedding = embed(query)  # ✅ appel simple

    try:
        res = sb.rpc("match_chunks", {
            "query_embedding": embedding,
            "match_threshold": 0.15,
            "match_count": top_k
        }).execute()

        return res.data

    except Exception as e:
        print(f"❌ search error: {e}")
        return []


# ==============================
# GENERATION GROQ (ROBUSTE)
# ==============================

import re
import asyncio

# ==========================
# ✅ FILTRE ROBUSTE
# ==========================
def filtrer_think(text: str) -> str:
    if not text:
        return ""

    # ✅ supprimer balises think (même mal fermées)
    text = text.replace("<think>", "").replace("</think>", "")

    # ✅ couper tout avant "Situation"
    match = re.search(r"(Situation\s*:.*)", text, flags=re.DOTALL | re.IGNORECASE)

    if match:
        return match.group(1).strip()

    return text.strip()


# ==========================
# ✅ SAFE GENERATE OPTIMISÉ
# ==========================
async def safe_generate(question, context, type_probleme):

    # ✅ LIMITER LE CONTEXTE (évite troncature)
    MAX_CHARS = 1500
    context = context[:MAX_CHARS]

    prompt = f"""
Tu es un expert en droit foncier malgache.

Réponds en français clair et professionnel.

Structure ta réponse comme suit :

Situation :
Décris la situation juridique.

Risques :
Explique les risques ou points d’attention.

Démarches :
Propose des actions concrètes.

IMPORTANT :
- Réponds uniquement en français
- Donne directement la réponse finale
- N'affiche pas de raisonnement interne
- Réponse concise (10 à 15 lignes)

Contexte :
{context}

Question :
{question}
"""

    for attempt in range(3):
        try:
            res = groq_client.chat.completions.create(
                model="qwen/qwen3-32b",
                messages=[
                    {"role": "system", "content": "Assistant juridique spécialisé foncier"},
                    {"role": "user", "content": prompt}
                ],
                max_tokens=1000,  # ✅ AUGMENTÉ
                temperature=0.2,
            )

            text = res.choices[0].message.content

            if text:
                cleaned = filtrer_think(text)

                # ✅ ne plus bloquer
                return cleaned

        except Exception as e:
            print(f"⚠️ generate attempt {attempt+1}: {e}")
            await asyncio.sleep(1)

    # ✅ fallback UX propre
    return """**Contexte juridique :**
            
            Les textes juridiques pertinents ont été identifiés ci-dessous.
            
            Vous pouvez consulter les articles affichés pour comprendre les règles applicables à votre situation.
            
            """




# ==============================
# ENDPOINT /search
# ==============================

@app.post("/search")
async def search(q: QuestionRequest):
    results = await hybrid_search(q.question)

    if not results:
        return {"error": "no_data"}

    return results


# ==============================
# ENDPOINT /ask
# ==============================

@app.post("/ask")
async def ask(q: QuestionRequest):

    qid = hash_question(q.question)

    try:
        # ✅ INCREMENT IA REQUEST (CORRIGÉ)
        res = sb.table("stats").select("ia_requests").eq("id", 1).execute()

        if res.data and len(res.data) > 0:
            current = res.data[0]["ia_requests"]

            sb.table("stats").update({
                "ia_requests": current + 1
            }).eq("id", 1).execute()

        # ✅ CACHE
        if qid in cache:
            return cache[qid]

        # ✅ TRIAGE
        triage = await groq_triage(q.question)

        if triage["hors_perimetre"]:
            return {
                "answer": "Cette question est hors du domaine du droit foncier.",
                "sources": []
            }

        # ✅ SEARCH
        chunks = await hybrid_search(
            triage["requete_enrichie"],
            top_k=3  # ✅ réduit pour vitesse
        )

        if not chunks or len(chunks) == 0:
            return {
                "answer": "Aucun texte pertinent trouvé.",
                "sources": []
            }

        # ✅ CONTEXT
        context = build_context(chunks)

        # ✅ GENERATION (IA)
        try:
            answer = await safe_generate(
                q.question,
                context,
                triage["type_probleme"]
            )
        except Exception as e:
            print("⚠️ generation fallback:", e)

            # ✅ FALLBACK IMPORTANT
            answer = """Voici les textes juridiques pertinents correspondant à votre question.
Veuillez consulter les sources ci-dessous pour obtenir les informations détaillées."""

        result = {
            "answer": answer,
            "sources": chunks
        }

        # ✅ CACHE
        cache[qid] = result

        return result

    except Exception as e:
        print(f"❌ /ask error:", e)

        # ✅ FALLBACK GLOBAL
        return {
            "answer": "Une erreur est survenue lors du traitement. Veuillez réessayer.",
            "sources": []
        }

#=========================
#DEBUG
#=========================
@app.get("/models")
async def list_models():
    try:
        models = groq_client.models.list()
        return [m.id for m in models.data]
    except Exception as e:
        return {"error": str(e)}

# ==============================
#STATS
# ==============================
@app.get("/stats")
def stats():
    data = sb.table("chunks").select("loi", "categorie").execute()
    rows = data.data or []

    textes = len(set([r["loi"] for r in rows if r.get("loi")]))
    categories = len(set([r["categorie"] for r in rows if r.get("categorie")]))
    articles = len(rows)

    # ✅ FIX CRASH
    res = sb.table("stats").select("*").eq("id", 1).execute()
    data_stats = res.data

    if not data_stats:
        stats_row = {
            "ia_requests": 0,
            "visits": 0
        }
    else:
        stats_row = data_stats[0]

    return {
        "textes": textes,
        "articles": articles,
        "categories": categories,
        "ia_requests": stats_row["ia_requests"],
        "visits": stats_row["visits"]
    }

# ==============================
#CATEGORIES
# ==============================
@app.get("/categories")
def categories():
    data = sb.table("chunks").select("categorie", "loi").execute()

    result = {}

    for row in data.data:
        cat = row["categorie"]

        if cat not in result:
            result[cat] = set()

        result[cat].add(row["loi"])

    return [
        {
            "categorie": k,
            "count": len(v)
        }
        for k, v in result.items()
    ]

# ==============================
#TEXTES  
# ==============================
@app.get("/textes")
def textes(categorie: str = None):
    query = sb.table("chunks").select("loi", "article", "texte", "priorite")

    if categorie:
        query = query.eq("categorie", categorie)

    data = query.execute()

    return data.data

# ==============================
#VISITES  
# ==============================
@app.post("/visit")
def visit():
    try:
        # ✅ récupérer valeur actuelle
        res = sb.table("stats").select("visits").eq("id", 1).execute()
        current = res.data[0]["visits"]

        # ✅ incrémenter
        sb.table("stats").update({
            "visits": current + 1
        }).eq("id", 1).execute()

        return {"status": "ok"}

    except Exception as e:
        print("❌ visit error:", e)
        return {"error": "visit_failed"}


# ==============================
#TRACKS
# ==============================
@app.post("/track")
def track(data: dict):
    sb.table("page_views").insert({
        "type": data.get("type"),
        "name": data.get("name")
    }).execute()

    return {"ok": True}

# ==============================
#STATS-DETAIL
# ==============================
@app.get("/stats-detail")
def stats_detail():

    views = sb.table("page_views").select("type,name").execute().data

    from collections import Counter

    lois = Counter()
    categories = Counter()

    for v in views:
        if v["type"] == "loi":
            lois[v["name"]] += 1
        elif v["type"] == "categorie":
            categories[v["name"]] += 1

    return {
        "top_lois": lois.most_common(5),
        "top_categories": categories.most_common(5)
    }
