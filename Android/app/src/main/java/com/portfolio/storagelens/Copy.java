package com.portfolio.storagelens;

import android.content.Context;
import org.json.JSONObject;
import java.io.InputStream;
import java.io.ByteArrayOutputStream;
import java.nio.charset.StandardCharsets;

final class Copy {
    final JSONObject model;
    private final JSONObject values;

    Copy(Context context) throws Exception {
        try (InputStream stream = context.getAssets().open("public/storagelens.model.json")) {
            ByteArrayOutputStream output = new ByteArrayOutputStream();
            byte[] buffer = new byte[4096];
            int count;
            while ((count = stream.read(buffer)) != -1) {
                if (output.size() + count > 128 * 1024) throw new IllegalStateException("model-size");
                output.write(buffer, 0, count);
            }
            model = new JSONObject(output.toString(StandardCharsets.UTF_8.name()));
        }
        if (model.getInt("schemaVersion") != 1) throw new IllegalStateException("model-schema");
        values = model.getJSONObject("locales").getJSONObject(model.getString("defaultLocale"));
    }

    String text(String key) { return values.optString(key, values.optString("errors.failed")); }
}
