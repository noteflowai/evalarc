FROM python@sha256:78387bc3881b8273120a12ebe6c1ab22b018ccc2c9adf565ae1ac9b536e184ea
RUN apt-get update \
    && apt-get install -y --no-install-recommends strace=6.13+ds-1 \
    && rm -rf /var/lib/apt/lists/*
COPY src/evalarc/assets/behavior_candidate.py /opt/observer/behavior_candidate.py
COPY src/evalarc/assets/behavior_service.py /opt/observer/behavior_service.py
COPY src/evalarc/assets/behavior_worker.py /opt/observer/behavior_worker.py
CMD ["python3", "-I", "-B", "/opt/observer/behavior_service.py"]
