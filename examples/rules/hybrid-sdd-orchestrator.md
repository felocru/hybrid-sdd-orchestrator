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

## 3. Ruta completa de orquestación y los 4 Gates por HU

Ejecuta la **ruta completa de producción de Spec Kit + Hybrid SDD** (en OpenCode se instalan como `speckit.<cmd>`, y `run_opencode.py` acepta tanto `speckit.<cmd>` como `speckit-<cmd>`):

1. **Constitución (`speckit.constitution`, una vez por proyecto):** si `.specify/memory/constitution.md` aún es plantilla, extrae/infiere los datos base desde `historias.md` + `product-owner`/`tech-lead`, ejecuta `speckit.constitution` y registra decisiones en `DECISIONS.md`.
2. **Especificación (`speckit.specify`):** lanza `speckit.specify` con la HU, resuelve dudas y registra en `DECISIONS.md`.
3. **Clarificación (`speckit.clarify`):** lanza `speckit.clarify` antes del plan, resuelve todas las preguntas con `product-owner`/`tech-lead` y registra en `DECISIONS.md`. Valida Mermaid con `mmdc`. **Gate 1:** aprobación de `product-owner` (`STATUS: APPROVED`).
4. **Planificación (`speckit.plan`):** lanza `speckit.plan`, resuelve dudas, valida Mermaid + `contracts/ui-contract.md` (+ diseño vía MCP). **Gate 2:** aprobación de `tech-lead` (`STATUS: APPROVED`).
5. **Checklist (`speckit.checklist`):** lanza `speckit.checklist` tras el plan y revisa con `product-owner`/`tech-lead` que no queden requisitos ambiguos antes de tareas.
6. **Tareas (`speckit.tasks`):** lanza `speckit.tasks`, revisa `response_text` y verifica con `tech-lead` que solo haya tareas de Build y caja blanca.
7. **Análisis transversal (`speckit.analyze`):** lanza `speckit.analyze` tras `tasks` y remedia cualquier inconsistencia crítica antes de congelar pruebas o implementar.
8. **Suite de Aceptación aislada (`speckit.hybrid-sdt.sdt-test`):** ejecuta con `sdt-tester` aislado. **Gate 3:** aprobación de `product-owner` y commit congelando `tests/acceptance/`.
9. **Implementación y Convergencia (`speckit.implement` + `speckit.converge`):** ejecuta `speckit.implement`, luego corre `speckit.converge` en bucle junto a `speckit.implement` hasta converger sin tareas pendientes, verifica que `tests/acceptance/` siga intacta, corre pruebas, revisión técnica del `tech-lead` y validación funcional (**Gate 4**) de `product-owner`.
