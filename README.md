# SimpleSeed

Análisis de RFPs con IA (FastAPI + Next.js).

## Requisitos previos

- Docker + Docker Compose instalados
- Tu `ANTHROPIC_API_KEY`

## Primera vez

```bash
# 1. Crear el .env (solo la primera vez)
make setup

# 2. Editar backend/.env y poner tu API key
#    DATABASE_URL ya viene configurada para Docker
nano backend/.env
```

El `.env` debe tener:

```
ANTHROPIC_API_KEY=sk-ant-...
DATABASE_URL=postgresql+asyncpg://simpleseed:simpleseed@db:5432/simpleseed
LLM_MODEL=claude-haiku-4-5-20251001
```

## Levantar

```bash
make up
```

Esto hace `docker compose up -d --build`. La primera vez tarda ~2-3 min (descarga imágenes, instala deps). Las siguientes veces es mucho más rápido.

Cuando termina, abre: **http://localhost:3000**

## Comandos del día a día

```bash
make up          # levantar (rebuild automático si hay cambios)
make down        # apagar
make logs        # ver todos los logs en vivo
make logs s=api  # solo logs del backend
make logs s=web  # solo logs del frontend
make shell-api   # shell dentro del contenedor API
```

## Flujo al hacer cambios en el código

```bash
make down && make up   # rebuild completo
# o más rápido:
docker compose up -d --build api   # solo rebuilds el backend
docker compose up -d --build web   # solo rebuilds el frontend
```

## Troubleshooting

**El frontend no conecta con el API:**
- El `web` espera a que `api` pase su healthcheck (`GET /health`)
- Revisa: `make logs s=api`

**Error de DB al iniciar:**
- La DB tarda unos segundos en estar lista; el compose ya tiene `service_healthy` como condición
- Si persiste: `docker compose down -v && make up` (borra el volumen de postgres)

**Ver el estado de los contenedores:**
```bash
docker compose ps
```
