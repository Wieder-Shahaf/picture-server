FROM python:3.11-slim AS builder
RUN apt-get update \
 && apt-get install -y --no-install-recommends libgl1 libglib2.0-0 libxcb1 \
 && rm -rf /var/lib/apt/lists/*
WORKDIR /build
COPY requirements.txt .
RUN pip install --user --no-cache-dir -r requirements.txt
RUN python -c "from ultralytics import YOLO; YOLO('yolov8n-cls.pt')" \
 && mkdir -p /opt/weights \
 && (cp /root/.config/Ultralytics/yolov8n-cls.pt /opt/weights/ 2>/dev/null \
     || cp yolov8n-cls.pt /opt/weights/)

FROM python:3.11-slim
RUN apt-get update \
 && apt-get install -y --no-install-recommends libgl1 libglib2.0-0 \
 && rm -rf /var/lib/apt/lists/*
ENV PATH=/root/.local/bin:$PATH \
    PYTHONUNBUFFERED=1 \
    YOLO_WEIGHTS=/opt/weights/yolov8n-cls.pt \
    DB_PATH=/app/data/app.db
COPY --from=builder /root/.local /root/.local
COPY --from=builder /opt/weights /opt/weights
WORKDIR /app
COPY . .
RUN mkdir -p /app/data
EXPOSE 5000
CMD ["python", "main.py", "--port", "5000"]
