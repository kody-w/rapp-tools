# Pinned workspace tooling

These ZIPs contain MIT-licensed public reference sources, not RAPP/1 eggs.
`pins.json` binds the exact repository commits, sizes, SHA-256 values and file
counts. Every ZIP carries an exact per-file manifest and original license.

- RAPP/1: `kody-w/rapp-1@dda32d741c7218f41443a5bd17eebfe0eae82cb7`,
  verified rev-15 chain/materialized specification.
- Workspace: `kody-w/rapp-workspace@44f6f124c47ed610b32e4d78f596b9b099669657`,
  `rapp-workspace/2.0` reference manager and project skills.

Rebuild from clean, exact public checkouts:

```sh
python3 tools/build_workspace_bundles.py \
  --authority-root /verified/rapp-1 \
  --workspace-root /verified/rapp-workspace \
  --output workspace/artifacts
```

The selected public protected-main checkpoint is the publication authority
input. The offline bootstrap verifies its frozen parser/profile, chain and
normative bytes. An internally consistent unsigned chain alone does not
authenticate a head. Use explicit network freshness checks before calling the
pin current; review and release a separately versioned tooling successor when
authority changes.

The bundled reference is an exact-integer profile, not full floating-point
JCS. Registered genesis, independent stream binding, signatures/lifecycle,
registry freshness/high-water state, and production Grail activation are
separate evidence requirements. Do not select a trust anchor from untrusted
candidate data or treat successful vectors as an application's certification.

The private local workspace contains the upstream project capabilities. Their
presence does not authorize Hive sharing, key creation, deployment, arbitrary
code execution, or a public push. Follow the host refresh workflow and preserve
the selected world boundary.
