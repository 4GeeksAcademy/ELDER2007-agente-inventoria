# Documentación del proyecto: Agente de Inventario

Esta carpeta explica **qué se construyó, qué decisiones se tomaron y por qué**. Está pensada
para alguien que estudia IA engineering y quiere entender el proyecto, no solo usarlo.

## Índice

| Archivo | Qué contiene |
|---|---|
| [01-que-se-construyo.md](01-que-se-construyo.md) | Visión general, mapa de archivos y flujo completo de una petición |
| [02-decisiones-de-diseno.md](02-decisiones-de-diseno.md) | Cada decisión importante: qué se eligió, qué alternativas había y por qué |
| [03-el-bucle-del-agente.md](03-el-bucle-del-agente.md) | El corazón del proyecto: Observar → Pensar → Actuar → Actualizar → Repetir |
| [04-diccionario.md](04-diccionario.md) | Glosario de términos, diccionarios de Python usados y diccionario de datos |
| [05-problemas-y-limitaciones.md](05-problemas-y-limitaciones.md) | Errores que aparecieron, cómo se resolvieron y qué queda pendiente |

## El proyecto en tres frases

1. Una **API REST** (FastAPI) guarda un inventario en un CSV y permite listar, crear, ajustar
   stock y detectar stock bajo.
2. Un **agente de IA** escrito a mano en Python (sin frameworks) usa un LLM de Groq y trata
   esa API como un conjunto de *tools*.
3. Cada evento de la conversación se guarda en otro CSV que solo crece (*append-only*).

## Cómo arrancarlo

Las instrucciones completas están en el [README principal](../README.md). Resumen:

```bash
# Terminal 1: la API (siempre primero)
uvicorn api.app:app --reload

# Terminal 2: el agente (necesita GROQ_API_KEY en .env)
python agent.py
```
