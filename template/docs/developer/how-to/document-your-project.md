# Document your project

This site is *your project's* documentation. It ships pre-wired with [properdocs](https://properdocs.org/)
and organized around the [Diátaxis](https://diataxis.fr/) framework, so the structure is ready — you just
write the content that describes **your** software.

This page is about documenting what your project *does*. For how the surrounding scaffold works
(the `_CI` tasks, uv, testing, SBOMs), see [The scaffold](../index.md).

## The four kinds of documentation

Diátaxis splits docs by what the reader needs *right now*. Put each page in the section that matches its
job — mixing them is the most common way docs get hard to use.

| Section | Answers | Write it for… | Example for your project |
| --- | --- | --- | --- |
| **Tutorials** | "Teach me by doing." | A newcomer who has never used your software. | A guided first session: install it, run the smallest end-to-end example, see a result. |
| **How-to** | "Help me solve this specific task." | A user who knows the basics and has a goal. | "Authenticate against the API", "Export results to CSV". |
| **Reference** | "Tell me the facts." | Someone who needs precise, lookup-style detail. | The API reference (auto-generated — see below), config keys, CLI flags. |
| **Explanation** | "Help me understand why." | Someone forming a mental model. | Why the architecture is shaped this way; trade-offs you chose. Start from [About your project](../../explanation/about-your-project.md). |

A good rule: a tutorial has one happy path and never stops to explain alternatives; a how-to assumes
competence and gets to the point; reference is exhaustive and boring on purpose; explanation is allowed
to discuss, compare, and admit trade-offs.

## Add a page

1. Create a markdown file under the matching section, e.g. `docs/how-to/export-to-csv.md`.
2. Register it in the `nav:` block of `properdocs.yml` so it appears in the navigation:

   ```yaml
   nav:
     - How-to:
       - Export to CSV: how-to/export-to-csv.md
   ```
3. Preview it — see [Preview docs locally](preview-docs-locally.md) for the live-reload server.

Files not listed in `nav:` still build, but won't appear in the navigation — keep the two in sync.

## Your API reference writes itself

The **Reference → API** page is generated from your code's docstrings by
[mkdocstrings](https://mkdocstrings.github.io/). You don't maintain it by hand — you maintain your
docstrings, and the page follows.

- Write [Google-style](https://google.github.io/styleguide/pyguide.html#38-comments-and-docstrings)
  docstrings on the public functions, classes, and modules in your package under `src/`.
- Use the sections mkdocstrings understands: `Args:`, `Returns:`, `Raises:`, `Yields:`, `Examples:`.
- Run the live-reload server and edit a docstring — the API page updates as you save.

So the most effective "documentation" you can write for reference material is a good docstring in the code.

## Replace the starters

Each of the four sections ships with a starter page carrying inline coaching comments — fill-in-the-blanks
scaffolding to edit, duplicate, or delete, not content to keep:

- [Getting started](../../tutorials/getting-started.md) — your first tutorial: install, smallest run, first win.
- [Solve a real task](../../how-to/solve-a-real-task.md) — a how-to skeleton; duplicate it once per real task
  and rename each copy after its goal.
- [Configuration](../../reference/configuration.md) — tables for the config surface your docstrings can't reach.
- [About your project](../../explanation/about-your-project.md) — a fill-in-the-blanks explanation page.

Make each one yours, then delete the coaching comments. Everything under **Developer** (this section)
documents the inherited scaffold instead — leave it be; it's kept up to date via `copier update`.

## See also

- [Preview docs locally](preview-docs-locally.md) — build and live-reload the site while you write.
- [The scaffold](../index.md) — the tooling behind properdocs and the rest of the project.
- [Diátaxis](https://diataxis.fr/) — the framework this structure follows, explained in depth.
