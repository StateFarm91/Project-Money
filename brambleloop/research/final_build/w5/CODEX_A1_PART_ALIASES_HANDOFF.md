# A1 explicit detachable part aliases

Continuation of `codex/a1-detachable-eye-safety` at `ec2dee6`. The existing under-three detachable-parts reader now recognizes explicit rattle inserts/boxes, compact pompoms, snap fasteners/press studs, and French buttons, beads and bells. These names use the same refusal as other detachable parts; they do not create a physical test, owner approval or exception. The existing `plastic_rattle_insert` classification is preserved without a duplicate generic classification.

Final source: Python 3.11 targeted children's PDF and actual SQLite `assets.build` Worker checks passed 3/3; independent reviewer reran two alias/PDF cases 2/2. Children's/A1 regression passed 62/62 immediately before the final duplicate-classification fix and its assertion. The Worker test uses a synthetic exact-design assignment only to reach the safety gate; no real authorization is implied.

Explicit word detection is finite, and a non-instruction mention can be conservatively held. This change does not establish physical safety or close parent A1 authority, source-fencing, or reapproval blockers. No purchase, publication, deployment or approval occurred.

## Unqualified toy-eye follow-up

Explicit `toy`, `doll`, `craft`, or `animal` eyes without a hard-material qualifier are now an UNKNOWN applied part and refused by the existing children's assessment, rather than silently omitted. Even `embroidered toy eyes` and `crocheted doll eyes` are UNKNOWN: a nearby adjective does not prove that the applied piece is integral. Previously supported exact `embroidered eyes` and `crocheted eyes` wording remains unchanged; ambiguous or contradictory hard-material wording adds UNKNOWN. No physical sample or new approval is inferred. This can conservatively hold a negative or otherwise harmless mention.

Python 3.11 tmpfs SQLite: `test_childrens.py` plus real `assets.build` Worker suite 46/46. The independent reviewer reran the actual Worker case 1/1 and confirmed the new phrases are held without a claim of physical safety. Legacy plain `embroidered eyes` interpretation and finite language coverage remain outside this fix. Descendant PRs based on the previous commit must retain this follow-up during integration.

## Neck/hood cord wording follow-up

The existing children's neck/hood drawstring reader now uses the shared Unicode fold and detects explicit `drawcord`, `draw-string`, French `cordon` near `capuche`/related neck terms, and an adjacent sentence only when a concrete action explicitly refers back to `it` or `them` and names the neck/hood. A reviewer identified a false hold on unrelated `This hood` copy; the reference rule was narrowed and that control added. Waist-only cord language remains a control, not an automatic exception for hood cords.

Python 3.11 tmpfs SQLite: final children's PDF and actual assets Worker suite 48/48. The independent reviewer reran the targeted PDF/waist-control case and the preceding actual Worker case, each 1/1. The Worker fixture temporarily binds a synthetic exact assignment to reach the child safety gate. This is finite wording recognition: unreferenced/more distant statements and separate CIR text fields can still be missed, and some ambiguous copy can be conservatively held. It is not a general safety classifier or physical evidence.

## Sewn felt retention follow-up

`felt_shapes_sewn` remains discoverable, including explicit `sewn felt eyes` and `felt shapes are stitched`, but is now UNKNOWN rather than automatically integral: separately attached felt retention is not established by wording. This creates a conservative hold pending an independently approved, content-bound physical-evidence authority. The old unscoped `SMALL_PARTS_EVIDENCE` assertion cannot clear it. Existing `embroidered_eyes` classification is unchanged. There is currently no accepted content-bound evidence exception to demonstrate as a legitimate clearance; no such authority was created.

Python 3.11 tmpfs SQLite children's and real assets Worker suite passed 50/50 on final code. Independent reviewer reran the focused PDF and Worker checks 2/2. Exact assignment in the Worker fixture was synthetic. Other felt wording and other detached-part phrasing may still be missed; the parent A1 safety/authority blockers remain, and descendants based on old 32f3163 must retain the follow-up during integration.
