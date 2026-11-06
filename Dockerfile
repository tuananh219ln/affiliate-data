# The Playwright image ships Chromium and its system libraries; its version must match the
# playwright pin in pyproject.toml.
FROM mcr.microsoft.com/playwright/python:v1.55.0-noble

WORKDIR /app
COPY pyproject.toml alembic.ini ./
COPY src ./src
COPY migrations ./migrations
RUN pip install --no-cache-dir .

ENV DATA_DIR=/data
VOLUME /data
EXPOSE 8000

# `api` by default; the worker service runs the same image with `worker`.
ENTRYPOINT ["python", "-m", "affiliate_data"]
CMD ["api"]
