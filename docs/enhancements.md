# StorageLens enhancements

## Personal-file relocation — Windows/Web 1.1.0 preview

Requested November 17, 2026. Implemented requirements:

- Suggest large personal downloads, documents, music, photos and videos from saved
  scans, showing scope, measurement date, size and a reason to review.
- Select one or multiple files/folders from suggestions, Folder explorer, Users
  explained and Largest files.
- Choose another connected drive, browse its folders and create a named child
  folder for the selected items. Prefer fixed drives with more free space when
  offering the default choice; the user chooses the final destination.
- Show exact destinations, capacity needs and the consequences for shortcuts,
  playlists and app references before typed confirmation.
- Copy and verify file contents and named streams before recycling originals.
  No overwriting/merging or permanent deletion of original files.
- Show progress, allow cancellation, retain partial copies for review, record
  completed/failed/interrupted actions and open the destination in Explorer.
- Explain that originals still occupy space in Recycle Bin until removed through
  Windows. Keep app/system/project/state/credential locations protected.

Current limits: NTFS destinations, 25 non-overlapping selections, 25,000 entries
per review and a 30-second review bound. Source projects and whole Windows library
containers use their owning tools; choose personal children instead. No personal
files are moved automatically by suggestions or by this enhancement task.

Detailed contracts, ownership, evidence and residual risks are maintained in
[architecture section 7](architecture.md#7-relocation-enhancement).

## Planned extensions

- Android external SD-card/provider moves with explicit read/write grants,
  provider-specific verification and cancellation/recovery; private app data stays
  under Android's protections. Android 1.1.0 has no new move adapter.
- Windows Known Folder Location migration through supported Windows mechanisms,
  preserving library locations rather than silently changing paths.
- exFAT/removable-media destinations, with an explicit plan for metadata or named
  streams the destination cannot preserve.
- Same-drive reorganization with an explanation that it does not free drive space.
- Explicit recovery/resume of interrupted jobs after fresh validation.

These extensions are requirements/backlog, not claims about the shipped preview.
