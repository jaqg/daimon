---
status: Seed
type: Decision
subject: [test-project]
---

# Open Questions — Test Project

## [CLOSED] Which splitting strategy to use for train/val/test? (resolved 2026-05-22) → Bemis-Murcko scaffold-aware split. Random split invalid due to 15% near-duplicate leak risk.
Random split may leak conformers. Need to evaluate scaffold-aware vs diversity-based splitting.
