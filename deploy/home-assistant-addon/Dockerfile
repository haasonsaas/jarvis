ARG BUILD_FROM=ghcr.io/home-assistant/amd64-base-python:3.12
FROM ${BUILD_FROM}

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1

RUN apk add --no-cache bash curl
RUN curl -LsSf https://astral.sh/uv/install.sh | sh
ENV PATH="/root/.local/bin:${PATH}"

WORKDIR /opt/jarvis
COPY . /opt/jarvis
RUN uv sync --frozen --extra dev

CMD ["uv", "run", "python", "-m", "jarvis", "--sim", "--no-vision"]
