FROM python:3.12-slim

WORKDIR /app

RUN apt-get update && apt-get install -y --no-install-recommends \
    libpq-dev gcc tesseract-ocr poppler-utils \
    && rm -rf /var/lib/apt/lists/*

COPY requirements.txt .
# Install CPU-only PyTorch first: avoids downloading ~3.5GB of heavy NVIDIA CUDA wheels,
# which causes extremely slow builds, hash mismatches, and network dropouts.
RUN pip install --no-cache-dir torch --index-url https://download.pytorch.org/whl/cpu && \
    pip install --no-cache-dir -r requirements.txt

# Pre-download both ML models at BUILD time, not at request time. Without
# this, the first submission upload (embedding model) and the first report
# generation (AI-detection model) each trigger a ~90MB-500MB Hugging Face
# download on-demand, inside the request itself. If the machine running the
# container has restricted/slow/blocked outbound internet access at runtime
# (common with campus/corporate networks, VPNs, or Docker network configs),
# that download can take a very long time or effectively hang — which is
# exactly what shows up as a submission stuck forever on "embedding" status
# and reports permanently refusing to generate ("needs to finish indexing").
# Baking the models into the image means they're already on disk before the
# container ever starts, so no network call happens during normal use.
RUN python -c "from sentence_transformers import SentenceTransformer; SentenceTransformer('all-MiniLM-L6-v2')"
RUN python -c "from transformers import pipeline; pipeline('text-classification', model='openai-community/roberta-base-openai-detector', top_k=None)"

# Force offline mode from here on (i.e. at container RUNTIME, not during the
# two RUN steps above, which still needed network to fetch the models once).
# Without this, sentence-transformers/transformers still try an online
# "is there a newer version of this model" check before falling back to the
# local cache on every load — even though the files are already on disk.
# If the *running container's* network can't reach huggingface.co for any
# reason (this can differ from the image build's network path — very common
# with Docker Desktop on Windows behind a VPN or corporate firewall), that
# check has no timeout and hangs indefinitely, with nothing to catch or log:
# exactly the silent "stuck on Indexing forever, no error anywhere" symptom.
# These two variables make both libraries skip the online check entirely and
# read only from the cache baked in above, so no network call happens at
# runtime at all.
ENV HF_HUB_OFFLINE=1
ENV TRANSFORMERS_OFFLINE=1

# TOKENIZERS_PARALLELISM=false is the standard, well-documented fix for a
# specific deadlock: Hugging Face's tokenizer (used by both the embedding
# model and the AI-detection model) spawns its own internal Rust-level
# thread pool. When the *first* real tokenize/encode call happens from
# inside a Python thread that isn't the process's main thread — exactly
# what happens here, since FastAPI runs a sync route like our upload
# endpoint in a worker thread, not the main thread — that internal thread
# pool can deadlock completely: no exception, no timeout, the call just
# never returns. This is why the model loaded fine in a one-off `python -c`
# test (that only constructs the model; it never calls .encode() from a
# worker thread) but the real upload pipeline hung with nothing logged.
# OMP_NUM_THREADS/MKL_NUM_THREADS/OPENBLAS_NUM_THREADS=1 close out a related,
# similarly-shaped class of bug: PyTorch's CPU math libraries can spawn far
# more threads than a container's actual CPU allocation, especially common
# on Docker Desktop for Windows (WSL2), leading to severe oversubscription
# that ranges from "very slow" to effectively hung.
ENV TOKENIZERS_PARALLELISM=false
ENV OMP_NUM_THREADS=1
ENV MKL_NUM_THREADS=1
ENV OPENBLAS_NUM_THREADS=1

COPY . .

EXPOSE 8000

CMD ["sh", "-c", "alembic upgrade head && uvicorn app.main:app --host 0.0.0.0 --port 8000"]
