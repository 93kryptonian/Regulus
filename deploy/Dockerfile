FROM python:3.12-slim

RUN useradd --system --create-home --uid 10001 regulus
WORKDIR /app
COPY requirements.lock pyproject.toml ./
RUN pip install --no-cache-dir -r requirements.lock
COPY src ./src
RUN pip install --no-cache-dir --no-deps .

ENV REGULUS_STATE_DIR=/var/lib/regulus
RUN mkdir -p /var/lib/regulus && chown regulus /var/lib/regulus
VOLUME /var/lib/regulus
USER regulus

HEALTHCHECK --interval=30s --timeout=5s --start-period=10s --retries=3 \
  CMD ["python", "-c", "import urllib.request as u; u.urlopen('http://127.0.0.1:8765/healthz', timeout=3)"]

ENTRYPOINT ["python", "-m", "regulus"]
CMD ["serve"]
