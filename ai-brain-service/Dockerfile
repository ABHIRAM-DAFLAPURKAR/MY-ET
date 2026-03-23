FROM python:3.10-slim-bookworm

WORKDIR /app

# Install system dependencies with retries/mirrors
RUN echo "deb http://mirrors.tuna.tsinghua.edu.cn/debian/ bookworm main contrib non-free non-free-firmware" > /etc/apt/sources.list && \
    echo "deb http://mirrors.tuna.tsinghua.edu.cn/debian/ bookworm-updates main contrib non-free non-free-firmware" >> /etc/apt/sources.list && \
    echo "deb http://mirrors.tuna.tsinghua.edu.cn/debian-security bookworm-security main contrib non-free non-free-firmware" >> /etc/apt/sources.list && \
    apt-get update -o Acquire::Retries=3 -y --fix-missing --allow-releaseinfo-change && \
    apt-get install -y --no-install-recommends gcc g++ make curl ca-certificates && \
    rm -rf /var/lib/apt/lists/* && \
    pip install --no-cache-dir --upgrade pip setuptools wheel

# Copy and install requirements first (cache layer)
COPY requirements.txt .
RUN pip install --no-cache-dir "torch==2.2.2+cpu" "torchvision==0.17.2+cpu" --index-url https://download.pytorch.org/whl/cpu && pip install --index-url https://pypi.tuna.tsinghua.edu.cn/simple --no-cache-dir --retries 10 --timeout 120 -r requirements.txt

# Copy application code
COPY . .

# Optional: Pre-load models if needed (commented to avoid startup failures)
# RUN python -c "from transformers import pipeline; pipeline('text2text-generation', model='google/flan-t5-small')" || true

EXPOSE 5005

# Robust healthcheck
HEALTHCHECK --interval=30s --timeout=10s --start-period=40s --retries=5 \
  CMD curl -f http://localhost:5005/health || wget --no-verbose --tries=1 --spider http://localhost:5005/health || exit 1

CMD ["python", "run.py"]
