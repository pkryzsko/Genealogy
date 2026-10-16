# /data — Source of Truth

This directory holds the written and visual representations Devin relies on when
answering questions or making decisions about this family history. `manifest.yaml` is
the index, and the trust level of every file is declared explicitly.

## Layout

| Path | Contents |
| --- | --- |
| `manifest.yaml` | Index of every entry in `/data/`, with its trust level. Consult this first. |
| `docs/` | Written representations. One folder per family line (e.g. `docs/norway/`). |
| `visual/` | Visual representations (diagrams, images, Mermaid `.mmd` files). |

## Trust model

| Level | Meaning | How Devin treats it |
| --- | --- | --- |
| `source` | Reviewed against records (documents, church books, census) and confirmed. | Relied on for decisions. |
| `draft` | Work in progress. | Context only; confirm before acting on it. |
| `unverified` | Not yet checked. **All data imported from Geni starts here.** | A hint; verify before relying on it. |
| `deprecated` | Superseded or shown to be wrong. | Ignored; kept for history. |

A file is **source of truth** only if it has frontmatter `truth: source` **or** a manifest
entry with `truth_level: source`. Unmarked, unlisted files default to `unverified`. If the
frontmatter and the manifest disagree, the lower level applies.

## Maintenance rules

- Add every new file or line folder to `manifest.yaml`. Paths are relative to `/data/`.
- Update `last_updated` whenever content changes.
- Promote to `source` only after review.
- Mark wrong or outdated entries `deprecated` rather than deleting them silently.
