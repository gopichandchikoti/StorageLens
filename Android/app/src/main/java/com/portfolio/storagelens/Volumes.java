package com.portfolio.storagelens;

import android.content.Context;
import android.os.Environment;
import android.os.StatFs;
import android.os.storage.StorageManager;
import android.os.storage.StorageVolume;
import org.json.JSONArray;
import org.json.JSONObject;
import java.io.File;
import java.util.LinkedHashMap;
import java.util.Map;

final class Volumes {
    private final Context context;
    Volumes(Context context) { this.context = context; }

    Map<String, File> roots() {
        Map<String, File> roots = new LinkedHashMap<>();
        StorageManager manager = context.getSystemService(StorageManager.class);
        for (StorageVolume volume : manager.getStorageVolumes()) {
            File root = volume.getDirectory();
            if (root != null && (Environment.MEDIA_MOUNTED.equals(volume.getState()) ||
                    Environment.MEDIA_MOUNTED_READ_ONLY.equals(volume.getState())))
                roots.put(volume.isPrimary() ? "primary" : volume.getUuid(), root);
        }
        return roots;
    }

    JSONArray list() throws Exception {
        JSONArray result = new JSONArray();
        StorageManager manager = context.getSystemService(StorageManager.class);
        for (StorageVolume volume : manager.getStorageVolumes()) {
            File root = volume.getDirectory();
            if (root == null || !root.exists()) continue;
            try {
                StatFs stats = new StatFs(root.getAbsolutePath());
                result.put(new JSONObject().put("id", volume.isPrimary() ? "primary" : volume.getUuid())
                        .put("label", volume.getDescription(context)).put("total", stats.getTotalBytes())
                        .put("free", stats.getAvailableBytes()).put("primary", volume.isPrimary())
                        .put("removable", volume.isRemovable()));
            } catch (IllegalArgumentException ignored) {
                // A volume can unmount between enumeration and measurement; omit stale capacity.
            }
        }
        return result;
    }
}
