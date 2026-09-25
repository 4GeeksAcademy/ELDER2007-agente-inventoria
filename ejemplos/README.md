# Ejemplo de registro

`conversation_log.ejemplo.csv` es el registro real de una sesión de 8 frases con el agente
(LLM de Groq, API aislada con el catálogo inicial). Se incluye como muestra porque el
`data/conversation_log.csv` de verdad está en `.gitignore`.

Columnas: `actor, message, tool_call, timestamp`. Cada frase del usuario produce una secuencia:
`user` → `assistant` (pide una tool) → `tool` (resultado de la API) → … → `assistant` (respuesta final).
