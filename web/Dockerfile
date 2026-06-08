FROM python:3.11-slim AS builder
RUN apt-get update \
 && apt-get install -y --no-install-recommends libgl1 libglib2.0-0 libxcb1 \
 && rm -rf /var/lib/apt/lists/*
WORKDIR /build
COPY requirements.txt .
# Install CPU-only torch/torchvision FIRST. ultralytics pulls torch in
# transitively, and the default PyPI wheels bundle the full CUDA/nvidia stack
# (~2.5 GB) we never use — this container has no GPU. Pre-installing the CPU
# wheels satisfies ultralytics' dependency, so the line below won't re-resolve
# torch to the CUDA build.
RUN pip install --user --no-cache-dir \
      --index-url https://download.pytorch.org/whl/cpu \
      torch torchvision
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
    YOLO_AUTOINSTALL=false \
    YOLO_WEIGHTS=/opt/weights/yolov8n-cls.pt \
    DB_PATH=/app/data/app.db
COPY --from=builder /root/.local /root/.local
COPY --from=builder /opt/weights /opt/weights
WORKDIR /app
COPY . .
RUN mkdir -p /app/data
EXPOSE 5000
CMD ["python", "main.py", "--port", "5000"]
