package com.portfolio.storagelens;

import android.app.usage.StorageStats;
import android.app.usage.StorageStatsManager;
import android.app.usage.UsageStats;
import android.app.usage.UsageStatsManager;
import android.content.Context;
import android.content.pm.ApplicationInfo;
import android.content.pm.PackageInfo;
import android.content.pm.PackageManager;
import android.os.Process;
import android.os.storage.StorageManager;
import org.json.JSONArray;
import org.json.JSONObject;
import java.io.File;
import java.util.ArrayList;
import java.util.Comparator;
import java.util.HashMap;
import java.util.List;
import java.util.Map;

final class Packages {
    private final Context context;
    private JSONArray cached;
    private long measured;
    Packages(Context context) { this.context = context; }

    JSONArray collect(boolean refresh) throws Exception {
        if (!refresh && cached != null && System.currentTimeMillis() - measured < 60000) return cached;
        PackageManager manager = context.getPackageManager();
        boolean usage = Access.usage(context);
        Map<String, UsageStats> lastUse = usage ? lastUse() : new HashMap<>();
        List<JSONObject> entries = new ArrayList<>();
        for (ApplicationInfo info : manager.getInstalledApplications(PackageManager.MATCH_DISABLED_COMPONENTS)) {
            if (Thread.currentThread().isInterrupted()) throw new InterruptedException();
            try { entries.add(describe(info, manager, usage, lastUse.get(info.packageName))); }
            catch (PackageManager.NameNotFoundException ignored) { /* App was removed during enumeration. */ }
            if (entries.size() >= 5000) break;
        }
        entries.sort(Comparator.comparingLong((JSONObject value) -> value.optLong("totalBytes", -1)).reversed());
        cached = new JSONArray(entries);
        measured = System.currentTimeMillis();
        return cached;
    }

    private JSONObject describe(ApplicationInfo info, PackageManager manager, boolean usage, UsageStats last) throws Exception {
        PackageInfo pkg = manager.getPackageInfo(info.packageName, 0);
        boolean system = (info.flags & (ApplicationInfo.FLAG_SYSTEM | ApplicationInfo.FLAG_UPDATED_SYSTEM_APP)) != 0;
        String installer = null;
        try { installer = manager.getInstallSourceInfo(info.packageName).getInstallingPackageName(); }
        catch (PackageManager.NameNotFoundException ignored) { /* Package may have just changed. */ }
        long apk = new File(info.sourceDir).length();
        if (info.splitSourceDirs != null) for (String split : info.splitSourceDirs) apk += new File(split).length();
        JSONObject value = new JSONObject().put("package", info.packageName).put("name", info.loadLabel(manager).toString())
                .put("version", pkg.versionName == null ? "" : pkg.versionName)
                .put("system", system).put("enabled", info.enabled)
                .put("uid", info.uid)
                .put("launcher", manager.getLaunchIntentForPackage(info.packageName) != null)
                .put("installer", installer == null ? JSONObject.NULL : installer)
                .put("updated", pkg.lastUpdateTime).put("apkBytes", apk)
                .put("self", context.getPackageName().equals(info.packageName))
                .put("appBytes", JSONObject.NULL).put("dataBytes", JSONObject.NULL)
                .put("cacheBytes", JSONObject.NULL).put("totalBytes", JSONObject.NULL)
                .put("lastUse", last == null || last.getLastTimeUsed() == 0 ? JSONObject.NULL : last.getLastTimeUsed())
                .put("stats", usage ? "unavailable" : "permission");
        if (usage) {
            try {
                StorageStatsManager stats = context.getSystemService(StorageStatsManager.class);
                StorageStats size = stats.queryStatsForPackage(info.storageUuid == null ? StorageManager.UUID_DEFAULT :
                        info.storageUuid, info.packageName, Process.myUserHandle());
                value.put("appBytes", size.getAppBytes()).put("dataBytes", size.getDataBytes())
                        .put("cacheBytes", size.getCacheBytes()).put("totalBytes", size.getAppBytes() + size.getDataBytes())
                        .put("stats", "available");
            } catch (java.io.IOException | PackageManager.NameNotFoundException | SecurityException error) {
                value.put("stats", "unavailable");
            }
        }
        return value;
    }

    JSONObject details(String name) throws Exception {
        PackageManager manager = context.getPackageManager();
        PackageInfo pkg = manager.getPackageInfo(name, PackageManager.GET_PERMISSIONS);
        JSONArray permissions = new JSONArray();
        if (pkg.requestedPermissions != null) for (int i = 0; i < pkg.requestedPermissions.length; i++) {
            if ((pkg.requestedPermissionsFlags[i] & PackageInfo.REQUESTED_PERMISSION_GRANTED) == 0) continue;
            var permission = manager.getPermissionInfo(pkg.requestedPermissions[i], 0);
            if ((permission.protectionLevel & 0xf) == android.content.pm.PermissionInfo.PROTECTION_DANGEROUS)
                permissions.put(permission.loadLabel(manager).toString());
        }
        return new JSONObject().put("permissions", permissions);
    }

    private Map<String, UsageStats> lastUse() {
        UsageStatsManager usage = context.getSystemService(UsageStatsManager.class);
        long now = System.currentTimeMillis();
        return usage.queryAndAggregateUsageStats(now - 180L * 86400000, now);
    }
}
