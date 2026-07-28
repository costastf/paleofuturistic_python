# Make your first template change

In this tutorial you clone the template repo, make a small change to what it generates, prove the change is correct at every level of the test pyramid, and open a pull request. At the end you'll know the edit-test loop every template change goes through.

Prerequisite: [uv](https://docs.astral.sh/uv/).

## 1. Clone and orient yourself

```bash
git clone https://github.com/schubergphilis/paleofuturistic_python
cd paleofuturistic_python
```

Everything under `template/` is what copier copies into a generated project; files ending in `.jinja` are rendered with the answers from `copier.yml`, everything else is copied verbatim. Everything *outside* `template/` — this repo's own `_CI/`, `docs/`, `tests/` — exists to develop and verify the template itself.

## 2. Make a change

Pick something harmless: open `template/README.md.jinja` and adjust a sentence, or tweak a page under `template/docs/`. If the file you edit ends in `.jinja`, remember that `{{ ... }}` and `{% ... %}` are rendered at generation time — plain text edits are safe.

## 3. Run the fast check

```bash
./workflow.cmd test.invariants
```

This generates a project for each matrix cell (git host × Dependency Track × Pages) once and asserts structural invariants over the results — the right files exist, conditional content matches the chosen knobs, nothing forbidden ships. It's the best signal-per-second check and should be your default while iterating.

## 4. Run one full cell

```bash
./workflow.cmd test
```

This generates a project with the default answers and runs the generated project's *own* full QA cycle inside it — `format`, `lint`, `test.tox`, `build`, `document`. If your change breaks the generated project's linters or docs build, this is where it surfaces.

To reproduce a specific CI matrix cell instead, use `test.combo`:

```bash
./workflow.cmd test.combo --git-hosting-service gitlab --no-integrate-pages
```

## 5. Commit and open a pull request

Commit messages must follow [Conventional Commits](https://www.conventionalcommits.org/) — `feat(template): …`, `fix(ci): …` — the lint step rejects anything else.

```bash
git checkout -b feat/my-first-change
git commit -am "feat(template): clarify the generated README wording"
git push -u origin feat/my-first-change
```

CI runs `test.invariants` plus a fanned-out `test.combo` per matrix cell on every pull request, so a green local run of steps 3–4 is a good predictor of a green PR.

## Where to go next

- [Test the template](../how-to/test-the-template.md) — all four test entry points and when to use each.
- [Extend the template workflow tasks](../how-to/extend-the-template-tasks.md) — changes that touch the generated `_CI/` framework.
- [Design principles](../explanation/design-principles.md) — the constraints your change should respect.
