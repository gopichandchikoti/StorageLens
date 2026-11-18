# StorageLens

A local Windows storage inspection app built for this device. Uses Python 3 and the Python standard library; no packages or accounts are required.

## Run

Double-click **Start-StorageLens.cmd**. The dashboard opens at http://127.0.0.1:8766. Python 3.13 is already installed on this device. Keep all files in this folder together.

The device snapshots are saved in `.data/storage.sqlite3`. Use **Scan device** to select any connected drives, all connected drives, or a specific local folder. **Quick** recursively reads logical file sizes and can overestimate disk use. **Deep** measures allocated space and deduplicates hard links. Both read metadata only and can take minutes for large drives. You can cancel a running scan.

Scanning one location preserves the latest whole-drive results for other drives. Folder scans have their own date and scope; parent totals refresh when the parent is scanned. **What’s growing** compares the latest two compatible whole-drive scans of the same mode. Use **Quit StorageLens** to stop the local server when finished.

For a broader scan of protected folders, quit the app, right-click the launcher, choose **Run as administrator**, and rescan. Elevation is optional and does not override every Windows protection. Do not start two copies of the scanner at the same time.

## Features

- Actual drive capacity/free space, folder allocation and logical sizes.
- Quick / Deep scan modes, multiple drive selection, and custom folder paths.
- A **Users explained** view separating the largest parts of your Windows profile.
- Folder drill-down and live direct-file listings (up to 500 per folder).
- Registered app names, versions, publishers, installation locations/dates, reported sizes, measured installation folders and labelled app-data associations.
- Largest files retained per drive (top 1,500 by allocation plus top 1,500 by logical size), with CSV export of the combined list.
- A review list for development caches, downloaded models, emulator data, temporary files and personal folders.
- Snapshot comparisons, coverage logs and CSV exports.
- Open scanned folders in Explorer or use Windows Storage / Apps settings.
- Per-folder and per-file **Review delete** controls explaining the likely impact before cleanup.
- Optional-app review filters and uninstall impact descriptions; uninstalls are handled in Windows Apps settings.
- Typed confirmation, fresh metadata validation, Recycle Bin cleanup, and an action history.

## Interface

The dashboard follows the supplied Capitalio reference: compact charcoal cards, blue actions, four storage metrics, a real usage-history chart, a folder-allocation donut, largest-folder table and storage insights. **Home** follows the supplied Watermelon landing-page reference with a dotted black background, lime typography and a tilted gallery of your actual drives. Its cards open the selected drive's dashboard. Charts show saved disk readings plus the current reading; they do not invent a timeline or savings estimate.

Drive cards switch the dashboard without starting a scan. The sidebar offers blue, lime and violet accent choices; your choice is saved in this browser. The header exports application, file and folder CSVs. Layouts adapt to smaller windows and respect reduced-motion settings. No fonts, images or UI libraries are fetched from an external service.

The visual direction was developed after reviewing Lenis, Watermelon UI, Manus, Realtime Colors, react-spring and Recent. The interface code and icons are original; it does not import those websites’ source or assets.

## Measurement limits

Scanning never opens user file contents. Cleanup is a separate explicit action: after reviewing impact, type the exact selected name and check the agreement to move that selection to Windows Recycle Bin. This app has no permanent-delete or empty-bin implementation. It does not uninstall applications or infer that an app is unused. No telemetry, cloud service or external assets are used.

Recycled items still use disk space. Restore or permanently remove selected recycled items through Windows after verification. The Recycle Bin is not a backup and can be emptied by Windows or other cleanup tools. Windows can reject oversized items, locked files, or unsupported locations. The native operation requests recycling and vetoes permanent-delete callbacks; failure does not trigger a permanent-delete fallback.

Drive roots, Windows folders, installed program folders, other account profiles, credentials, broad profile containers and StorageLens itself are protected. Some SDK/model data is managed through its owning application. Linked/cloud paths, unreadable selections and selections that cannot be fully reviewed are blocked. Cleanup reviews are limited to 250,000 entries or 35 seconds; select a smaller child folder if needed. Review tickets expire after ten minutes and cannot be reused after an attempted confirmed operation. A changed metadata manifest requires a new review.

Directory links, junctions and reparse points are skipped, so cloud-backed directory trees can be omitted. Inaccessible locations are logged. Unmounted partitions, network shares and other users’ application registrations are outside the scan.

Allocated sizes use `GetCompressedFileSizeW`; unavailable allocations are estimated in 4 KiB units. Hard links are counted once within each volume and assigned to the first path visited. Logical size counts every visible file name. Directory records, alternate streams and NTFS metadata are not included. Used space can exceed measured files because of protected folders, restore points, metadata and changes during the scan. Folder allocations can be lower than logical sizes due to compression and hard links.

Parent and child totals overlap. App folder associations can overlap across applications, and shared caches may not be wholly reclaimable. Windows reported app sizes can be missing or outdated. Folder totals are snapshot measurements; direct file listings are live.

## Data and source

`storage.py` performs scans; `inventory.ps1` reads application registrations without invoking `Win32_Product`; `cleanup.py` performs impact assessment and confirmation validation; `Recycle.cs` and `recycle.ps1` call the Windows Shell recycling API; `app.py` serves the dashboard only on loopback; `index.html`, `app.js`, `enhancements.js`, `design.js` and `style.css` implement the interface. No installation or startup entry is created. Scans and cleanup share a cross-process operation lock.

Scan metadata is stored under `.data/`, which is excluded from scanning itself. Snapshots consume disk space and are retained for comparisons. CSV exports may contain private file paths; keep them local unless you choose to share them.

The repository's `.gitignore` excludes `.data/`, the device-specific `inventory.json`, local location notes and Python caches. These files remain on your computer. A fresh copy creates its local data directory when started; use **Scan device** to collect that device's inventory and folder measurements.

To run from a terminal: `python Web/app.py --open`. To scan without the dashboard: `python Web/storage.py --mode deep --drives C: E:` or `python Web/storage.py --mode quick --folder "C:\Users\yourname\Downloads"`.


The root compatibility launcher remains the recommended entry. Source files are now in Web/; private data is retained in the repository root .data folder. Native platform versions and build instructions are documented in the root README.


### Relocation

The Move to another drive screen and Review move buttons now suggest and transfer personal files to another local NTFS drive. Choose a parent folder and a new child folder name. After typed confirmation, copies and named streams are verified before originals are recycled. Saved measurements are not rewritten: rescan after moving. Empty the relevant recycled originals through Windows only after reviewing the verified copies if you need to reclaim source-drive space. Whole-library location changes, app installations and project relocation use their owning tools. See root README for limits and cancellation/recovery behavior.
