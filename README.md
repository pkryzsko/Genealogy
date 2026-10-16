# Genealogy

Indexed family-history data for the Kryzsko family lines, imported from
[Geni](https://www.geni.com) and organized so people (and Devin) can rely on it.

**This repository is public and contains deceased relatives only.** Living relatives
are kept in a separate private repository.

## Lines

| Line | Folder | Anchor |
| --- | --- | --- |
| Norwegian | `data/docs/norway/` | Grandmother Schultz (maternal side) |

Irish, German and Polish lines will be added as sibling folders.

Each line folder contains:

- `index.json`: every profile in the line with relation, generation, birth/death years and Geni URL.
- `profiles/`: one JSON file per profile.
- `tree.mmd`: a Mermaid family-tree diagram (children point to parents).

## Trust

See [`data/README.md`](data/README.md). Imported Geni data is user-contributed, so it is
`unverified` until reviewed.

## Updating

`tools/geni_import.py` re-imports a line through Geni's official API. It needs
`GENI_APP_SECRET` (and optionally `GENI_APP_ID`) in the environment; never commit them.
