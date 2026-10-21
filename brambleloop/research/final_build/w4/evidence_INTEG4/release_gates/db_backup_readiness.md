# db-backup readiness (read-only Railway log read, 2026-10-21T02:3xZ; nothing redeployed)

Service db-backup (4dcbeb0b…), project brambleloop, environment production. Latest run:

- `BK start 20261020T035733Z`
- `BK file /backup/brambleloop_prod_20261020T035733Z.dump bytes 400700102 sha256 9b048ea46a550bdd69b3d9621479b35c19eb03c56d9ca11ca556c9a4e7f30995`
- `BK toc_entries 1344`
- `BK restore_ok`
- `BK tables 135 restored_rows 143054 tables_changed_since_snapshot 1`
- `BK volume 3.7G total 682M free`
- `BK RESULT OK /backup/brambleloop_prod_20261020T035733Z.dump`

The previous run, 20261020T034535Z, was also `RESULT OK` and `restore_ok`.

The pre-deploy backup is taken at deploy time, with the owner's approval. 682 MB free holds one
more ~400 MB dump, not two. Prune or grow the volume before a second.
