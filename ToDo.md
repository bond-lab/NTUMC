# Things to apply to the main

## wn
fixlinks.py
fixwn.py

## download more

* cross-language links
  There are also link DBs for non-English pairs (cmn-jpn, ind-cmn, jpn-kor etc.) in the 2016
  snapshot, though I didn't check their validity.

* korean

## English fixes from intern
 /home/bond/work/ntu-mc/2017-11-17
 
 
### add other languages
* Bulgarian
* Abui
* Polish

##  Indonesian spec — the 4,622 missing tags
  
  This is a partial re-annotation, not data loss or a bug. Here's what happened to The Speckled Band
  (Indonesian) between the 2016 snapshot and the Feb 2025 build:

  ┌───────────────────────┬───────┬───────┬────────┐
  │       Category        │ 2016  │ Build │ Change │
  ├───────────────────────┼───────┼───────┼────────┤
  │ synset-tagged         │ 6,139 │ 2,304 │ −3,835 │
  ├───────────────────────┼───────┼───────┼────────┤
  │ x (not in WN)         │ 2,424 │ 1,799 │ −625   │
  ├───────────────────────┼───────┼───────┼────────┤
  │ w (wrongly segmented) │ 153   │ 12    │ −141   │
  ├───────────────────────┼───────┼───────┼────────┤
  │ NE: per/org/loc       │ 108   │ 6     │ −102   │
  ├───────────────────────┼───────┼───────┼────────┤
  │ null/empty            │ 0     │ 4,622 │ +4,622 │
  └───────────────────────┴───────┴───────┴────────┘

  All 4,622 null concepts still have their word links intact (cwl entries preserved). The tag was
  cleared but the concept itself was kept. Only 17 concepts got a different synset assigned. This
  pattern — clearing tags without re-assigning them — looks like someone started a quality-control
  pass on spec (visiting concepts, clearing uncertain tags) but never finished. The 2016 annotation
  is still in ~/work/ntu-mc/2016-11-30/ind.db and could be used to restore it.

  Question for you: Was spec in Indonesian deliberately re-reviewed (and the cleared tags are
  intentional "I'm not sure about these")? Or should the 2016 tags be restored for the ~4,622 cleared
  items?

  ---
  Cross-language link DBs

  The 2016 snapshots are in good shape and almost entirely valid against the current build DBs:

  ┌─────────┬──────────────┬───────────────┬────────┬───────────────────────────────────────┐
  │ Link DB │ Total slinks │     Valid     │ Broken │           Broken documents            │
  ├─────────┼──────────────┼───────────────┼────────┼───────────────────────────────────────┤
  │ eng-cmn │ 6,555        │ 6,462 (98.6%) │ 93     │ kumo-no-ito (73), spec (13), danc (7) │
  ├─────────┼──────────────┼───────────────┼────────┼───────────────────────────────────────┤
  │ eng-jpn │ 1,535        │ 1,520 (99.0%) │ 15     │ danc (15)                             │
  ├─────────┼──────────────┼───────────────┼────────┼───────────────────────────────────────┤
  │ eng-ind │ 2,746        │ 2,746 (100%)  │ 0      │ —                                     │
  ├─────────┼──────────────┼───────────────┼────────┼───────────────────────────────────────┤
  │ eng-zsm │ 79           │ 79 (100%)     │ 0      │ —                                     │
  └─────────┴──────────────┴───────────────┴────────┴───────────────────────────────────────┘

  The 93 broken eng-cmn links and 15 broken eng-jpn links are all in documents where sentences were
  restructured between 2016 and 2025 — kumo-no-ito (Spider's Thread), danc (Dancing Men), and spec.
  The broken entries are small enough to either delete or re-link by hand once the server is
  reachable.

  All link DBs are missing clink (concept-level links) — the clink table exists but has 0 rows in all
  2016 files. Only sentence-level links were ever populated.

  There are also link DBs for non-English pairs (cmn-jpn, ind-cmn, jpn-kor etc.) in the 2016
  snapshot, though I didn't check their validity.

For the Indonesian, I think we probably copied the wrong file across at some stage.   Is there    
  anything in the new file not in the 2016 snapshots?  i.e. can we go back to that, or should we     
  merge properly, ...  

## Manual

Update!


# Display (branch: display-corpus)

## Done (2026-06-21)
* Dynamic language loading — WN defs/syns/translations fetched from JSON, not baked in
* Cross-compiled slinks for all language pairs via English pivot
* Fixed cmn.db spec/danc sid swap + imported kumo-no-ito
* Recovered 1280 standalone concepts into cmn.db from old DB
* Imported eng-ita.db (475 slinks) and eng-zsm.db (79 slinks) from old snapshots
* Propagated stypes bidirectionally across all languages
* Aligned kc01/kc02 via article IDs — 1466 new eng↔jpn slinks + paragraph markers
* 36 pytest tests + browser tests for make_display.py
* Annotation audit script comparing build vs all old DBs

## TODO
* ~~catb: extract paragraph/heading stypes from source HTML~~ Done (fix_catb_stype.py)
* Review cwl errors found by `check_cwl.py`: concept-word links where unrelated
  words share a concept (eng: 682, jpn: 466, ces: 81, cmn: 37, ind: 26, ita: 2)
* jpn tourism (312 docs): no slinks — same doc names as eng but different sid ranges, need alignment
* ind spec: investigate 4,622 cleared concept tags (see above)
* Deploy display to GitHub Pages

