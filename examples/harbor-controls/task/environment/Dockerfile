FROM python:3.12-slim
RUN mkdir /workspace && chown 65534:65534 /workspace
WORKDIR /workspace
COPY --chown=65534:65534 main.py requests.jsonl ./
USER 65534:65534
