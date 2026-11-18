package com.portfolio.storagelens;

import android.content.Context;
import android.content.Intent;
import android.content.pm.ApplicationInfo;
import android.net.Uri;
import android.provider.Settings;
import androidx.webkit.JavaScriptReplyProxy;
import org.json.JSONObject;
import java.util.Set;
import java.util.concurrent.ArrayBlockingQueue;
import java.util.concurrent.ThreadPoolExecutor;
import java.util.concurrent.TimeUnit;

final class NativeRouter implements AutoCloseable {
    static final String ORIGIN = "https://appassets.androidplatform.net";
    private static final Set<String> METHODS = Set.of("snapshot", "refresh", "progress", "scan", "cancel",
            "usageAccess", "fileAccess", "chooseFolder", "appSettings", "uninstall", "appDetails",
            "securitySettings", "storageSettings", "trashMedia");
    private final MainActivity activity;
    private final Context context;
    private final Packages packages;
    private final Snapshots snapshots;
    private final StorageScanner scanner;
    private final ThreadPoolExecutor requests = pool(1, 8), scans = pool(1, 1);
    private volatile boolean closed;

    NativeRouter(MainActivity activity) {
        this.activity = activity;
        context = activity.getApplicationContext();
        packages = new Packages(context);
        snapshots = new Snapshots(context);
        scanner = new StorageScanner(context, snapshots);
    }

    static boolean trusted(String origin, boolean mainFrame) {
        return mainFrame && ORIGIN.equals(origin);
    }

    private static ThreadPoolExecutor pool(int threads, int capacity) {
        return new ThreadPoolExecutor(threads, threads, 0, TimeUnit.MILLISECONDS, new ArrayBlockingQueue<>(capacity));
    }

    void receive(String message, String origin, boolean mainFrame, JavaScriptReplyProxy reply) {
        if (closed || !trusted(origin, mainFrame) || message == null || message.length() > 8192) return;
        String id = "";
        try {
            JSONObject request = new JSONObject(message);
            id = request.getString("id");
            String method = request.getString("method");
            if (!id.matches("[a-zA-Z0-9-]{1,64}") || !METHODS.contains(method)) throw new IllegalArgumentException();
            JSONObject args = request.optJSONObject("args");
            if (args == null) args = new JSONObject();
            final String requestId = id;
            final JSONObject input = args;
            // Progress/cancel stay responsive while app statistics are being collected.
            if (method.equals("progress") || method.equals("cancel")) {
                respond(reply, requestId, execute(method, input), null); return;
            }
            requests.execute(() -> {
                try { respond(reply, requestId, execute(method, input), null); }
                catch (java.util.concurrent.RejectedExecutionException error) { respond(reply, requestId, null, "busy"); }
                catch (SecurityException error) { respond(reply, requestId, null, "permission"); }
                catch (IllegalArgumentException error) { respond(reply, requestId, null, "invalid"); }
                catch (Exception error) { respond(reply, requestId, null, "failed"); }
            });
        } catch (java.util.concurrent.RejectedExecutionException error) { respond(reply, id, null, "busy"); }
        catch (Exception error) { respond(reply, id, null, "invalid"); }
    }

    private JSONObject execute(String method, JSONObject args) throws Exception {
        return switch (method) {
            case "snapshot", "refresh" -> snapshot(method.equals("refresh"), args.optString("root"));
            case "progress" -> scanner.progress();
            case "cancel" -> { scanner.cancel(); yield new JSONObject().put("requested", true); }
            case "scan" -> startScan(args);
            case "appDetails" -> packages.details(packageName(args));
            case "chooseFolder" -> onUi(activity::chooseFolder);
            case "usageAccess" -> open(new Intent(Settings.ACTION_USAGE_ACCESS_SETTINGS,
                    Uri.parse("package:" + context.getPackageName())));
            case "fileAccess" -> open(new Intent(Settings.ACTION_MANAGE_APP_ALL_FILES_ACCESS_PERMISSION,
                    Uri.parse("package:" + context.getPackageName())));
            case "appSettings" -> open(new Intent(Settings.ACTION_APPLICATION_DETAILS_SETTINGS,
                    Uri.parse("package:" + packageName(args))));
            case "uninstall" -> uninstall(args);
            case "securitySettings" -> open(new Intent(Settings.ACTION_SECURITY_SETTINGS));
            case "storageSettings" -> open(new Intent(Settings.ACTION_INTERNAL_STORAGE_SETTINGS));
            case "trashMedia" -> onUi(() -> activity.reviewMediaTrash(args.optString("id"), args.optString("root"), snapshots));
            default -> throw new IllegalArgumentException();
        };
    }

    private JSONObject snapshot(boolean refresh, String root) throws Exception {
        if (!root.isEmpty() && !root.equals("selected") && !new Volumes(context).roots().containsKey(root)
                && snapshots.read(root) == null)
            throw new IllegalArgumentException();
        JSONObject saved = root.isEmpty() ? snapshots.read() : snapshots.read(root);
        return new JSONObject().put("schemaVersion", 1).put("access", Access.state(context))
                .put("version", context.getPackageManager().getPackageInfo(context.getPackageName(), 0).versionName)
                .put("volumes", new Volumes(context).list()).put("apps", packages.collect(refresh))
                .put("scan", saved == null ? JSONObject.NULL : saved).put("scans", snapshots.summaries())
                .put("progress", scanner.progress())
                .put("measuredAt", System.currentTimeMillis());
    }

    private JSONObject startScan(JSONObject args) throws Exception {
        String mode = args.optString("mode"), root = args.optString("root");
        if (!Set.of("quick", "deep").contains(mode)) throw new IllegalArgumentException();
        if (!root.equals("selected") && !new Volumes(context).roots().containsKey(root)) throw new IllegalArgumentException();
        if (root.equals("selected") ? !Access.state(context).getBoolean("tree") : !android.os.Environment.isExternalStorageManager())
            throw new SecurityException();
        if (!scanner.reserve()) throw new java.util.concurrent.RejectedExecutionException();
        scans.execute(() -> scanner.run(mode, root));
        return new JSONObject().put("started", true);
    }

    private String packageName(JSONObject args) throws Exception {
        String name = args.getString("package");
        if (name.length() > 255 || !name.matches("[a-zA-Z0-9_.]+")) throw new IllegalArgumentException();
        context.getPackageManager().getApplicationInfo(name, 0);
        return name;
    }

    private JSONObject uninstall(JSONObject args) throws Exception {
        String name = packageName(args);
        ApplicationInfo info = context.getPackageManager().getApplicationInfo(name, 0);
        if (name.equals(context.getPackageName()) || (info.flags & (ApplicationInfo.FLAG_SYSTEM |
                ApplicationInfo.FLAG_UPDATED_SYSTEM_APP)) != 0) throw new SecurityException();
        return open(new Intent(Intent.ACTION_DELETE, Uri.parse("package:" + name)));
    }

    private JSONObject open(Intent intent) throws Exception {
        return onUi(() -> activity.openSettings(intent));
    }

    private JSONObject onUi(Runnable action) throws Exception {
        activity.runOnUiThread(() -> { if (!closed) action.run(); });
        return new JSONObject().put("opened", true);
    }

    private void respond(JavaScriptReplyProxy reply, String id, JSONObject data, String error) {
        activity.runOnUiThread(() -> {
            if (closed) return;
            try {
                JSONObject response = new JSONObject().put("id", id).put("ok", error == null);
                response.put(error == null ? "data" : "error", error == null ? data : error);
                reply.postMessage(response.toString());
            } catch (org.json.JSONException exception) { throw new IllegalStateException(exception); }
        });
    }

    void backgrounded() { if (scanner.running()) scanner.cancel(); }
    @Override public void close() {
        closed = true; scanner.cancel(); requests.shutdownNow(); scans.shutdownNow();
        Thread cleanup = new Thread(() -> {
            try {
                if (requests.awaitTermination(5, TimeUnit.SECONDS) && scans.awaitTermination(5, TimeUnit.SECONDS))
                    snapshots.close();
            } catch (InterruptedException error) { Thread.currentThread().interrupt(); }
        }, "StorageLens-close");
        cleanup.setDaemon(true); cleanup.start();
    }
}
