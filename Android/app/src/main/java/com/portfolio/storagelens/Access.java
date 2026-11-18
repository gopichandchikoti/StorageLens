package com.portfolio.storagelens;

import android.app.AppOpsManager;
import android.content.Context;
import android.os.Environment;
import android.os.Process;
import org.json.JSONObject;

final class Access {
    private Access() { }

    static boolean usage(Context context) {
        AppOpsManager ops = context.getSystemService(AppOpsManager.class);
        return ops != null && ops.unsafeCheckOpNoThrow(AppOpsManager.OPSTR_GET_USAGE_STATS,
                Process.myUid(), context.getPackageName()) == AppOpsManager.MODE_ALLOWED;
    }

    static JSONObject state(Context context) throws Exception {
        String tree = context.getSharedPreferences("access", Context.MODE_PRIVATE).getString("tree", "");
        boolean readable = context.getContentResolver().getPersistedUriPermissions().stream()
                .anyMatch(grant -> grant.isReadPermission() && grant.getUri().toString().equals(tree));
        return new JSONObject().put("usage", usage(context))
                .put("files", Environment.isExternalStorageManager()).put("tree", readable)
                .put("android", android.os.Build.VERSION.RELEASE).put("api", android.os.Build.VERSION.SDK_INT);
    }
}
