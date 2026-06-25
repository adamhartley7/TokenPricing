# Optional: run the gateway as a container instead of host uvicorn (keeps it off the host LAN —
# publish only to 127.0.0.1, and let LibreChat reach it over the Docker network). See README.
FROM python:3.13-slim
WORKDIR /app
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt
COPY . .
EXPOSE 8787
CMD ["uvicorn", "app:app", "--host", "0.0.0.0", "--port", "8787"]
