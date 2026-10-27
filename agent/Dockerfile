# Heliox GPU agent image. Run with the NVIDIA container runtime so NVML can see the GPUs.
FROM python:3.11-slim

RUN useradd --uid 10001 --no-create-home --shell /usr/sbin/nologin heliox

WORKDIR /agent
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt
COPY heliox_agent.py .

# Ask the NVIDIA runtime for driver utilities (NVML) on every GPU, without claiming a GPU resource
ENV NVIDIA_VISIBLE_DEVICES=all \
    NVIDIA_DRIVER_CAPABILITIES=utility \
    PYTHONUNBUFFERED=1

USER 10001
ENTRYPOINT ["python", "/agent/heliox_agent.py"]
