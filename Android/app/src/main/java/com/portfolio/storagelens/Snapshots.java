package com.portfolio.storagelens;

import android.content.Context;
import android.content.ContentValues;
import android.database.Cursor;
import android.database.sqlite.SQLiteDatabase;
import android.database.sqlite.SQLiteOpenHelper;
import org.json.JSONArray;
import org.json.JSONObject;
import java.nio.charset.StandardCharsets;

final class Snapshots extends SQLiteOpenHelper {
    private static final int LIMIT = 8 * 1024 * 1024;
    Snapshots(Context context) { this(context, "storagelens.db"); }
    Snapshots(Context context, String database) { super(context, database, null, 1); }

    @Override public void onCreate(SQLiteDatabase database) {
        database.execSQL("CREATE TABLE snapshots(root TEXT PRIMARY KEY, measured INTEGER NOT NULL, bytes INTEGER," +
                " files INTEGER, folders INTEGER, mode TEXT, body TEXT NOT NULL)");
    }
    @Override public void onUpgrade(SQLiteDatabase database, int old, int next) {
        throw new IllegalStateException("unsupported-schema-upgrade");
    }

    synchronized JSONObject read() throws Exception { return read(""); }
    synchronized JSONObject read(String root) throws Exception {
        try (Cursor cursor = getReadableDatabase().query("snapshots", new String[]{"body"},
                root.isEmpty() ? null : "root=?", root.isEmpty() ? null : new String[]{root},
                null, null, "measured DESC", "1")) {
            if (!cursor.moveToFirst()) return null;
            JSONObject snapshot = new JSONObject(cursor.getString(0));
            if (snapshot.getInt("schemaVersion") != 1) throw new IllegalStateException("snapshot-schema");
            return snapshot;
        }
    }

    synchronized JSONArray summaries() throws Exception {
        JSONArray result = new JSONArray();
        try (Cursor cursor = getReadableDatabase().query("snapshots", new String[]{"root", "measured", "bytes", "files", "mode"},
                null, null, null, null, "measured DESC", "16")) {
            while (cursor.moveToNext()) result.put(new JSONObject().put("root", cursor.getString(0))
                    .put("measuredAt", cursor.getLong(1)).put("bytes", cursor.getLong(2))
                    .put("files", cursor.getLong(3)).put("mode", cursor.getString(4)));
        }
        return result;
    }

    synchronized void save(JSONObject snapshot) throws Exception {
        String body = snapshot.toString();
        if (body.getBytes(StandardCharsets.UTF_8).length > LIMIT) throw new IllegalStateException("snapshot-limit");
        SQLiteDatabase database = getWritableDatabase();
        database.beginTransaction();
        try {
            ContentValues values = new ContentValues();
            values.put("root", snapshot.getString("root")); values.put("measured", snapshot.getLong("measuredAt"));
            values.put("bytes", snapshot.getLong("bytes")); values.put("files", snapshot.getLong("files"));
            values.put("mode", snapshot.getString("mode")); values.put("body", body);
            if (database.insertWithOnConflict("snapshots", null, values, SQLiteDatabase.CONFLICT_REPLACE) == -1)
                throw new IllegalStateException("snapshot-write");
            database.execSQL("DELETE FROM snapshots WHERE root NOT IN (SELECT root FROM snapshots ORDER BY measured DESC LIMIT 16)");
            database.setTransactionSuccessful();
        } finally { database.endTransaction(); }
    }
}
