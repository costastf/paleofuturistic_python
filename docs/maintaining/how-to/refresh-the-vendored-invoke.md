# Refresh the vendored invoke

For when [vendored_invoke](https://github.com/schubergphilis/vendored_invoke) tags a new release
and this template should ship it. The trees under `_CI/lib/vendor/` and `template/_CI/lib/vendor/`
are not maintained here: upstream builds them, and this repository copies the result in
verbatim, so the only edit you make is the pin.

## What the pin is

`pyproject.toml` records the upstream release in two fields that say the same thing twice:

```toml
[tool.vendored-invoke]
repository = "schubergphilis/vendored_invoke"
version = "v3.0.0"
commit = "4810777da7b297eb3c1b3c3f6e608dc64ca25b7d"
```

`version` is the upstream release tag, for people. `commit` is the commit that tag points at,
for the sync: tags can be moved, commits cannot, so the sync fetches the commit. The version of
invoke itself is not here; `_CI/lib/vendor.txt` records it.

## Refresh it

1. Find the commit the new tag points at:

   ```bash
   git ls-remote --tags https://github.com/schubergphilis/vendored_invoke
   ```

2. Set both fields in `[tool.vendored-invoke]` and commit that change on its own. The sync
   refuses a dirty tree, so the diff it produces is the vendored change and nothing else.

3. Copy the release in:

   ```bash
   ./workflow.cmd maintain.sync-vendor
   ```

   It downloads the pinned commit and replaces `vendor/`, `vendor.txt` and `patches/` in both
   trees. `vendor.txt`'s `# via` attribution is rewritten to this repository's own `_CI`
   package name; nothing else is edited.

4. Read `git diff --stat`. Only files under the two `_CI/lib/` trees should have changed, and
   both trees identically.

5. Run the full verification: `./workflow.cmd lint`, `./workflow.cmd test.invariants`,
   `./workflow.cmd test`, `./workflow.cmd test.combo --git-hosting-service gitlab` and
   `./workflow.cmd test.combo --mature`. The invariants check that the two trees are
   byte-identical, pure Python, and that every package in the tree is pinned in `vendor.txt`.

6. Commit the vendored change with the pin, and push.

Running `maintain.sync-vendor` again on the committed tree must change nothing. If it does, the
tree was edited by hand somewhere, which the pin exists to make visible.

## The patches

`_CI/lib/patches/` holds the two hand-maintained edits upstream applies while building the tree.
They arrive with the sync; nothing here applies them.

- `path_inject.patch` adds a `sys.path` prelude to `bin/inv` and `bin/invoke`, so the launcher
  can import the vendored tree and the project's `_CI` package with nothing installed.
- `vendored_version.patch` hard-codes invoke's version string. invoke 3 reads its version from
  installed package metadata, which a vendored copy does not have, so without the patch the
  import fails before anything runs.

## Source of truth

- [schubergphilis/vendored_invoke](https://github.com/schubergphilis/vendored_invoke) — the
  upstream repository; its README documents how the tree is built and re-vendored.
- [`maintain.sync-vendor`](https://github.com/schubergphilis/paleofuturistic_python/blob/main/_CI/tasks/maintain.py)
  in this repository — what the copy does, and what it refuses.
