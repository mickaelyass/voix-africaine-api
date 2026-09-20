FROM python:3.11-slim
WORKDIR /app
# ffmpeg requis par pydub (validation/duree audio) - installe avant pip pour le cache
RUN apt-get update && apt-get install -y --no-install-recommends ffmpeg \
    && rm -rf /var/lib/apt/lists/*
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt
COPY . .
EXPOSE 8000
# Render injecte $PORT : le shell la substitue au demarrage (pas au build).
CMD ["sh", "-c", "uvicorn main:app --host 0.0.0.0 --port ${PORT:-8000} --proxy-headers"]
