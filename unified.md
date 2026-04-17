## Plan: Replace set_active_connection with iris.runtime

Remove `set_active_connection()` / `get_active_connection()` entirely and replace them with an explicit `iris.runtime` namespace that owns runtime detection, backend selection, and active handles. The public contract becomes context-first instead of connection-slot-first. This is a breaking change by design, but it aligns the library with the actual model you want: one unified library, multiple runtime states, and distinct handles for object API and DB-API.

**Proposed public API**
- `iris.runtime.get()` -> return the current runtime context object
- `iris.runtime.configure(mode="auto" | "embedded" | "native", install_dir=None, iris=None, dbapi=None, native_connection=None)` -> replace ad hoc globals with one explicit configuration entrypoint
- `iris.runtime.reset()` -> clear explicit overrides and return to auto-detection
- `iris.runtime.state` -> detected state: `embedded-kernel`, `embedded-local`, `native-remote`, or `unavailable`
- `iris.runtime.mode` -> selected policy: `auto`, `embedded`, or `native`
- `iris.runtime.embedded_available` -> whether embedded backend can be used
- `iris.runtime.iris` -> active native object API handle, if any
- `iris.runtime.dbapi` -> optional explicitly bound native DB-API connection, if any; `iris.dbapi.connect()` remains standalone unless the user binds it into runtime

**Usage shape**
- Embedded kernel: no configuration required; `iris.runtime.state` resolves to `embedded-kernel`
- Embedded local shell: `iris.runtime.configure(mode="embedded", install_dir="...")` or `mode="auto"` with environment variables already set
- Native remote object API: create `conn`, then `db = iris.createIRIS(conn)`, then `iris.runtime.configure(mode="native", iris=db, native_connection=conn)`
- Native remote DB-API: `conn = iris.dbapi.connect(...)` stays independent by default; bind it into runtime only when you explicitly want runtime-managed DB-API routing via `iris.runtime.configure(mode="native", dbapi=conn)`

**Steps**
1. Phase 1: Public API redesign
Define `iris.runtime` as the single public entrypoint for runtime selection and active handles. Remove `set_active_connection()` and `get_active_connection()` from the stubs, exports, demos, and tests. The new top-level story is that users configure a runtime context, not a single active connection slot.
2. Phase 1: Internal context object
Implement an internal `RuntimeContext` type in `iris_utils` with fields for `mode`, `state`, `install_dir`, `embedded_available`, `iris`, `dbapi`, and optional `native_connection`. `mode` expresses policy (`auto | embedded | native`), while `state` expresses what was actually detected or bound (`embedded-kernel | embedded-local | native-remote | unavailable`).
3. Phase 1: Detection helpers
Extract the embedded detection logic from [_iris_ep/__init__.py](/Users/grongier/git/iris-embedded-python-wrapper/_iris_ep/__init__.py) into dedicated helpers used by the context object. Detection should distinguish kernel embedded (`sys._embedded`), local embedded (install dir plus importable `pythonint`), and unavailable states. This avoids duplicating detection logic across object API and DB-API code.
4. Phase 2: New dispatch rules for object API
Rewrite `iris.cls()` dispatch to depend on `iris.runtime`, not on a hidden global connection slot. Proposed behavior: in `native` mode use `runtime.iris`; in `embedded` mode use embedded `cls`; in `auto` mode prefer embedded when available and otherwise use `runtime.iris` when present. If the selected backend is unavailable, raise a clear error instead of returning a mock silently for the configured path.
5. Phase 2: New dispatch rules for DB-API
Make `iris.dbapi.connect()` context-aware. In `mode="embedded"`, return the embedded adapter over `iris.sql`. In `mode="native"`, return a native DB-API connection or proxy. In `mode="auto"`, prefer embedded when embedded is available and no explicit remote connection arguments are supplied; otherwise choose native. This keeps DB-API user expectations intact while aligning with the unified context.
6. Phase 2: Runtime namespace design
Expose `iris.runtime` as a small object rather than a bag of functions. Recommended shape: immutable-ish inspected properties (`state`, `mode`, `embedded_available`) and a few explicit mutators (`configure`, `reset`). Avoid exposing multiple overlapping setters such as `set_active_dbapi_connection`; that would recreate the same problem under a new name.
7. Phase 3: Breaking-change migration
Replace all current usage sites of `set_active_connection()` with `iris.runtime.configure(...)`. Update [demo2.py](/Users/grongier/git/iris-embedded-python-wrapper/demo2.py) to show `iris.runtime.configure(mode="native", iris=db, native_connection=conn)` rather than registering one global active connection. Update tests to assert runtime-context behavior rather than direct global slot mutation.
8. Phase 3: Stubs and exports
Update [iris/__init__.pyi](/Users/grongier/git/iris-embedded-python-wrapper/iris/__init__.pyi) and the embedded stubs to expose `runtime` and remove the old helper functions. Update [iris/__init__.py](/Users/grongier/git/iris-embedded-python-wrapper/iris/__init__.py) and related module exports so the public surface tells one coherent story.
9. Phase 4: Error model and strictness
When `mode="embedded"` is selected but embedded runtime is unavailable, raise a dedicated runtime/configuration error. When `mode="native"` is selected but no `iris` or `dbapi` handle is bound for the API being used, raise a clear error. Reserve MagicMock fallback only for truly unconfigured/legacy import situations if you decide to preserve that behavior at all.
10. Phase 4: Documentation and examples
Document the new model around `state` versus `mode`, because that distinction is the key to understanding shell-local embedded versus kernel embedded. Show examples for `embedded-kernel`, `embedded-local`, and `native-remote` in one place.
11. Phase 5: Verification
Add tests for runtime configuration, state detection, object API routing, DB-API routing, reset behavior, and the failure modes when the chosen backend is unavailable. Include migration tests ensuring old examples are updated and the new API reads naturally.

**Relevant files**
- `/Users/grongier/git/iris-embedded-python-wrapper/_iris_ep/__init__.py` — replace hidden global lookup with runtime-context dispatch
- `/Users/grongier/git/iris-embedded-python-wrapper/iris_utils/_iris_utils.py` — current global slot to replace with `RuntimeContext`
- `/Users/grongier/git/iris-embedded-python-wrapper/iris_utils/__init__.py` — update exports from helper functions to runtime/context types
- `/Users/grongier/git/iris-embedded-python-wrapper/iris/__init__.py` — expose `runtime` publicly
- `/Users/grongier/git/iris-embedded-python-wrapper/iris/__init__.pyi` — remove `set_active_connection`/`get_active_connection`, add runtime stubs
- `/Users/grongier/git/iris-embedded-python-wrapper/_iris_ep/__init__.pyi` — same breaking API change on embedded entrypoints
- `/Users/grongier/git/iris-embedded-python-wrapper/iris_utils/_iris_native_proxy.py` — keep proxy behavior but feed it from `runtime.iris`
- `/Users/grongier/git/iris-embedded-python-wrapper/demo2.py` — migrate the public example to `iris.runtime.configure(...)`
- `/Users/grongier/git/iris-embedded-python-wrapper/tests/iris/test_native_proxy.py` — replace global slot tests with runtime-context tests
- `/Users/grongier/git/iris-embedded-python-wrapper/tests/iris/test_iris.py` — extend to cover runtime states and configuration

**Verification**
1. Verify `iris.runtime.state` correctly reports `embedded-kernel` when `sys._embedded` is true.
2. Verify `iris.runtime.state` reports `embedded-local` when `IRISINSTALLDIR` or `ISC_PACKAGE_INSTALLDIR` is present and `pythonint` imports successfully.
3. Verify `iris.runtime.state` reports `unavailable` when embedded runtime cannot be loaded and no native handles are bound.
4. Verify `iris.runtime.configure(mode="native", iris=db)` makes `iris.cls()` route through the native proxy layer.
5. Verify `iris.runtime.configure(mode="embedded")` makes `iris.cls()` and `iris.dbapi.connect()` choose the embedded backend and fail clearly if embedded is unavailable.
6. Verify `iris.runtime.reset()` clears explicit overrides and returns dispatch to `auto` mode.
7. Verify the new example paths for native remote, embedded local shell, and embedded kernel all read consistently.
8. Verify stubs and imports no longer mention `set_active_connection` or `get_active_connection`.

**Decisions**
- This is a breaking API redesign: remove `set_active_connection()` / `get_active_connection()` instead of preserving compatibility shims.
- Public API should be context-oriented: `iris.runtime` is the single runtime control surface.
- `mode` is user intent; `state` is detected reality. Both are required and should be visible.
- `embedded-local` and `embedded-kernel` are distinct runtime states but share the embedded backend family.
- `iris_obj` and `dbapi_conn` remain separate handles inside one runtime context rather than being forced into one “connection” concept.
- The DB-API bridge should not be synthesized from `iris_obj`; native DB-API should come from a real DB-API connection.

**Further Considerations**
1. Decide whether `iris.runtime.configure(...)` should eagerly validate the requested backend or defer validation until first use. Recommendation: validate eagerly when enough information is available.
2. Decide whether `iris.dbapi.connect(...)` should implicitly update `iris.runtime.dbapi` or remain independent. Recommendation: keep `connect()` independent first and only bind into runtime when explicitly configured.
3. Decide whether MagicMock fallback should survive this redesign. Recommendation: remove it for configured runtime paths and keep failures explicit.
