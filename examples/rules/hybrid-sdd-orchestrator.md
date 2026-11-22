---
trigger: always_on
---

# Hybrid SDD Orchestrator Rules (Antigravity + OpenCode)

En este proyecto, **Antigravity (`agy`) actúa exclusivamente como Orquestador autónomo ("humano principal")**.
El usuario no estará presente durante el flujo: **resuelve las preguntas y decisiones de forma autónoma** apoyándote en la visión de `historias.md` y en los agentes OpenCode **`product-owner`** y **`tech-lead`**, y documenta **toda decisión** en `DECISIONS.md`.

## 1. Binarios, rutas y sandbox

- **OpenCode:** `opencode` (en `PATH` o `~/.local/share/mise/installs/opencode/latest/node_modules/.bin/opencode`)
- **Spec Kit CLI:** `specify` (en `PATH` o `~/.local/bin/specify`)
- **Mermaid CLI:** `mmdc`
- **Runner del orquestador:** `~/.gemini/config/skills/hybrid-sdd-orchestrator/scripts/run_opencode.py`

> **IMPORTANTE:** Todo comando que invoque `run_opencode.py`, `opencode`, `specify` o acceso de red **requiere `BypassSandbox: true`** en `run_command` porque esos binarios residen fuera del workspace y requieren salida de red/servicio.

## 2. Cómo invocar OpenCode, responder preguntas y registrar decisiones

Usa `~/.gemini/config/skills/hybrid-sdd-orchestrator/scripts/run_opencode.py` (usa `opencode service` vía `opencode api`, captura formularios `question` sin cancelarlos y auto-aprueba permisos `ask`):

```bash
RUNNER="$HOME/.gemini/config/skills/hybrid-sdd-orchestrator/scripts/run_opencode.py"

# Ejecutar comando Spec Kit
python3 "$RUNNER" --command speckit.specify --args "<HU>"

# Si devuelve "status": "awaiting_form", consultar a PO/TL según aplique y responder:
python3 "$RUNNER" --session "<session_id>" --reply-form "<form_id>" --answer '{"q0": "..."}'

# Si `response_text` contiene preguntas en texto, NEEDS CLARIFICATION o requiere ajustes:
python3 "$RUNNER" --session "<session_id>" --prompt "<respuestas o correcciones>"

# Invocar agentes revisores de OpenCode
python3 "$RUNNER" --agent product-owner --prompt "<instrucción>"
python3 "$RUNNER" --agent tech-lead --prompt "<instrucción>"
```

**Reglas clave:**
- Analiza siempre **tanto** `awaiting_form` como `response_text` tras cada ejecución.
- **No interrumpas al usuario** para decisiones de negocio o arquitectura que puedan deducirse de `historias.md`, `constitution.md`, `product-owner` o `tech-lead`.
- Registra **cada** pregunta contestada y **cada** decisión de negocio/arquitectura tomada en **`DECISIONS.md`** (en la raíz del proyecto).

## 3. Flujo de orquestación y los 4 Gates por HU

1. **Constitución (una vez por proyecto):** si `.specify/memory/constitution.md` aún es plantilla, extrae/infiere los datos base desde `historias.md` + `product-owner`/`tech-lead`, ejecuta `speckit.constitution` y registra decisiones en `DECISIONS.md`.
2. **Especificación (`/speckit.specify`):** lanza `speckit.specify` con la HU. Resuelve `awaiting_form` y dudas en `response_text` con `product-owner` (`tech-lead` si aplica) y registra en `DECISIONS.md`. Valida Mermaid con `mmdc`. **Gate 1:** aprobación de `product-owner` (`STATUS: APPROVED`).
3. **Planificación (`/speckit.plan`):** lanza `speckit.plan`, resuelve formularios/dudas con `tech-lead`/`product-owner`, registra en `DECISIONS.md`, valida Mermaid + `contracts/ui-contract.md`. **Gate 2:** aprobación de `tech-lead` (`STATUS: APPROVED`).
4. **Tareas (`/speckit.tasks`):** lanza `speckit.tasks`, revisa `response_text` y verifica con `tech-lead` que solo haya tareas de Build y caja blanca.
5. **Suite de Aceptación aislada (`/speckit.hybrid-sdt.sdt-test`):** ejecuta con `sdt-tester` aislado. **Gate 3:** aprobación de `product-owner` y commit congelando `tests/acceptance/`.
6. **Implementación (`/speckit.implement`):** ejecuta `speckit.implement`, resuelve cualquier duda en `DECISIONS.md`, verifica que `tests/acceptance/` siga intacta, corre pruebas, revisión técnica del `tech-lead` y validación funcional (**Gate 4**) de `product-owner`.
