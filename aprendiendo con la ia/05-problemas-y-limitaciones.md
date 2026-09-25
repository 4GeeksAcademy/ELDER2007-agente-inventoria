# 5. Problemas encontrados y limitaciones

Un proyecto real nunca sale a la primera. Esto es lo que falló durante el desarrollo, cómo se
detectó y qué queda pendiente. **Saber qué no funciona es parte de la ingeniería.**

## Problemas que aparecieron y cómo se resolvieron

### 1. Mensajes de error con comillas de más
- **Síntoma:** al ajustar el stock de un producto inexistente, el mensaje era
  `"\"Producto 'x' no encontrado\""`.
- **Causa:** en Python, `str(KeyError("texto"))` devuelve el texto **con comillas**.
- **Cómo se detectó:** probando a mano cada caso de error con `curl`.
- **Solución:** excepciones propias (`ProductNotFoundError`, etc.).
- **Lección:** no reutilices excepciones estándar para errores de tu dominio.

### 2. "El modelo no existe" (error 404 de Groq)
- **Síntoma:** el agente respondía "Tuve un problema hablando con la API o el modelo".
- **Causa:** el modelo por defecto no estaba disponible para la cuenta.
- **Cómo se detectó:** el agente mostraba el error real de Groq; se listaron los modelos
  disponibles con la clave y se eligió otro.
- **Lección:** ni los nombres de modelos ni su disponibilidad son estables. Hazlos
  configurables.

### 3. La API se cayó sola en segundo plano
- **Síntoma:** al ir a ejecutar el agente, `/health` no respondía.
- **Causa:** no se determinó. El proceso arrancado en segundo plano dejó de existir.
- **Solución:** se relanzó. **Esto no debería pasar en tu uso normal**, porque arrancarás la
  API tú en una terminal visible; allí verías el error si ocurriera.

### 4. Pruebas que fallaban por culpa del propio script
- Un test devolvía `HTTP 000` porque el servidor aún no había terminado de arrancar. Otro
  fallaba al importar porque estaba en otra carpeta. **No eran fallos del proyecto**, sino de
  los scripts de prueba; se corrigieron esperando a `/health` y ejecutando desde la raíz.
- **Lección:** cuando una prueba falla, comprueba primero si el fallo es de la prueba.

## Limitaciones actuales (honestas)

| Limitación | Detalle |
|---|---|
| **Sin validar la unidad** | Al decir "vendimos 12 bolsas", el agente elige un producto por nombre; la API no comprueba que "bolsas" coincida con la unidad del producto. |
| **El LLM puede equivocarse** | Es no determinista. En una prueba real llamó "Café arábica (1 kg)" a un producto que se llama "Bolsas de arábica 1kg". El stock que cambió fue el correcto, pero el texto no. |
| **Búsqueda por nombre aproximada** | `buscar_producto("arábica")` devuelve varios productos; el LLM elige. Con nombres ambiguos podría elegir mal. |
| **Sin editar ni borrar productos** | Solo se pueden crear y ajustar. Un producto creado por error no se puede eliminar desde la API. |
| **Sin autenticación** | Cualquiera que llegue a la API puede modificar el inventario. Vale para uso local. |
| **CSV y concurrencia** | El candado sirve para un solo proceso. Con varios *workers* habría que usar una base de datos. |
| **Sin memoria entre sesiones** | Al reiniciar el agente, el LLM olvida la conversación (solo queda el log). |
| **Idioma del prompt** | Las respuestas del agente usan voseo (*"tenés"*, *"podés"*), porque así se redactó el prompt. Se cambia editando `SYSTEM_PROMPT` en `agent.py`. |
| **Rutas duplicadas** | `/inventory` y `/products` hacen cosas iguales en parte (ver decisión A6). |
| **Sin tests automáticos** | Las comprobaciones se hicieron con scripts manuales, no hay una suite de tests en el repositorio. |
| **Cambios sin confirmar en git** | Tras el primer commit ("agente inventario") se hicieron más cambios (redirección de `/`, búsqueda con erratas, esta carpeta) que aún no están confirmados. |

## Ideas para seguir aprendiendo

1. **Escribe tests automáticos** con `pytest` y el `TestClient` de FastAPI para los
   endpoints. Es la mejora que más valor aporta.
2. **Cambia el CSV por SQLite** y observa qué partes de `storage.py` cambian y cuáles no
   (la API no debería notar la diferencia; eso es buena separación de capas).
3. **Añade una tool nueva**, por ejemplo `eliminar_producto`: endpoint, esquema, función y una
   línea en el diccionario. Comprobarás lo poco que hay que tocar.
4. **Valida las unidades** en la API para cerrar la limitación más importante.
5. **Prueba otro modelo** con `GROQ_MODEL` y compara cuántas veces elige bien las tools.
6. **Mide el coste:** el historial completo se reenvía en cada vuelta. ¿Cómo crece el número
   de *tokens* con una conversación larga? Investiga cómo recortar el historial.
