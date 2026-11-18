package com.portfolio.storagelens;

import android.app.Activity;
import android.content.ContentUris;
import android.database.Cursor;
import android.net.Uri;
import android.os.Environment;
import android.provider.MediaStore;
import org.json.JSONArray;
import org.json.JSONObject;
import java.io.File;
import java.util.List;

final class MediaReview {
    private MediaReview() { }
    static void request(Activity activity, String id, String rootId, Snapshots snapshots) throws Exception {
        if (!Environment.isExternalStorageManager() || id.length() > 64) throw new SecurityException();
        JSONObject snapshot = snapshots.read(rootId);
        if (snapshot == null) throw new IllegalArgumentException();
        JSONArray files = snapshot.getJSONArray("largeFiles");
        JSONObject record = null;
        for (int i = 0; i < files.length(); i++)
            if (files.getJSONObject(i).getString("id").equals(id)) record = files.getJSONObject(i);
        if (record == null || record.getString("path").isEmpty()) throw new IllegalArgumentException();
        File target = new File(record.getString("path"));
        File root = new Volumes(activity).roots().get(snapshot.getString("root"));
        if (root == null || !target.isFile() || !target.getCanonicalPath().startsWith(root.getCanonicalPath() + "/") ||
                !target.getCanonicalPath().equals(target.getAbsolutePath()) ||
                target.length() != record.getLong("logical") || target.lastModified() != record.getLong("modified"))
            throw new SecurityException();
        Uri collection = MediaStore.Files.getContentUri("external");
        Uri media = null;
        try (Cursor cursor = activity.getContentResolver().query(collection,
                new String[]{MediaStore.Files.FileColumns._ID, MediaStore.Files.FileColumns.MEDIA_TYPE},
                MediaStore.Files.FileColumns.DATA + "=?", new String[]{target.getCanonicalPath()}, null)) {
            if (cursor != null && cursor.moveToFirst() && cursor.getInt(1) != MediaStore.Files.FileColumns.MEDIA_TYPE_NONE)
                media = ContentUris.withAppendedId(collection, cursor.getLong(0));
        }
        if (media == null) throw new IllegalArgumentException();
        var consent = MediaStore.createTrashRequest(activity.getContentResolver(), List.of(media), true);
        activity.startIntentSenderForResult(consent.getIntentSender(), 11, null, 0, 0, 0);
    }
}
