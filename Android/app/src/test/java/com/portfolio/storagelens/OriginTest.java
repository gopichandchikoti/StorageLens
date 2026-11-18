package com.portfolio.storagelens;

import org.junit.Test;
import static org.junit.Assert.*;

public class OriginTest {
    @Test public void nativeBridgeRejectsForeignOriginsAndSubframes() {
        assertTrue(NativeRouter.trusted("https://appassets.androidplatform.net", true));
        assertFalse(NativeRouter.trusted("https://appassets.androidplatform.net", false));
        assertFalse(NativeRouter.trusted("http://appassets.androidplatform.net", true));
        assertFalse(NativeRouter.trusted("https://appassets.androidplatform.net.evil.example", true));
        assertFalse(NativeRouter.trusted("file:///android_asset/index.html", true));
        assertFalse(NativeRouter.trusted("https://example.com", true));
    }
}
