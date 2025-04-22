FROM python:3.11-slim

WORKDIR /app

COPY requirements.txt .
RUN apt-get update && apt-get install -y \
    ffmpeg curl \
  && rm -rf /var/lib/apt/lists/*

RUN pip install --no-cache-dir -r requirements.txt

COPY . .

# expose port if needed
EXPOSE 8080

CMD ["gunicorn", "-b", "0.0.0.0:8080", "app:app"]
