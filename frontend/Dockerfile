# ---- deps ----
FROM node:20-alpine AS deps
WORKDIR /app
COPY package.json ./
RUN npm install

# ---- dev (used by docker-compose.yml for local development with HMR) ----
FROM deps AS dev
WORKDIR /app
COPY . .
EXPOSE 5173
CMD ["npm", "run", "dev", "--", "--host", "0.0.0.0"]

# ---- build (production static assets, consumed by nginx/Dockerfile) ----
FROM deps AS build
WORKDIR /app
COPY . .
ARG VITE_API_URL=/api/v1
ARG VITE_STATIC_URL=/static
ENV VITE_API_URL=$VITE_API_URL
ENV VITE_STATIC_URL=$VITE_STATIC_URL
RUN npm run build
