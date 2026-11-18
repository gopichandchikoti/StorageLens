using System.IO;
using System.Text.Json;
using System.Windows;
using Microsoft.Web.WebView2.Core;
using Microsoft.Web.WebView2.Wpf;

namespace StorageLens.Desktop;

internal static class DesktopVerification
{
    public static async Task RunAsync(Window window, WebView2 browser, BackendSession backend, string directory)
    {
        Directory.CreateDirectory(directory);
        var core = browser.CoreWebView2;
        await WaitAsync(core, "!!document.querySelector('#scan-button:not(:disabled)')");
        await WaitAsync(core, "!!document.querySelector('.nav[data-view=security]')");
        var initial = window.WindowState.ToString();
        var wideViewportWidth=JsonSerializer.Deserialize<double>(await core.ExecuteScriptAsync("innerWidth"));
        await CaptureAsync(core, directory, "desktop-wide.png");
        await core.ExecuteScriptAsync("document.querySelector('[data-view=apps]').click()");
        await WaitAsync(core, "!!document.querySelector('#app-search') || !!document.querySelector('#apps .empty')");
        await CaptureAsync(core, directory, "applications.png");
        await core.ExecuteScriptAsync("document.querySelector('[data-view=security]').click()");
        await WaitAsync(core, "!!document.querySelector('#security [data-settings=security]')");
        await CaptureAsync(core, directory, "security-review.png");
        await core.ExecuteScriptAsync("document.querySelector('[data-view=moves]').click()");
        await WaitAsync(core, "!!document.querySelector('#moves [data-move-refresh]')");
        await CaptureAsync(core, directory, "move-suggestions.png");
        var moveFixture=Path.Combine(backend.DataDirectory,"move-ui-fixture.json");
        if (File.Exists(moveFixture))
        {
            using var fixture=JsonDocument.Parse(await File.ReadAllTextAsync(moveFixture));
            var source=fixture.RootElement.GetProperty("source").GetString()!;
            var parent=fixture.RootElement.GetProperty("parent").GetString()!;
            await core.ExecuteScriptAsync("chooser("+JsonSerializer.Serialize(new[]{source})+")");
            await WaitAsync(core,"document.querySelector('#move-dialog').open");
            await core.ExecuteScriptAsync("document.querySelector('#move-parent').value="+JsonSerializer.Serialize(parent)+";document.querySelector('#move-browse').click()");
            await WaitAsync(core,"!document.querySelector('#move-browser').hidden");
            await CaptureAsync(core,directory,"move-folder-picker.png");
            await core.ExecuteScriptAsync("document.querySelector('#move-check').click()");
            await WaitAsync(core,"!!document.querySelector('#move-start')");
            if (await core.ExecuteScriptAsync("document.querySelector('#move-start').disabled")!="true")
                throw new InvalidDataException("Move confirmation must start disabled.");
            await CaptureAsync(core,directory,"move-review.png");
            await core.ExecuteScriptAsync("document.querySelector('#move-dialog').close()");
        }
        await core.ExecuteScriptAsync("document.querySelector('[data-view=overview]').click();document.querySelector('#scan-button').click()");
        await WaitAsync(core, "document.querySelector('#scan-dialog').open");
        var scanModes = await core.ExecuteScriptAsync("[...document.querySelector('#scan-mode').options].map(o=>o.value)");
        await CaptureAsync(core, directory, "scan-dialog.png");
        await core.ExecuteScriptAsync("document.querySelector('#scan-dialog').close();document.querySelector('[data-view=home]').click()");
        await WaitAsync(core, "!!document.querySelector('.cap-home-hero')");
        await CaptureAsync(core, directory, "home.png");
        window.WindowState = WindowState.Normal;
        // Let WPF finish restoring native bounds before applying the smaller size.
        await window.Dispatcher.InvokeAsync(() => window.UpdateLayout(),
            System.Windows.Threading.DispatcherPriority.ApplicationIdle);
        var targetWidth=Math.Max(window.MinWidth,Math.Min(850,SystemParameters.WorkArea.Width-100));
        window.Width = targetWidth; window.Height = 680;
        window.UpdateLayout();
        // WPF measures DIPs; WebView's CSS width can differ at non-default display
        // scaling. Require both a real native resize and a smaller web viewport.
        await WaitAsync(core, "innerWidth < "+(wideViewportWidth-1).ToString(System.Globalization.CultureInfo.InvariantCulture));
        if(window.ActualWidth>targetWidth+1)throw new InvalidDataException("Native window did not resize.");
        var narrowViewportWidth=JsonSerializer.Deserialize<double>(await core.ExecuteScriptAsync("innerWidth"));
        var overflow = await core.ExecuteScriptAsync("document.documentElement.scrollWidth > innerWidth+1");
        if (overflow == "true") throw new InvalidDataException("Narrow window has horizontal overflow.");
        await CaptureAsync(core, directory, "desktop-narrow.png");
        var report = new { initialWindowState = initial, backendPid = backend.ProcessId,
            browserVersion = core.Environment.BrowserVersionString,
            modes = JsonSerializer.Deserialize<string[]>(scanModes), narrowOverflow = false,
            wideViewportWidth,narrowViewportWidth,narrowWindowWidth=window.ActualWidth,
            version = AppText.Version, checkedAt = DateTimeOffset.Now, completed = true };
        await File.WriteAllTextAsync(Path.Combine(directory, "verified.json"),
            JsonSerializer.Serialize(report, new JsonSerializerOptions { WriteIndented = true }));
        window.Close();
    }

    private static async Task WaitAsync(CoreWebView2 core, string predicate)
    {
        var deadline = DateTimeOffset.UtcNow.AddSeconds(40);
        while (DateTimeOffset.UtcNow < deadline)
        {
            if (await core.ExecuteScriptAsync("Boolean(" + predicate + ")") == "true") return;
            await Task.Delay(100);
        }
        throw new TimeoutException("Desktop UI readiness condition failed: " + predicate);
    }

    private static async Task CaptureAsync(CoreWebView2 core, string directory, string name)
    {
        await using var output = File.Create(Path.Combine(directory, name));
        await core.CapturePreviewAsync(CoreWebView2CapturePreviewImageFormat.Png, output);
    }
}
