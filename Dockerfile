FROM python:3.12-slim

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1

WORKDIR /app

COPY requirements.txt ./
RUN pip install --no-cache-dir --upgrade pip \
    && pip install --no-cache-dir -r requirements.txt

COPY . .
RUN mkdir -p /app/tracking/job-radar/runs /app/tracking/job-radar/profile /app/entregables

EXPOSE 8766

CMD ["uvicorn", "job_radar_app.api:app", "--host", "0.0.0.0", "--port", "8766"]
