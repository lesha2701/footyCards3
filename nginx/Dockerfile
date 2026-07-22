# Build context: repository root (see docker-compose.prod.yml)
FROM node:20-alpine AS frontend-build
WORKDIR /app
COPY frontend/package.json ./
RUN npm install
COPY frontend/ .
ARG VITE_API_URL=/api/v1
ARG VITE_STATIC_URL=/static
ENV VITE_API_URL=$VITE_API_URL
ENV VITE_STATIC_URL=$VITE_STATIC_URL
RUN npm run build

FROM nginx:1.27-alpine
COPY --from=frontend-build /app/dist /usr/share/nginx/html
COPY nginx/nginx.conf /etc/nginx/conf.d/default.conf
EXPOSE 80
