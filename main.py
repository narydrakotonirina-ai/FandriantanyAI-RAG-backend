import os
import json
import asyncio
import hashlib
from fastapi import FastAPI
from pydantic import BaseModel
from supabase import create_client
from cachetools import TTLCache
from fastembed import TextEmbedding
from groq import Groq

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
            model="qwen/qwen-3-32b",
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
            "match_count": top_k
        }).execute()

        return res.data

    except Exception as e:
        print(f"❌ search error: {e}")
        return []


# ==============================
# GENERATION GROQ (ROBUSTE)
# ==============================

async def safe_generate(question, context, type_probleme):

    prompt = f"""
Tu es un expert du droit foncier malgache.

Réponds STRICTEMENT avec :

Situation :
Risques :
Démarches :

Contexte :
{context}

Question :
{question}
"""

    for attempt in range(3):
        try:
            res = groq_client.chat.completions.create(
                model="qwen/qwen-3-32b",
                messages=[
                    {"role": "system", "content": "Réponse juridique claire"},
                    {"role": "user", "content": prompt}
                ],
                max_tokens=500,
                temperature=0.2,
            )

            text = res.choices[0].message.content

            if text:
                return text

        except Exception as e:
            print(f"⚠️ generate attempt {attempt+1}: {e}")
            await asyncio.sleep(1)

    return "❌ Erreur génération Groq"


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

    # ✅ CACHE
    if qid in cache:
        return cache[qid]

    try:
        # ✅ TRIAGE
        triage = await groq_triage(q.question)

        if triage["hors_perimetre"]:
            return {"error": "hors_perimetre"}

        # ✅ SEARCH
        chunks = await hybrid_search(
            triage["requete_enrichie"],
            top_k=5
        )

        if not chunks or chunks[0].get("score", 0) < 0.15:
            return {"error": "non_trouve"}

        # ✅ CONTEXT
        context = build_context(chunks)

        # ✅ GENERATION
        answer = await safe_generate(
            q.question,
            context,
            triage["type_probleme"]
        )

        result = {
            "answer": answer,
            "sources": chunks
        }

        cache[qid] = result

        return result

    except Exception as e:
        print(f"❌ /ask error: {e}")
        return {"error": "generation_failed"}
