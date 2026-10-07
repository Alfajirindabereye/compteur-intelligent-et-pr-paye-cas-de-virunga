FROM node:22-slim

RUN apt-get update && apt-get install -y --no-install-recommends python3 python3-venv python3-pip build-essential default-libmysqlclient-dev pkg-config && rm -rf /var/lib/apt/lists/*

WORKDIR /app
COPY . .

RUN npm install -g corepack@latest && corepack pnpm install && corepack pnpm run build
RUN python3 -m venv /opt/venv && /opt/venv/bin/pip install --no-cache-dir --upgrade pip && /opt/venv/bin/pip install --no-cache-dir -r backend/requirements.txt

ENV NODE_ENV=production
ENV PYTHONUNBUFFERED=1
ENV DJANGO_SETTINGS_MODULE=config.settings

WORKDIR /app/backend
CMD ["sh", "-c", "/opt/venv/bin/python manage.py migrate --noinput && exec /opt/venv/bin/daphne -b 0.0.0.0 -p ${PORT:-3000} config.asgi:application"]
