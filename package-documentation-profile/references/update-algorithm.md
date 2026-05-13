# Update Algorithm

Use git provenance to refresh profiles progressively while preserving manual editorial fields.

## Required Manifest Fields

Incremental refresh requires:

- `source.git.current_hash`
- `profile_files.modules`
- `scope.package_roots`

If any are missing, run a conservative initial profile and set `previous_hash` to null.

## REFRESH_SCOPE

```pseudocode
REFRESH_SCOPE(profile_path, package_path):
  manifest = read_json(profile_path + "/manifest.json")
  previous_hash = manifest.source.git.current_hash
  current_hash = git rev-parse HEAD

  IF previous_hash is null:
    RETURN full_refresh(reason="missing previous hash")

  IF git cat-file -e previous_hash fails:
    RETURN full_refresh(reason="previous hash unavailable locally")

  changed_committed = git diff --name-only previous_hash current_hash
  changed_uncommitted = parse git status --short

  changed_files = union(changed_committed, changed_uncommitted.paths)
  changed_modules = map_files_to_modules(changed_files, manifest.scope.package_roots)
  changed_facets = map_modules_to_audiences(changed_modules, profile_path)

  local_dependents = find modules that import or reference changed_modules

  RETURN {
    "previous_hash": previous_hash,
    "current_hash": current_hash,
    "changed_files": changed_files,
    "changed_modules": changed_modules + local_dependents,
    "changed_facets": changed_facets,
    "dirty_files": changed_uncommitted
  }
```

## Refresh Rules

- Refresh changed modules and direct local dependents.
- Refresh facets for every audience touched by changed modules.
- Re-run coverage after every refresh.
- Preserve `manual` fields in existing module profiles.
- Mark profiles as stale when their `source_hash` does not match the current hash and they were not refreshed.
- Mark profiles as orphaned when the source module no longer exists.
- If many modules changed or package structure changed, prefer full refresh.

## Full Refresh Triggers

Run a full profile refresh when:

- the previous hash is missing or unavailable;
- package roots changed;
- public export files changed substantially;
- module discovery rules changed;
- more than one third of source modules changed;
- coverage reports missing or orphaned profiles after partial refresh.

## Provenance Semantics

`current_hash` identifies the committed repository baseline. If the working tree is dirty, record dirty files separately and set `working_tree_dirty: true`; do not pretend the profile corresponds only to the commit.
