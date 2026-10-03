# Backend image: the frozen LocalFlex engine + the FastAPI service. Build from the repository root.
FROM python:3.13-slim
ENV PYTHONUNBUFFERED=1 PIP_NO_CACHE_DIR=1
WORKDIR /app
COPY webapp/backend/requirements.txt /tmp/req.txt
RUN pip install -r /tmp/req.txt
COPY . /app
ENV LOCALFLEX_ROOT=/app LOCALFLEX_DATA_DIR=/data
WORKDIR /app/webapp/backend
EXPOSE 8000
CMD ["sh", "-c", "uvicorn app.main:app --host 0.0.0.0 --port ${PORT:-8000}"]
