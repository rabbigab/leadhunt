FROM python:3.11-slim

# Dépendances système pour Firefox (Camoufox)
RUN apt-get update && apt-get install -y --no-install-recommends \
    libglib2.0-0 libnss3 libatk1.0-0 libatk-bridge2.0-0 libcups2 \
    libdrm2 libdbus-1-3 libxrandr2 libgbm1 libasound2 \
    libx11-xcb1 libxcomposite1 libxdamage1 libxfixes3 \
    libxshmfence1 libgtk-3-0 fonts-liberation \
    && rm -rf /var/lib/apt/lists/*

WORKDIR /app

COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# Télécharger le binaire Firefox Camoufox au build (pas au runtime)
RUN python -m camoufox fetch

COPY . .

RUN mkdir -p sessions logs

CMD ["python", "main.py"]
