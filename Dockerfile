FROM python:3.12-slim
ENV PYTHONDONTWRITEBYTECODE=1 PYTHONUNBUFFERED=1
RUN apt-get update && apt-get install -y --no-install-recommends ffmpeg && rm -rf /var/lib/apt/lists/*
WORKDIR /app
COPY clipforge ./clipforge
COPY requirements.txt ./
RUN useradd -r -u 10001 cliprunner && mkdir /app/data && chown cliprunner:cliprunner /app/data
USER cliprunner
ENV HOST=0.0.0.0 PORT=8000 CLIPS_DATA_DIR=/app/data
EXPOSE 8000
CMD ["python", "-m", "clipforge.web"]
