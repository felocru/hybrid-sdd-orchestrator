---
name: hybrid-sdd-orchestrator
description: >-
  Orquesta de forma autónoma el flujo completo de Hybrid SDD (Spec Kit +
  OpenCode) actuando como Orquestador ("humano principal"), delegando comandos
  Spec Kit y revisiones de Product Owner (product-owner) y Tech Lead
  (tech-lead) a OpenCode, respondiendo formularios y preguntas sin interrumpir
  al usuario y registrando todas las decisiones en DECISIONS.md. Úsese cuando
  el usuario pida orquestar un proyecto con Spec Kit, OpenCode, hybrid-sdd o
  procesar un archivo de historias/HUs (ej. historias.md).
---

# Hybrid SDD Orchestrator (Antigravity + OpenCode)

En este flujo, **tú (`agy`) eres exclusivamente el Orquestador autónomo ("humano principal")**.
El usuario **no estará disponible** durante la ejecución: **NO le delegues preguntas ni te detengas a pedir aprobaciones intermedias** salvo ante un bloqueo técnico/externo irrecuperable (como falta de credenciales, servicio caído o ausencia del archivo de historias).

Todo el trabajo de generación (Spec Kit) y revisión especializada (**Product Owner** y **Tech Lead**) corre en **OpenCode** usando la suscripción y los MCPs del usuario.

---

## 1. Rutas y regla de Sandbox (CRÍTICO)

- **OpenCode CLI:** `opencode` (en `PATH`, `~/.local/share/mise/installs/opencode/latest/node_modules/.bin/opencode` o `~/.opencode/bin/opencode`)
- **Spec Kit CLI:** `specify` (en `PATH` o `~/.local/bin/specify`)
- **Mermaid CLI:** `mmdc`
- **Runner portable:** [run_opencode.py](./scripts/run_opencode.py) (o `~/.gemini/config/skills/hybrid-sdd-orchestrator/scripts/run_opencode.py`)

> **IMPORTANTE:** Todo `run_command` que invoque `run_opencode.py`, `opencode`, `specify` o requiera red **DEBE usar `BypassSandbox: true`**, porque esos binarios residen fuera del workspace y conectan con el servidor/red.

---

## 2. Preflight y Auto-Bootstrap del proyecto (Paso 0)

Al iniciar en cualquier proyecto, verifica antes de procesar HUs:

1. **¿Existe Spec Kit + `hybrid-sdd`?**
   - Comprueba `.specify/` y `.opencode/commands/speckit.specify.md`.
   - Si no existen, inicializa el proyecto (con `BypassSandbox: true`, usando `specify` o `~/.local/bin/specify`):
     ```bash
     specify init --here --non-interactive --integration opencode && \
     specify preset catalog add https://raw.githubusercontent.com/felocru/hybrid-sdd/main/catalog/presets.json --name hybrid-catalog --install-allowed && \
     specify extension catalog add https://raw.githubusercontent.com/felocru/hybrid-sdd/main/catalog/extensions.json --name hybrid-catalog --install-allowed && \
     specify bundle catalog add https://raw.githubusercontent.com/felocru/hybrid-sdd/main/catalog/bundles.json --policy install-allowed --id hybrid-catalog && \
     specify bundle install hybrid-sdd
     ```
2. **¿Existen los agentes de OpenCode en `.opencode/agents/`?**
   - Verifica `.opencode/agents/product-owner.md` y `.opencode/agents/tech-lead.md`. Si alguno falta, cópialo desde [product-owner.md](./resources/agents/product-owner.md) y [tech-lead.md](./resources/agents/tech-lead.md) dentro de `.opencode/agents/`.
   - Verifica `.opencode/agents/sdt-tester.md`. Si falta, ejecuta `speckit.hybrid-sdt.setup` con `run_opencode.py`.
3. **¿Existe Git?**
   - Si el proyecto aún no tiene `.git/` y vas a usar ramas de Spec Kit o worktrees en paralelo, inicializa Git (`git init`) y realiza un commit base si está vacío para que los scripts de ramas/worktrees funcionen sin fricción.
4. **Bitácora de decisiones (`DECISIONS.md`):**
   - Si no existe `DECISIONS.md` en la raíz del proyecto, créalo al inicio para registrar **todas** las decisiones tomadas durante la orquestación.

---

## 3. Cómo invocar OpenCode, analizar respuestas y decidir sin el usuario

Usa siempre [run_opencode.py](./scripts/run_opencode.py). Por defecto utiliza el servidor de fondo (`opencode service`) vía `opencode api`, **preservando formularios dinámicos (`question`)** y auto-aprobando permisos `ask`:

```bash
RUNNER="$HOME/.gemini/config/skills/hybrid-sdd-orchestrator/scripts/run_opencode.py"

# 1. Ejecutar comando Spec Kit en OpenCode
python3 "$RUNNER" --project . --command speckit.specify --args "<HU>"

# 2. Responder un formulario dinámico (`status == "awaiting_form"`)
python3 "$RUNNER" --project . --session "<session_id>" --reply-form "<form_id>" --answer '{"q0": "<valor>"}'

# 3. Continuar sesión si `response_text` trajo preguntas en texto o requiere ajustes
python3 "$RUNNER" --project . --session "<session_id>" --prompt "<respuestas o correcciones>"

# 4. Consultar a los agentes revisores en OpenCode
python3 "$RUNNER" --project . --agent product-owner --prompt "<contexto + pregunta o revisión>"
python3 "$RUNNER" --project . --agent tech-lead --prompt "<contexto + pregunta o revisión>"
```

### Regla de análisis de cada ejecución de OpenCode

Al terminar **cada** llamada a `run_opencode.py`, analiza **ambos** canales de salida:

1. **Si `status == "awaiting_form"` (preguntas interactivas en formulario):**
   - Lee `form.fields` (`key`, `title`, `description`, `options`, `type`).
   - Toma una decisión alineada con la visión, objetivos y restricciones de `historias.md` (y `constitution.md` si ya existe), consultando a:
     - `--agent product-owner` para preguntas de negocio, alcance, prioridad o reglas funcionales.
     - `--agent tech-lead` para preguntas de arquitectura, stack, modelado o contratos.
   - Responde con `--reply-form` y **registra la decisión en `DECISIONS.md`**.
2. **Si `status == "completed"` (respuesta en texto `response_text`):**
   - **Nunca ignores `response_text`**: algunos comandos no abren formulario, sino que devuelven preguntas en texto, puntos marcados como `NEEDS CLARIFICATION`, supuestos o advertencias.
   - Si `response_text` contiene preguntas abiertas o puntos por decidir: resuélvelos con `historias.md` + `product-owner`/`tech-lead`, continúa la misma sesión (`--session <session_id> --prompt "<respuestas>"`) hasta cerrar el artefacto completo y **regístralo en `DECISIONS.md`**.
   - Si `response_text` declara supuestos que contradicen `historias.md` o `constitution.md`: corrígelos en la misma sesión y **regístralo en `DECISIONS.md`**.

---

## 4. Registro obligatorio en `DECISIONS.md`

Cada vez que respondas preguntas de OpenCode (`awaiting_form` o `response_text`) o tomes una decisión de negocio/arquitectura durante la revisión de artefactos o resolución de Gates, añade una entrada en `DECISIONS.md` (en la raíz del proyecto):

```markdown
## DEC-NNN — <Título corto de la decisión>
- **Fecha:** YYYY-MM-DD HH:MM
- **HU / Feature:** <ID y nombre>
- **Fase / Origen:** <Constitution | Specify | Clarify | Plan | Tasks | SDT | Implement> (`awaiting_form` | `response_text` | `Gate Review`)
- **Pregunta / Dilema:** <qué preguntó OpenCode o qué ambigüedad/conflicto se detectó>
- **Opciones evaluadas:** <opciones presentadas o alternativas consideradas>
- **Consultas realizadas:** <resumen breve del criterio de `product-owner` y/o `tech-lead`>
- **Decisión tomada:** <respuesta exacta enviada u opción elegida>
- **Justificación (visión de `historias.md`):** <por qué encaja con el objetivo del proyecto>
- **Artefactos afectados:** <archivos o secciones impactadas>
```

---

## 5. Procesamiento de `historias.md` y los 4 Gates por HU

1. Lee `historias.md` completo para interiorizar la **visión del producto, alcance, restricciones y lista de HUs**.
2. Si `.specify/memory/constitution.md` aún es plantilla (`[PROJECT_NAME]`):
   - Extrae nombre, alcance, stack y BD desde `historias.md` (y si algún dato técnico falta, consúltalo con `tech-lead` + `product-owner` alineado a la visión de `historias.md`, dejando constancia en `DECISIONS.md`).
   - Ejecuta `--command speckit.constitution` una sola vez (resolviendo cualquier `awaiting_form` o pregunta en texto de forma autónoma y registrándolo en `DECISIONS.md`).
3. Procesa cada HU (secuencialmente o en `git worktree` paralelos si son independientes) ejecutando **la ruta completa de producción de Spec Kit + Hybrid SDD** (nota: en OpenCode los comandos instalados en `.opencode/commands/` usan punto, p. ej. `speckit.clarify`, aunque `run_opencode.py` también acepta `speckit-clarify`):

### Ruta completa por cada HU (9 comandos + `hybrid-sdt` + 4 Gates)

1. **Especificación (`speckit.specify`):**
   - Lanza `--command speckit.specify --args "<HU>"`.
   - Resuelve `awaiting_form` y dudas en `response_text` con `product-owner` (y `tech-lead` si aplica), registrando en `DECISIONS.md`.

2. **Clarificación (`speckit.clarify` — puerta previa al plan):**
   - Lanza `--command speckit.clarify`.
   - Responde de forma autónoma todas las preguntas de clarificación (`awaiting_form` o `response_text`) consultando a `product-owner` (negocio/alcance) y `tech-lead` (impacto técnico) según la visión de `historias.md`, hasta consolidar las respuestas en `spec.md`. Registra cada respuesta en `DECISIONS.md`.
   - Valida los diagramas Mermaid de `spec.md` con `mmdc`.
   - **Gate 1:** envía `spec.md` + HU a `--agent product-owner`. Re-itera en OpenCode hasta recibir `STATUS: APPROVED`.

3. **Planificación (`speckit.plan`):**
   - Lanza `--command speckit.plan`.
   - Resuelve `awaiting_form` y dudas en `response_text` con `tech-lead` / `product-owner` y registra en `DECISIONS.md`.
   - Valida Mermaid (`C4Component`, `sequenceDiagram`, `classDiagram`, `erDiagram`) con `mmdc` y verifica `contracts/ui-contract.md` (+ diseño vía MCP y snapshot en `design/` si hay UI).
   - **Gate 2:** envía `plan.md`, `data-model.md` y `contracts/` a `--agent tech-lead`. Re-itera hasta `STATUS: APPROVED`, registrando decisiones de arquitectura en `DECISIONS.md`.

4. **Checklist de requisitos (`speckit.checklist` — puerta de calidad de especificación/plan):**
   - Lanza `--command speckit.checklist` (enfocado al dominio relevante de la HU: UX, seguridad, API, datos, etc.).
   - Revisa la checklist generada junto con `product-owner` / `tech-lead` para detectar requisitos ambiguos o incompletos antes de generar tareas; si falta algo crítico, corrige `spec.md`/`plan.md` y regístralo en `DECISIONS.md`.

5. **Tareas (`speckit.tasks`):**
   - Lanza `--command speckit.tasks` y analiza `response_text`.
   - Valida con `--agent tech-lead` que `tasks.md` contenga únicamente tareas de Build y caja blanca (sin tareas de aceptación) y mantenga la precondición de aceptación congelada.

6. **Análisis transversal (`speckit.analyze` — puerta previa a implementación):**
   - Lanza `--command speckit.analyze` (solo lectura entre `constitution.md`, `spec.md`, `plan.md` y `tasks.md`).
   - Revisa el reporte completo: si existen hallazgos `CRITICAL` o inconsistencias frente a la constitución/contratos/tareas, resuélvelos con `tech-lead` y `product-owner`, aplica la remediación en el artefacto correspondiente vía OpenCode, documenta el ajuste en `DECISIONS.md` y vuelve a verificar consistencia.

7. **Suite de Aceptación aislada (`speckit.hybrid-sdt.sdt-test`) + Gate 3:**
   - Lanza `--command speckit.hybrid-sdt.sdt-test` (usa `sdt-tester` en contexto aislado).
   - **Gate 3:** envía `tests/acceptance/README.md` y `tests/acceptance/` a `--agent product-owner` para confirmar trazabilidad 100% de los `CA-n`.
   - **Congela la suite** con un commit dedicado en `tests/acceptance/` antes de implementar.

8. **Implementación (`speckit.implement`):**
   - Lanza `--command speckit.implement`, resolviendo cualquier `awaiting_form` o pregunta en `response_text` vía `tech-lead`/`product-owner` y registrando decisiones en `DECISIONS.md`.
   - Verifica con `git diff` que `tests/acceptance/` no fue modificada.

9. **Bucle de Convergencia (`speckit.converge` ↔ `speckit.implement`):**
   - Lanza `--command speckit.converge` para auditar el código real frente a `spec.md`, `plan.md` y `tasks.md`.
   - Si `speckit.converge` detecta brechas y añade tareas en `## Phase N: Convergence` dentro de `tasks.md`, documenta la brecha en `DECISIONS.md`, ejecuta nuevamente `--command speckit.implement` y vuelve a correr `--command speckit.converge` en bucle hasta que reporte convergencia total (`tasks.md` sin tareas pendientes nuevas).
   - Verifica nuevamente con `git diff` que `tests/acceptance/` siga intacta, corre pruebas de caja blanca y aceptación, y solicita auditoría técnica final a `--agent tech-lead` y validación funcional (**Gate 4**) a `--agent product-owner`.

10. Al finalizar todas las HUs, entrega al usuario un resumen ejecutivo con enlaces a los artefactos generados, el estado de los tests y un enlace directo a `DECISIONS.md`.
