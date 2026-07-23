FROM python:3.11-slim

WORKDIR /app

# System deps kept minimal; wheels cover numpy/scipy/statsmodels/matplotlib.
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

COPY . .

# Credentials live on a persistent volume mounted at /data (see render.yaml).
ENV AUTH_CONFIG_PATH=/data/auth_config.yaml \
    PYTHONUNBUFFERED=1

EXPOSE 8501

# Shell form so ${PORT} (set by the host, e.g. Render) is expanded; falls back to 8501.
CMD streamlit run app.py \
    --server.port=${PORT:-8501} \
    --server.address=0.0.0.0 \
    --server.headless=true
