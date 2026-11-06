<!--
Mojt Linux
Copyright (C) 2026 Jonas Persson
SPDX-License-Identifier: GPL-2.0-only
-->

# Distribution contract: first consistency review

2026-11-01, against draft 1 in PR #35 at `3021ff0`. This is a documentation
review/proposal, not runtime acceptance or independent reviewer approval.
The owner approved continuing specification work; public MBT syntax and wire
formats remain discussion items. Draft 2 records the following fixes.

| Finding | Consequence of draft 1 | Draft 2 disposition |
| --- | --- | --- |
| "State changed since approval" was too broad | Normal writes before boot could block every update | Revalidate schema/owner/action preconditions; exact snapshots only when explicitly required |
| Schema wording could cover every user file | Arbitrary Ports could require home-data schemas | Gate declared managed state; show unmanaged-data limits without pretending to inspect/restore it |
| Retained previous content appeared permanently compatible | Later data changes could invalidate recovery | Recheck compatibility on select/start; M1 refuses transitions that break its recovery choice |
| Initial actions were only examples | An implementation could accept arbitrary executables | Recommend a closed System-owned set, fixed phases/scopes and postcondition-based evidence |
| MBT had no concrete interface | Several incompatible command families remained possible | Propose four objects and a worked journey, without treating syntax as approved |
| Failed initialization could be read as stopping everything | An optional service failure could remove diagnostics | Gate dependents via a graph; retain independent authenticated diagnostics and degraded readiness |

## Proposed decisions ready for discussion

| Gate | Recommendation | Status |
| --- | --- | --- |
| D1 | `mbt env/build/package/bootstrap <action>`, optional builder System delivery; separate build/package/install/select | Concrete CLI/behavior proposal; not adopted |
| D3 | Closed initial handlers for derived output and minimal accounts/directories/missing defaults | Initial scope proposed; schema/handler versions still to specify |
| D4 | Managed-state compatibility, preserved local data/config, effect evidence separate from selection | Behavior clarified; durable record schema/protocol still to specify |
| D5 | Editable inputs, resolved exact execution inventory and result receipts are separate | Workflow proposal; recipe/lock/provenance formats still to specify |

Do not mark these gates closed just because behavior paragraphs exist. D2
identity/storage/System composition and D3/D4 action/state/evidence formats are
the next detailed specifications. D6 destructive migrations stay disabled for
M1. D7/D8 remain rollout gates; D9/D10 bound advanced policy/reconciliation.

## Focused validation for implementation

1. Compatible data records may change between plan and boot; a relevant required
   schema/ownership change blocks before mutation.
2. An unmanaged-data Port can install without schema inference; a declared
   required migration with no supported handler cannot select.
3. Conflicting accounts/directories/defaults are preserved and reported;
   recursive repair/reset never happens implicitly.
4. Interrupted effects distinguish selected/running from ready; retry checks
   actual postconditions and a stale marker cannot hide changed inputs.
5. Previous content is retained but refused if current managed state makes it
   incompatible; offline diagnostics remain possible.
6. MBT plans execute no recipe/import; builds do not install; packaging does
   not select; bootstrap cannot treat an existing installation as empty.

No extra manual VM round is needed for this text review. Existing AC and gap
IDs are preserved. These scenarios become tests when the mechanism exists;
no runtime result is claimed by this review.
