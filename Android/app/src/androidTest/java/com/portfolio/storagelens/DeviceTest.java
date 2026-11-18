package com.portfolio.storagelens;

import android.content.Context;
import android.content.Intent;
import android.content.pm.PackageManager;
import android.graphics.Bitmap;
import androidx.test.ext.junit.runners.AndroidJUnit4;
import androidx.test.platform.app.InstrumentationRegistry;
import org.json.JSONObject;
import org.junit.Test;
import org.junit.runner.RunWith;
import java.io.File;
import java.io.FileOutputStream;
import java.nio.file.Files;
import java.util.Arrays;
import java.util.Map;
import java.util.UUID;
import java.util.concurrent.CountDownLatch;
import java.util.concurrent.TimeUnit;
import java.util.concurrent.atomic.AtomicReference;
import static org.junit.Assert.*;

@RunWith(AndroidJUnit4.class)
public class DeviceTest {
    private final android.app.Instrumentation instrumentation = InstrumentationRegistry.getInstrumentation();
    private final Context context = instrumentation.getTargetContext();

    private void shell(String command) throws Exception {
        try (var descriptor = instrumentation.getUiAutomation().executeShellCommand(command);
             var stream = new java.io.FileInputStream(descriptor.getFileDescriptor())) {
            byte[] buffer = new byte[4096];
            int total = 0, read;
            while ((read = stream.read(buffer)) >= 0) { total += read; if (total > 65536) throw new AssertionError("shell-output"); }
        }
    }

    @Test public void packagedPermissionsAndAppStatistics() throws Exception {
        var pkg = context.getPackageManager().getPackageInfo(context.getPackageName(), PackageManager.GET_PERMISSIONS);
        assertFalse(Arrays.asList(pkg.requestedPermissions).contains("android.permission.INTERNET"));
        assertEquals(0, pkg.applicationInfo.flags & android.content.pm.ApplicationInfo.FLAG_ALLOW_BACKUP);
        shell("appops set " + context.getPackageName() + " GET_USAGE_STATS ignore");
        assertFalse(Access.usage(context));
        var denied = new Packages(context).collect(true);
        assertTrue(denied.length() > 0);
        assertTrue(denied.getJSONObject(0).isNull("totalBytes"));
        shell("appops set " + context.getPackageName() + " GET_USAGE_STATS allow");
        assertTrue(Access.usage(context));
        var entries = new Packages(context).collect(true);
        boolean selfMeasured = false;
        for (int i=0; i<entries.length(); i++) {
            JSONObject app = entries.getJSONObject(i);
            if (app.getString("package").equals(context.getPackageName())) {
                assertEquals("available", app.getString("stats"));
                assertEquals(app.getLong("appBytes") + app.getLong("dataBytes"), app.getLong("totalBytes"));
                assertTrue(app.getLong("apkBytes") > 0);
                selfMeasured = true;
            }
        }
        assertTrue(selfMeasured);
    }

    @Test public void quickDeepCancellationAndIndependentRoots() throws Exception {
        shell("appops set " + context.getPackageName() + " MANAGE_EXTERNAL_STORAGE allow");
        String database = "fixture-"+ UUID.randomUUID()+".db";
        File root = new File(context.getCacheDir(), "scan-"+UUID.randomUUID());
        assertTrue(root.mkdirs());
        File nested = new File(root, "one/two/three"); assertTrue(nested.mkdirs());
        Files.write(new File(root,"visible.bin").toPath(),new byte[8192]);
        Files.write(new File(nested,"deep.bin").toPath(),new byte[16384]);
        try (Snapshots snapshots = new Snapshots(context,database)) {
            StorageScanner scanner = new StorageScanner(context,snapshots,()->Map.of("fixture",root,"other",root));
            assertTrue(scanner.reserve()); scanner.run("quick","fixture");
            assertEquals("complete",scanner.progress().getString("status"));
            assertEquals(1,snapshots.read("fixture").getLong("files"));
            assertTrue(snapshots.read("fixture").getBoolean("limited"));
            assertTrue(scanner.reserve()); scanner.run("deep","fixture");
            assertEquals(2,snapshots.read("fixture").getLong("files"));
            long expected = android.system.Os.lstat(new File(root,"visible.bin").getPath()).st_blocks * 512
                    + android.system.Os.lstat(new File(nested,"deep.bin").getPath()).st_blocks * 512;
            assertEquals(expected,snapshots.read("fixture").getLong("bytes"));
            assertTrue(scanner.reserve()); scanner.run("deep","other");
            assertNotNull(snapshots.read("fixture")); assertNotNull(snapshots.read("other"));
            long original = snapshots.read("fixture").getLong("measuredAt");
            assertTrue(scanner.reserve()); scanner.cancel(); scanner.run("deep","fixture");
            assertEquals("cancelled",scanner.progress().getString("status"));
            assertEquals(original,snapshots.read("fixture").getLong("measuredAt"));
        } finally {
            context.deleteDatabase(database);
            try(var paths=Files.walk(root.toPath())) { paths.sorted(java.util.Comparator.reverseOrder()).forEach(path->{
                try { Files.delete(path); } catch(java.io.IOException error) {throw new IllegalStateException(error);}
            }); }
        }
    }

    private String javascript(MainActivity activity,String script) throws Exception {
        CountDownLatch done=new CountDownLatch(1); AtomicReference<String> result=new AtomicReference<>();
        instrumentation.runOnMainSync(()->activity.browserForTesting().evaluateJavascript(script,value->{result.set(value);done.countDown();}));
        assertTrue(done.await(10, TimeUnit.SECONDS)); return result.get();
    }

    private void waitFor(MainActivity activity,String predicate) throws Exception {
        long deadline=System.currentTimeMillis()+60000;
        while(System.currentTimeMillis()<deadline) {
            if("true".equals(javascript(activity,"Boolean("+predicate+")"))) return;
            Thread.sleep(100);
        }
        fail("UI readiness failed: "+predicate);
    }

    private void screenshot(MainActivity activity,String name) throws Exception {
        File folder=new File(context.getExternalFilesDir(null),"verification"); assertTrue(folder.exists()||folder.mkdirs());
        AtomicReference<Bitmap> captured=new AtomicReference<>();
        CountDownLatch ready=new CountDownLatch(1); AtomicReference<Integer> status=new AtomicReference<>();
        instrumentation.runOnMainSync(()->{
            ViewSize size=new ViewSize(activity.getWindow().getDecorView().getWidth(),activity.getWindow().getDecorView().getHeight());
            Bitmap bitmap=Bitmap.createBitmap(size.width,size.height,Bitmap.Config.ARGB_8888); captured.set(bitmap);
            // DOM readiness precedes compositor presentation. Capture only after
            // WebView acknowledges the visual update and presents its next frame.
            activity.browserForTesting().postVisualStateCallback(System.nanoTime(),new android.webkit.WebView.VisualStateCallback(){
                @Override public void onComplete(long requestId){
                    activity.browserForTesting().postOnAnimation(()->activity.browserForTesting().postOnAnimation(()->
                        android.view.PixelCopy.request(activity.getWindow(),bitmap,result->{status.set(result);ready.countDown();},
                            new android.os.Handler(android.os.Looper.getMainLooper()))));
                }
            });
        });
        assertTrue(ready.await(10,TimeUnit.SECONDS)); assertEquals(Integer.valueOf(android.view.PixelCopy.SUCCESS),status.get());
        Bitmap bitmap=captured.get();
        try(var output=new FileOutputStream(new File(folder,name+".png"))) { assertTrue(bitmap.compress(Bitmap.CompressFormat.PNG,100,output)); }
        bitmap.recycle();
    }
    private static final class ViewSize {
        final int width,height;
        ViewSize(int width,int height){this.width=width;this.height=height;}
    }

    @Test public void offlineUiAndPermissionScreens() throws Exception {
        shell("cmd statusbar collapse");
        shell("appops set "+context.getPackageName()+" GET_USAGE_STATS ignore");
        MainActivity activity=(MainActivity)instrumentation.startActivitySync(new Intent(context,MainActivity.class)
                .addFlags(Intent.FLAG_ACTIVITY_NEW_TASK));
        try {
            waitFor(activity,"document.querySelector('#navigation button') && document.querySelector('#screen h1')");
            assertEquals("false",javascript(activity,"document.documentElement.scrollWidth > innerWidth+1"));
            screenshot(activity,"android-overview");
            javascript(activity,"document.querySelector('[data-nav=access]').click()");
            waitFor(activity,"document.querySelector('.permission')"); screenshot(activity,"android-access");
            javascript(activity,"document.querySelector('[data-nav=apps]').click()");
            waitFor(activity,"document.querySelector('#app-search')"); screenshot(activity,"android-apps");
            javascript(activity,"document.querySelector('[data-nav=review]').click()");
            waitFor(activity,"document.querySelector('[data-native=securitySettings]')"); screenshot(activity,"android-review");
            assertEquals("false",javascript(activity,"document.documentElement.scrollWidth > innerWidth+1"));
        } finally { instrumentation.runOnMainSync(activity::finish); }
    }

    @Test public void grantedAppDetailsAndLandscape() throws Exception {
        shell("cmd statusbar collapse");
        shell("appops set "+context.getPackageName()+" GET_USAGE_STATS allow");
        MainActivity activity=(MainActivity)instrumentation.startActivitySync(new Intent(context,MainActivity.class)
                .addFlags(Intent.FLAG_ACTIVITY_NEW_TASK));
        try {
            waitFor(activity,"typeof data !== 'undefined' && data && data.access.usage");
            javascript(activity,"document.querySelector('[data-nav=apps]').click()");
            waitFor(activity,"document.querySelector('#app-search')");
            javascript(activity,"document.querySelector('#app-search').value='"+context.getPackageName()+"';document.querySelector('#app-search').dispatchEvent(new Event('input'))");
            waitFor(activity,"document.querySelector('[data-package]')");
            javascript(activity,"document.querySelector('[data-package]').click()");
            waitFor(activity,"document.querySelector('#details').open && document.querySelector('#permissions').textContent !== t('common.loading')");
            assertEquals("true",javascript(activity,"data.apps.find(a=>a.self).totalBytes > 0"));
            assertEquals("true",javascript(activity,"!!document.querySelector('[data-native=appSettings]')"));
            assertEquals("false",javascript(activity,"!!document.querySelector('[data-native=uninstall]')"));
            screenshot(activity,"android-app-details-granted");
            javascript(activity,"document.querySelector('#details').close();document.querySelector('[data-nav=overview]').click()");
            instrumentation.runOnMainSync(()->activity.setRequestedOrientation(android.content.pm.ActivityInfo.SCREEN_ORIENTATION_LANDSCAPE));
            waitFor(activity,"innerWidth > innerHeight");
            assertEquals("false",javascript(activity,"document.documentElement.scrollWidth > innerWidth+1"));
            screenshot(activity,"android-landscape");
            javascript(activity,"document.querySelector('[data-scan]').click()");
            waitFor(activity,"document.querySelector('#scan-dialog').open");
            assertEquals("2",javascript(activity,"document.querySelectorAll('input[name=mode]').length"));
            screenshot(activity,"android-scan-options");
        } finally {
            instrumentation.runOnMainSync(()->{activity.setRequestedOrientation(android.content.pm.ActivityInfo.SCREEN_ORIENTATION_UNSPECIFIED);activity.finish();});
        }
    }
}
