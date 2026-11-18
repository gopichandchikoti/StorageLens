package com.portfolio.storagelens;

import android.content.Context;
import android.database.Cursor;
import android.net.Uri;
import android.os.Environment;
import android.provider.DocumentsContract;
import android.system.Os;
import org.json.JSONArray;
import org.json.JSONObject;
import java.io.File;
import java.nio.file.DirectoryStream;
import java.nio.file.Files;
import java.nio.file.Path;
import java.util.ArrayList;
import java.util.Comparator;
import java.util.HashSet;
import java.util.List;
import java.util.PriorityQueue;
import java.util.Set;
import java.util.UUID;
import java.util.concurrent.atomic.AtomicBoolean;

final class StorageScanner {
    private static final int ENTRY_LIMIT = 500000, NODE_LIMIT = 4000, FILE_LIMIT = 200, DEPTH_LIMIT = 64;
    private final Context context;
    private final Snapshots snapshots;
    interface Roots { java.util.Map<String, File> get(); }
    private final Roots roots;
    private final AtomicBoolean running = new AtomicBoolean(), cancel = new AtomicBoolean();
    private volatile JSONObject state = new JSONObject();
    private final List<JSONObject> nodes = new ArrayList<>();
    private final PriorityQueue<JSONObject> large = new PriorityQueue<>(Comparator.comparingLong(n -> n.optLong("logical")));
    private final Set<String> identities = new HashSet<>();
    private long files, folders, errors, bytes, deadline;
    private boolean limited, estimated;
    private String mode, rootId;

    StorageScanner(Context context, Snapshots snapshots) {
        this(context, snapshots, () -> new Volumes(context).roots());
    }
    StorageScanner(Context context, Snapshots snapshots, Roots roots) {
        this.context = context;
        this.snapshots = snapshots;
        this.roots = roots;
    }
    boolean running() { return running.get(); }
    JSONObject progress() { return state; }
    void cancel() { cancel.set(true); }

    boolean reserve() {
        if (!running.compareAndSet(false, true)) return false;
        cancel.set(false);
        files = folders = errors = bytes = 0;
        publish("starting");
        return true;
    }

    void run(String selectedMode, String selectedRoot) {
        try {
            limited = false;
            nodes.clear(); large.clear(); identities.clear();
            mode = selectedMode; rootId = selectedRoot;
            deadline = System.nanoTime() + 600_000_000_000L;
            estimated = mode.equals("quick") || rootId.equals("selected");
            publish("scanning");
            long measured;
            if (rootId.equals("selected")) measured = scanSelected();
            else {
                if (!Environment.isExternalStorageManager()) throw new SecurityException("permission");
                File root = roots.get().get(rootId);
                if (root == null) throw new IllegalArgumentException("root");
                measured = walkFile(root.toPath(), root.getCanonicalPath(), "", 0);
            }
            if (cancel.get()) { publish("cancelled"); return; }
            List<JSONObject> sorted = new ArrayList<>(large);
            sorted.sort(Comparator.comparingLong((JSONObject n) -> n.optLong("logical")).reversed());
            nodes.sort(Comparator.comparingLong((JSONObject n) -> n.optLong("bytes")).reversed());
            JSONObject snapshot = new JSONObject().put("schemaVersion", 1).put("mode", mode)
                    .put("root", rootId).put("measuredAt", System.currentTimeMillis())
                    .put("bytes", measured).put("files", files).put("folders", folders).put("errors", errors)
                    .put("limited", limited).put("estimated", estimated).put("nodes", new JSONArray(nodes))
                    .put("largeFiles", new JSONArray(sorted));
            snapshots.save(snapshot);
            publish("complete");
        } catch (SecurityException error) { publishFailure("permission"); }
        catch (Exception error) { publishFailure("failed"); }
        finally { running.set(false); }
    }

    private boolean stop(int depth) {
        if (Thread.currentThread().isInterrupted()) cancel.set(true);
        if (cancel.get()) return true;
        if (files + folders >= ENTRY_LIMIT || System.nanoTime() >= deadline || depth > DEPTH_LIMIT) {
            limited = true; return true;
        }
        return false;
    }

    private long walkFile(Path path, String root, String relative, int depth) throws Exception {
        if (stop(depth)) return 0;
        File file = path.toFile();
        String canonical;
        try { canonical = file.getCanonicalPath(); }
        catch (java.io.IOException error) { errors++; return 0; }
        if (Files.isSymbolicLink(path) || !(canonical.equals(root) || canonical.startsWith(root + "/"))) {
            errors++; return 0;
        }
        if (relative.equals("Android/data") || relative.equals("Android/obb")) { errors++; return 0; }
        if (!file.canRead()) { errors++; return 0; }
        if (!file.isDirectory()) {
            files++;
            long logical = file.length(), allocated = logical;
            if (mode.equals("deep")) {
                try {
                    var stat = Os.lstat(canonical);
                    boolean shared = stat.st_nlink > 1 && stat.st_ino != 0;
                    allocated = !shared || identities.add(stat.st_dev + ":" + stat.st_ino) ? stat.st_blocks * 512 : 0;
                } catch (android.system.ErrnoException error) { errors++; estimated = true; }
            }
            keepFile(relative, canonical, logical, file.lastModified());
            bytes += allocated;
            if (files % 128 == 0) publish("scanning");
            return allocated;
        }
        folders++;
        if (mode.equals("quick") && depth >= 2) { limited = true; return 0; }
        long total = 0, startingFiles = files;
        try (DirectoryStream<Path> entries = Files.newDirectoryStream(path)) {
            for (Path child : entries) {
                if (stop(depth)) break;
                String id = relative.isEmpty() ? child.getFileName().toString() : relative + "/" + child.getFileName();
                if (id.length() > 2048) { errors++; continue; }
                total += walkFile(child, root, id, depth + 1);
            }
        } catch (java.io.IOException | SecurityException error) { errors++; }
        keepNode(relative, total, files - startingFiles);
        return total;
    }

    private long scanSelected() throws Exception {
        String value = context.getSharedPreferences("access", Context.MODE_PRIVATE).getString("tree", "");
        if (value.isEmpty()) throw new SecurityException("permission");
        Uri tree = Uri.parse(value);
        return walkDocument(tree, DocumentsContract.getTreeDocumentId(tree), "", 0, new HashSet<>());
    }

    private long walkDocument(Uri tree, String id, String relative, int depth, Set<String> seen) throws Exception {
        if (stop(depth)) return 0;
        if (seen.size() >= NODE_LIMIT) { limited = true; return 0; }
        if (!seen.add(id)) { errors++; return 0; }
        folders++;
        if (mode.equals("quick") && depth >= 2) { limited = true; return 0; }
        Uri children = DocumentsContract.buildChildDocumentsUriUsingTree(tree, id);
        String[] columns = {"document_id", "_display_name", "mime_type", "_size", "last_modified"};
        long total = 0, startingFiles = files;
        try (Cursor cursor = context.getContentResolver().query(children, columns, null, null, null)) {
            if (cursor == null) { errors++; return 0; }
            while (cursor.moveToNext() && !stop(depth)) {
                String child = cursor.getString(0), name = cursor.getString(1);
                if (child == null || child.length() > 4096 || name == null || name.length() > 1024) { errors++; continue; }
                String next = relative.isEmpty() ? name : relative + "/" + name;
                if (DocumentsContract.Document.MIME_TYPE_DIR.equals(cursor.getString(2))) {
                    total += walkDocument(tree, child, next, depth + 1, seen);
                } else {
                    if (cursor.isNull(3)) { errors++; continue; }
                    long length = Math.max(0, cursor.getLong(3));
                    files++; total += length; bytes += length;
                    keepFile(next, "", length, cursor.getLong(4));
                    if (files % 128 == 0) publish("scanning");
                }
            }
        } catch (SecurityException error) { throw error; }
        catch (RuntimeException error) { errors++; }
        keepNode(relative, total, files - startingFiles);
        return total;
    }

    private void keepNode(String relative, long total, long count) throws Exception {
        if (nodes.size() >= NODE_LIMIT) { limited = true; return; }
        int slash = relative.lastIndexOf('/');
        nodes.add(new JSONObject().put("id", relative).put("parent", slash < 0 ? "" : relative.substring(0, slash))
                .put("name", relative.isEmpty() ? rootId : relative.substring(slash + 1))
                .put("bytes", total).put("files", count));
    }

    private void keepFile(String relative, String path, long length, long modified) throws Exception {
        if (large.size() >= FILE_LIMIT && length <= large.peek().optLong("logical")) return;
        JSONObject value = new JSONObject().put("id", UUID.randomUUID().toString()).put("name", relative)
                .put("path", path).put("logical", length).put("modified", modified);
        large.add(value);
        if (large.size() > FILE_LIMIT) large.poll();
    }

    private void publish(String status) {
        try { state = new JSONObject().put("status", status).put("files", files)
                .put("folders", folders).put("errors", errors).put("bytes", bytes); }
        catch (org.json.JSONException error) { throw new IllegalStateException(error); }
    }
    private void publishFailure(String reason) {
        try { state = new JSONObject().put("status", "failed").put("reason", reason); }
        catch (org.json.JSONException error) { throw new IllegalStateException(error); }
    }
}
