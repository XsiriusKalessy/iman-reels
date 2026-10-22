# Servidor de la IA incluida

La licencia incluye la IA: la app no pide claves. Las peticiones van a `api.imanreels.com`, que comprueba la
licencia y llama a Claude con la clave de Imán. Solo viaja texto (la transcripción), nunca el vídeo.

## Variables

| Variable | Qué es |
|---|---|
| `ANTHROPIC_API_KEY` | Clave de la API de Anthropic de Imán (obligatoria, va como secreto, nunca en el código) |
| `IMAN_LEMON_PRODUCT_ID` | ID del producto en Lemon Squeezy, para no aceptar licencias de otros productos |
| `IMAN_DAILY_LIMIT` | Llamadas al día por licencia (por defecto 40) |
| `IMAN_TRIAL_LIMIT` | Llamadas al día sin licencia, por IP, para la prueba gratis (por defecto 6) |
| `IMAN_CLAUDE_MODEL` | Modelo de Claude (por defecto `claude-opus-5-5`) |

## Desplegarlo

Cualquier servicio que ejecute un contenedor sirve (Fly.io, Railway, Render, Google Cloud Run):

```
docker build -f iman_cloud/Dockerfile -t iman-cloud .
docker run -p 8080:8080 -e ANTHROPIC_API_KEY=... -e IMAN_LEMON_PRODUCT_ID=... iman-cloud
```

Después se apunta `api.imanreels.com` al servicio. `GET /health` responde `{"ok": true}`.

## Coste

Un reel usa una llamada de plan (unos pocos miles de tokens de entrada) y, si se pide, alguna de chat,
texto de publicación o ideas. Con el límite de 40 llamadas al día por licencia, el gasto por usuario
activo queda en céntimos al día; conviene poner un tope de gasto mensual en la consola de Anthropic.

Los contadores de uso están en memoria: con una sola instancia es suficiente para empezar. Si se escala a
varias, hay que moverlos a Redis o a una base de datos.
