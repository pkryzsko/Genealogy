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

It can also read a GEDCOM export (from Geni, MyHeritage or genealogy software)
instead of calling the API, applying the same scope and living/deceased split:

```
python3 tools/geni_import.py find --gedcom tree.ged Schultz        # look up record ids
python3 tools/geni_import.py path --gedcom tree.ged --me @I1@      # check me -> mother -> grandmother
python3 tools/geni_import.py run --gedcom tree.ged --me @I1@ --line norway \
    --public-dir data/docs --private-dir ../Genealogy-Living/data/docs
```

Keep the `.ged` file itself out of this public repo: it contains living relatives.
