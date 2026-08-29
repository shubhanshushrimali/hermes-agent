# BMAD Workflow Integration for Hermes Agent — Aizen Version
# Maps BMAD methodology agents to Hermes Agent project roles
# Reference: c:\Personal\Eisen-Engine\_bmad\config.toml

## Agent-Role Mapping

| BMAD Agent | Hermes Role | Responsibility |
|------------|-------------|----------------|
| Analyst | Requirements Gatherer | Parse user stories, extract acceptance criteria |
| Architect | System Designer | Define module boundaries, API contracts |
| Developer | Code Executor | Implement features, write tests |
| PM | Sprint Manager | Track velocity, manage backlog |
| QA | Test Runner | Execute test suites, report coverage |
| Designer | UI/UX | Apply design tokens, validate accessibility |

## Sprint Structure

### Sprint Cadence: 1-week cycles

```yaml
sprint:
  duration: 7d
  ceremonies:
    - daily: "Status check via /sprint-status"
    - planning: "Monday via /sprint-plan"
    - review: "Friday via /sprint-review"
    - retro: "Friday via /sprint-retro"
```

### Backlog Priority (current)

| Priority | Item | Phase | Story Points |
|----------|------|-------|-------------|
| P0 | Decompose cli.py | Phase 0 | 13 |
| P0 | Decompose gateway/run.py | Phase 0 | 21 |
| P1 | Wire mobile auth to gateway | Phase 2 | 8 |
| P1 | Monaco editor integration | Phase 4 | 13 |
| P2 | Add git submodules | Phase 5 | 5 |
| P2 | Observability dashboard | Phase 7 | 8 |
| P3 | MCP Apps system | Phase 7 | 13 |
| P3 | YAML Recipes | Phase 7 | 8 |

### Definition of Done

- [ ] Code compiles without errors
- [ ] All existing tests pass
- [ ] New code has >80% test coverage
- [ ] No new lint warnings
- [ ] Design tokens used (no hardcoded colors)
- [ ] Accessibility: keyboard navigable, ARIA labels
- [ ] prefers-reduced-motion respected
- [ ] Documentation updated
