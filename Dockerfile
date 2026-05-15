FROM python:3.11-slim
 
WORKDIR /app
 
# Dépendances système minimales
RUN apt-get update && apt-get install -y --no-install-recommends \
    build-essential \
    && rm -rf /var/lib/apt/lists/*
 
COPY requirements.txt .
 
# Installation sans cache (réduit la taille de l'image)
RUN pip install --no-cache-dir -r requirements.txt
 
# Téléchargement du modèle ONNX au BUILD (pas au démarrage)
# MiniLM multilingual : ~100 MB, 384 dims, no PyTorch
RUN python -c "\
from fastembed import TextEmbedding; \
m = TextEmbedding('sentence-transformers/paraphrase-multilingual-MiniLM-L12-v2'); \
list(m.embed(['warmup']))"
 
COPY . .
 
# $PORT est injecté dynamiquement par Railway
CMD ["sh", "-c", "uvicorn main:app --host 0.0.0.0 --port ${PORT:-8000}"]
 
