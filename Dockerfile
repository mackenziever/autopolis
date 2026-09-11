FROM python:3.12-slim AS runtime
ENV PYTHONDONTWRITEBYTECODE=1 PYTHONUNBUFFERED=1
WORKDIR /app
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt \
    && pip install --no-cache-dir "litellm>=1.60,<2" "starlette>=0.38,<1" "uvicorn>=0.30,<1" || true
COPY . .
RUN mkdir -p /app/data /app/data/alveare
CMD ["python","main.py","--agents","50","--ticks","600","--hz","15","--log","data/simulation_replay.msgpack"]
