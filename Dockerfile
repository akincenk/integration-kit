FROM python:3.13-slim
WORKDIR /app
RUN pip install --no-cache-dir "fastapi==0.165.0" "uvicorn==0.54.0" && useradd --uid 10001 --no-create-home app
COPY server/ server/
USER 10001
EXPOSE 8000
HEALTHCHECK CMD python -c "import urllib.request; urllib.request.urlopen('http://127.0.0.1:8000/healthz')"
CMD ["uvicorn", "server.app:app", "--host", "0.0.0.0", "--port", "8000"]
