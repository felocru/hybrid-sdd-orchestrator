# Hybrid SDD Orchestrator (Antigravity + OpenCode)

Skill global para **Google Antigravity (`agy`)** que convierte a Antigravity en el **Orquestador autónomo ("humano principal")** sobre proyectos que usan **[GitHub Spec Kit](https://github.com/github/spec-kit)** + **[Hybrid SDD](https://github.com/felocru/hybrid-sdd)** ejecutado en **OpenCode**.

## Cómo funciona la arquitectura

* **Antigravity (`agy`) = Orquestador autónomo:** lee `historias.md`, controla el avance por cada HU, valida diagramas Mermaid con `mmdc`, gestiona Git/worktrees, responde formularios y preguntas sin interrumpir al usuario y registra cada decisión en `DECISIONS.md`.
* **OpenCode = Motor de ejecución y revisión:**
  * Ejecuta la **ruta completa de producción** de Spec Kit (`speckit.constitution`, `speckit.specify`, `speckit.clarify`, `speckit.plan`, `speckit.checklist`, `speckit.tasks`, `speckit.analyze`, `speckit.hybrid-sdt.sdt-test`, `speckit.implement` y el bucle `speckit.converge`), incluyendo el uso de tus **MCPs** conectados en OpenCode.
  * Ejecuta los subagentes especialistas en modo solo lectura:
    * **`product-owner`** (Gates 1, 3 y 4 + clarificaciones de negocio).
    * **`tech-lead`** (Gate 2 + revisión de `tasks.md` y auditoría técnica).
    * **`sdt-tester`** (suite de aceptación aislada de `hybrid-sdt`).
* **Comunicación interactiva real:** [scripts/run_opencode.py](./scripts/run_opencode.py) utiliza `opencode service` (`opencode api`) para capturar formularios dinámicos (`question` -> `session.form.list`) sin cancelarlos, permitiendo que el Orquestador los resuelva con `product-owner`/`tech-lead` y responda vía `session.form.reply`.

## Estructura

```text
hybrid-sdd-orchestrator/
├── SKILL.md                         # Instrucciones principales del skill para agy
├── scripts/
│   └── run_opencode.py              # Runner headless/interactivo sobre opencode api
├── resources/
│   └── agents/
│       ├── product-owner.md         # Agente PO para OpenCode (.opencode/agents/)
│       └── tech-lead.md             # Agente Tech Lead para OpenCode (.opencode/agents/)
└── examples/
    └── rules/
        └── hybrid-sdd-orchestrator.md  # Regla opcional always_on por proyecto (.agents/rules/)
```

## Requisitos

* **Antigravity CLI (`agy`)**
* **OpenCode** (`v2.3.2+`, con `opencode service` disponible)
* **Spec Kit CLI (`specify`)** (`>= 1.2.3`) y bundle `hybrid-sdd`
* **Mermaid CLI (`mmdc`)** (`>= 12`) y **Python 3.10+**

## Instalación global en Antigravity

Clona este repositorio dentro de tu carpeta global de skills de Antigravity:

```bash
git clone https://github.com/felocru/hybrid-sdd-orchestrator.git ~/.gemini/config/skills/hybrid-sdd-orchestrator
chmod +x ~/.gemini/config/skills/hybrid-sdd-orchestrator/scripts/run_opencode.py
```

*(Opcional)* Si quieres fijar el rol de orquestador de forma permanente en un proyecto concreto sin mencionarlo en cada sesión, copia [examples/rules/hybrid-sdd-orchestrator.md](./examples/rules/hybrid-sdd-orchestrator.md) a `<tu-proyecto>/.agents/rules/hybrid-sdd-orchestrator.md`.

## Uso recomendado (modo autónomo largo)

1. Abre `agy` en la raíz de tu proyecto (si va a correr de largo sin supervisión, usa `--dangerously-skip-permissions`):
   ```bash
   agy --dangerously-skip-permissions
   ```
2. Lanza la orquestación con `/goal`:
   ```text
   /goal Usa el skill hybrid-sdd-orchestrator.
   Eres el Orquestador autónomo ("humano principal") de este proyecto usando Hybrid SDD (Spec Kit + OpenCode).
   No estaré disponible durante la ejecución: toma todas las decisiones necesarias basándote en la visión y objetivo de historias.md y consultando a los agentes product-owner y tech-lead de OpenCode.
   Documenta en DECISIONS.md cada pregunta contestada (formularios o texto) y cada decisión de negocio o arquitectura tomada al revisar artefactos.

   Archivo de historias: historias.md
   1. Verifica/inicializa el proyecto (Spec Kit, hybrid-sdd, agentes PO/TL/sdt-tester y Git si falta).
   2. Si la constitución sigue siendo plantilla, extrae/define los datos base desde historias.md + PO/TL, ejecuta speckit.constitution y registra las decisiones en DECISIONS.md.
   3. Procesa todas las HUs cumpliendo los 4 Gates hasta terminar, y al final preséntame el resumen con enlace a DECISIONS.md.
   ```
