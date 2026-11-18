package com.portfolio.storagelens;

import androidx.activity.ComponentActivity;
import androidx.activity.OnBackPressedCallback;
import android.content.Intent;
import android.net.Uri;
import android.os.Bundle;
import android.view.View;
import android.view.WindowInsets;
import android.webkit.WebResourceRequest;
import android.webkit.WebResourceResponse;
import android.webkit.WebView;
import android.webkit.WebViewClient;
import android.widget.TextView;
import android.widget.Toast;
import androidx.webkit.WebViewAssetLoader;
import androidx.webkit.WebViewCompat;
import androidx.webkit.WebViewFeature;
import java.io.ByteArrayInputStream;
import java.util.Set;

public final class MainActivity extends ComponentActivity {
    private static final int FOLDER_PICKER = 10;
    private WebView browser;
    private NativeRouter router;
    private Copy copy;
    WebView browserForTesting() { return browser; }

    @Override public void onCreate(Bundle state) {
        super.onCreate(state);
        try {
            copy = new Copy(this);
            if (!WebViewFeature.isFeatureSupported(WebViewFeature.WEB_MESSAGE_LISTENER)) {
                showFailure(copy.text("errors.webview")); return;
            }
            setupBrowser();
            getOnBackPressedDispatcher().addCallback(this, new OnBackPressedCallback(true) {
                @Override public void handleOnBackPressed() { navigateBack(); }
            });
        } catch (Exception error) { showFailure(getString(R.string.native_failure)); }
    }

    private void setupBrowser() {
        browser = new WebView(this);
        browser.setBackgroundColor(0xff131315);
        browser.getSettings().setJavaScriptEnabled(true);
        browser.getSettings().setAllowFileAccess(false);
        browser.getSettings().setAllowContentAccess(false);
        browser.getSettings().setBlockNetworkLoads(true);
        browser.getSettings().setDomStorageEnabled(false);
        browser.getSettings().setMediaPlaybackRequiresUserGesture(true);
        browser.getSettings().setMixedContentMode(android.webkit.WebSettings.MIXED_CONTENT_NEVER_ALLOW);
        browser.setOnApplyWindowInsetsListener((view, insets) -> {
            var bars = insets.getInsets(WindowInsets.Type.systemBars() | WindowInsets.Type.displayCutout());
            view.setPadding(bars.left, bars.top, bars.right, bars.bottom);
            return insets;
        });
        WebViewAssetLoader assets = new WebViewAssetLoader.Builder()
                .addPathHandler("/assets/", new WebViewAssetLoader.AssetsPathHandler(this)).build();
        browser.setWebViewClient(new WebViewClient() {
            @Override public WebResourceResponse shouldInterceptRequest(WebView view, WebResourceRequest request) {
                if (request.getUrl().getScheme().equals("https") &&
                        request.getUrl().getHost().equals("appassets.androidplatform.net")) {
                    WebResourceResponse response = assets.shouldInterceptRequest(request.getUrl());
                    if (response != null) return response;
                }
                return new WebResourceResponse("text/plain", "utf-8", 403, "Blocked", null,
                        new ByteArrayInputStream(new byte[0]));
            }
            @Override public boolean shouldOverrideUrlLoading(WebView view, WebResourceRequest request) {
                return !request.getUrl().toString().startsWith(NativeRouter.ORIGIN + "/assets/");
            }
        });
        router = new NativeRouter(this);
        WebViewCompat.addWebMessageListener(browser, "StorageLensNative", Set.of(NativeRouter.ORIGIN),
                (view, message, origin, main, reply) -> router.receive(message.getData(), origin.toString(), main, reply));
        setContentView(browser);
        browser.loadUrl(NativeRouter.ORIGIN + "/assets/index.html");
    }

    private void showFailure(String message) {
        TextView text = new TextView(this);
        text.setText(message); text.setTextColor(0xffeeeeee); text.setTextSize(18); text.setPadding(28, 48, 28, 28);
        text.setBackgroundColor(0xff131315); setContentView(text);
    }

    void openSettings(Intent intent) {
        try { startActivity(intent); }
        catch (android.content.ActivityNotFoundException | SecurityException error) {
            Toast.makeText(this, copy.text("errors.failed"), Toast.LENGTH_LONG).show();
        }
    }

    void chooseFolder() {
        Intent intent = new Intent(Intent.ACTION_OPEN_DOCUMENT_TREE);
        intent.addFlags(Intent.FLAG_GRANT_READ_URI_PERMISSION | Intent.FLAG_GRANT_PERSISTABLE_URI_PERMISSION);
        openForResult(intent, FOLDER_PICKER);
    }

    private void openForResult(Intent intent, int code) {
        try { startActivityForResult(intent, code); }
        catch (android.content.ActivityNotFoundException error) {
            Toast.makeText(this, copy.text("errors.failed"), Toast.LENGTH_LONG).show();
        }
    }

    @Override protected void onActivityResult(int request, int result, Intent data) {
        super.onActivityResult(request, result, data);
        if (request == FOLDER_PICKER && result == RESULT_OK && data != null && data.getData() != null) {
            Uri tree = data.getData();
            try {
                if (!android.provider.DocumentsContract.isTreeUri(tree)) throw new SecurityException();
                getContentResolver().takePersistableUriPermission(tree, Intent.FLAG_GRANT_READ_URI_PERMISSION);
                String previous = getSharedPreferences("access", MODE_PRIVATE).getString("tree", "");
                if (!previous.isEmpty() && !previous.equals(tree.toString())) {
                    try { getContentResolver().releasePersistableUriPermission(Uri.parse(previous), Intent.FLAG_GRANT_READ_URI_PERMISSION); }
                    catch (SecurityException ignored) { /* A previous grant may already be revoked. */ }
                }
                getSharedPreferences("access", MODE_PRIVATE).edit().putString("tree", tree.toString()).apply();
            } catch (SecurityException error) { Toast.makeText(this, copy.text("errors.permission"), Toast.LENGTH_LONG).show(); }
        }
        refreshPage();
    }

    void reviewMediaTrash(String id, String root, Snapshots snapshots) {
        try { MediaReview.request(this, id, root, snapshots); }
        catch (Exception error) { Toast.makeText(this, copy.text("files.noTrash"), Toast.LENGTH_LONG).show(); }
    }

    private void refreshPage() {
        if (browser != null) browser.evaluateJavascript("window.StorageLensRefresh?.()", null);
    }
    private void navigateBack() {
        if (browser != null) browser.evaluateJavascript("Boolean(window.StorageLensBack?.())",
                result -> { if (!"true".equals(result)) finish(); });
        else finish();
    }
    @Override protected void onResume() { super.onResume(); refreshPage(); }
    @Override protected void onStop() { super.onStop(); if (router != null) router.backgrounded(); }
    @Override protected void onDestroy() {
        if (router != null) router.close();
        if (browser != null) { browser.stopLoading(); browser.destroy(); }
        super.onDestroy();
    }
}
