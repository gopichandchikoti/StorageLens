using System.ComponentModel;
using System.Diagnostics;
using System.IO;
using System.Net;
using System.Text.Json;
using System.Windows;
using System.Windows.Controls;
using System.Windows.Media;
using Microsoft.Web.WebView2.Core;
using Microsoft.Web.WebView2.Wpf;
using Microsoft.Win32;

namespace StorageLens.Desktop;

internal sealed class MainWindow : Window
{
    private readonly BackendSession backend;
    private readonly CommandLine options;
    private readonly WebView2 browser = new();
    private readonly TextBlock status = new();
    private readonly Grid root = new();
    private bool allowClose, closing, verificationStarted;

    public MainWindow(CommandLine options)
    {
        this.options = options;
        backend = new(options.DataDirectory);
        Title = AppText.T("windows.title");
        MinWidth = Math.Min(760, SystemParameters.WorkArea.Width);
        MinHeight = Math.Min(520, SystemParameters.WorkArea.Height);
        Width = Math.Clamp(1440, MinWidth, SystemParameters.WorkArea.Width);
        Height = Math.Clamp(960, MinHeight, SystemParameters.WorkArea.Height);
        WindowStartupLocation = WindowStartupLocation.CenterScreen;
        WindowState = WindowState.Maximized;
        Background = new SolidColorBrush(Color.FromRgb(19, 19, 21));
        Foreground = Brushes.White;
        root.RowDefinitions.Add(new() { Height = GridLength.Auto });
        root.RowDefinitions.Add(new());
        root.Children.Add(CreateMenu());
        Grid.SetRow(browser, 1); root.Children.Add(browser);
        status.Text = AppText.T("windows.loading");
        status.HorizontalAlignment = HorizontalAlignment.Center;
        status.VerticalAlignment = VerticalAlignment.Center;
        status.Foreground = Brushes.LightGray;
        status.TextWrapping = TextWrapping.Wrap;
        status.MaxWidth = 600;
        status.Margin = new Thickness(30);
        Grid.SetRow(status, 1); root.Children.Add(status);
        Content = root;
        SourceInitialized += (_, _) => NativeChrome.Apply(this);
        RestoreBoundsFromDisk();
        Loaded += async (_, _) => await InitializeAsync();
        Closing += OnClosing;
        Closed += (_, _) => { browser.Dispose(); backend.Dispose(); };
    }

    private Menu CreateMenu()
    {
        var menu = new Menu { Background = new SolidColorBrush(Color.FromRgb(25, 25, 28)), Foreground = Brushes.White };
        var file = new MenuItem { Header = AppText.T("windows.file") };
        file.Items.Add(Item("windows.existingData", OpenExistingData));
        file.Items.Add(new Separator());
        file.Items.Add(Item("windows.close", Close));
        var view = new MenuItem { Header = AppText.T("windows.view") };
        view.Items.Add(Item("windows.zoomIn", () => browser.ZoomFactor = Math.Min(2, browser.ZoomFactor + .1)));
        view.Items.Add(Item("windows.zoomOut", () => browser.ZoomFactor = Math.Max(.7, browser.ZoomFactor - .1)));
        view.Items.Add(Item("windows.resetZoom", () => browser.ZoomFactor = 1));
        var help = new MenuItem { Header = AppText.T("windows.help") };
        help.Items.Add(Item("windows.about", () => MessageBox.Show(this,
            AppText.T("windows.aboutBody", ("version", AppText.Version)), AppText.T("app.name"))));
        help.Items.Add(Item("windows.logs", () => Process.Start(new ProcessStartInfo("explorer.exe")
            { ArgumentList = { backend.DataDirectory }, UseShellExecute = true })));
        menu.Items.Add(file); menu.Items.Add(view); menu.Items.Add(help);
        return menu;
    }

    private static MenuItem Item(string key, Action action)
    {
        var item = new MenuItem { Header = AppText.T(key) };
        item.Click += (_, _) => action();
        return item;
    }

    private void OpenExistingData()
    {
        var picker = new OpenFolderDialog { Title = AppText.T("windows.existingData") };
        if (picker.ShowDialog(this) != true) return;
        var path = Path.GetFullPath(picker.FolderName);
        if (!File.Exists(Path.Combine(path, "storage.sqlite3")))
        {
            MessageBox.Show(this, AppText.T("windows.invalidData"), AppText.T("app.name"));
            return;
        }
        var start = new ProcessStartInfo(Environment.ProcessPath!) { UseShellExecute = false };
        start.ArgumentList.Add("--data-dir"); start.ArgumentList.Add(path);
        Process.Start(start);
        Close();
    }

    private async Task InitializeAsync()
    {
        try
        {
            _ = CoreWebView2Environment.GetAvailableBrowserVersionString();
            await backend.StartAsync();
            var profile = Path.Combine(backend.DataDirectory, "webview-profile");
            var environment = await CoreWebView2Environment.CreateAsync(userDataFolder: profile);
            await browser.EnsureCoreWebView2Async(environment);
            ConfigureBrowser();
            browser.CoreWebView2.Navigate(backend.Origin!.ToString());
        }
        catch (WebView2RuntimeNotFoundException)
        {
            status.Text = AppText.T("windows.runtime");
            var link = new Button { Content = AppText.T("windows.runtimeLink"), Margin = new Thickness(20), Padding = new Thickness(15) };
            link.Click += (_, _) => Process.Start(new ProcessStartInfo(
                "https://developer.microsoft.com/microsoft-edge/webview2/") { UseShellExecute = true });
            link.VerticalAlignment = VerticalAlignment.Bottom;
            Grid.SetRow(link, 1); root.Children.Add(link);
            await VerificationFailureAsync("webview-runtime-unavailable");
        }
        catch (Exception error)
        {
            Log(error);
            status.Text = AppText.T("windows.launchFailure", ("reason", error.GetType().Name));
            await VerificationFailureAsync("startup-failed");
        }
    }

    private void ConfigureBrowser()
    {
        var core = browser.CoreWebView2;
        core.Settings.AreDevToolsEnabled = false;
        core.Settings.AreDefaultContextMenusEnabled = false;
        core.Settings.IsStatusBarEnabled = false;
        core.Settings.IsPasswordAutosaveEnabled = false;
        core.Settings.IsGeneralAutofillEnabled = false;
        var cookie = core.CookieManager.CreateCookie("StorageLensSession", backend.Secret, "127.0.0.1", "/");
        cookie.IsHttpOnly = true;
        cookie.SameSite = CoreWebView2CookieSameSiteKind.Strict;
        core.CookieManager.AddOrUpdateCookie(cookie);
        core.NavigationStarting += (_, e) => e.Cancel = !SameOrigin(e.Uri);
        core.NewWindowRequested += (_, e) => e.Handled = true;
        core.WebMessageReceived += (_, e) =>
        {
            if (!SameOrigin(e.Source) || e.WebMessageAsJson.Length > 200) return;
            try
            {
                using var message = JsonDocument.Parse(e.WebMessageAsJson);
                if (message.RootElement.TryGetProperty("action", out var action) && action.GetString() == "close") Close();
            }
            catch (JsonException) { /* Reject malformed messages without granting any capability. */ }
        };
        core.PermissionRequested += (_, e) => e.State = CoreWebView2PermissionState.Deny;
        core.AddWebResourceRequestedFilter("*", CoreWebView2WebResourceContext.All);
        core.WebResourceRequested += (_, e) =>
        {
            if (!SameOrigin(e.Request.Uri) && !e.Request.Uri.StartsWith("data:", StringComparison.Ordinal))
                e.Response = core.Environment.CreateWebResourceResponse(Stream.Null, 403, "Blocked", "");
        };
        core.DownloadStarting += (_, e) =>
        {
            if (!SameOrigin(e.DownloadOperation.Uri) || !new Uri(e.DownloadOperation.Uri).AbsolutePath.Equals("/api/export"))
            { e.Cancel = true; return; }
            var dialog = new SaveFileDialog { FileName = "StorageLens.csv", DefaultExt = ".csv", Filter = "CSV|*.csv" };
            if (dialog.ShowDialog(this) != true) { e.Cancel = true; return; }
            e.ResultFilePath = dialog.FileName;
        };
        core.NavigationCompleted += async (_, e) =>
        {
            if (!e.IsSuccess) { status.Text = AppText.T("common.retry"); return; }
            status.Visibility = Visibility.Collapsed;
            if (options.VerifyDirectory is not null && !verificationStarted)
            {
                verificationStarted = true;
                try { await DesktopVerification.RunAsync(this, browser, backend, options.VerifyDirectory); }
                catch (Exception error) { Log(error); await VerificationFailureAsync(error.GetType().Name); }
            }
        };
        core.ProcessFailed += (_, _) => status.Text = AppText.T("common.retry");
    }

    private bool SameOrigin(string value) => Uri.TryCreate(value, UriKind.Absolute, out var uri) &&
        backend.Origin is not null && uri.Scheme == "http" && uri.Host == "127.0.0.1" &&
        uri.Port == backend.Origin.Port && uri.UserInfo.Length == 0;

    private async void OnClosing(object? sender, CancelEventArgs e)
    {
        if (allowClose) return;
        e.Cancel = true;
        if (closing) return;
        closing = true;
        try
        {
            if (!await backend.StopAsync())
            {
                MessageBox.Show(this, AppText.T("windows.closeBusy"), AppText.T("app.name"));
                return;
            }
            SaveBounds();
            allowClose = true;
            Close();
        }
        catch (Exception error)
        {
            Log(error);
            // The job object owns only this window's helper, including failed startup.
            allowClose = true;
            Close();
        }
        finally { closing = false; }
    }

    private string BoundsPath => Path.Combine(backend.DataDirectory, "window.json");
    private void RestoreBoundsFromDisk()
    {
        try
        {
            if (!File.Exists(BoundsPath)) return;
            using var settings = JsonDocument.Parse(File.ReadAllText(BoundsPath));
            var s = settings.RootElement;
            Width = Math.Clamp(s.GetProperty("width").GetDouble(), MinWidth, SystemParameters.WorkArea.Width);
            Height = Math.Clamp(s.GetProperty("height").GetDouble(), MinHeight, SystemParameters.WorkArea.Height);
            WindowState = s.GetProperty("maximized").GetBoolean() ? WindowState.Maximized : WindowState.Normal;
        }
        catch (Exception error) when (error is IOException or JsonException or KeyNotFoundException or InvalidOperationException)
        { Log(error); }
    }

    private void SaveBounds()
    {
        if (options.VerifyDirectory is not null) return;
        var bounds = WindowState == WindowState.Normal ? new Rect(Left, Top, Width, Height) : RestoreBounds;
        var json = JsonSerializer.Serialize(new { width = bounds.Width, height = bounds.Height,
            maximized = WindowState == WindowState.Maximized });
        File.WriteAllText(BoundsPath + ".tmp", json);
        File.Move(BoundsPath + ".tmp", BoundsPath, true);
    }

    private void Log(Exception error)
    {
        var path = Path.Combine(backend.DataDirectory, "desktop-errors.log");
        if (File.Exists(path) && new FileInfo(path).Length > 1024 * 1024) File.Move(path, path + ".previous", true);
        File.AppendAllText(path, DateTimeOffset.Now.ToString("O") + " " + error + Environment.NewLine);
    }

    private async Task VerificationFailureAsync(string reason)
    {
        if (options.VerifyDirectory is null) return;
        Directory.CreateDirectory(options.VerifyDirectory);
        await File.WriteAllTextAsync(Path.Combine(options.VerifyDirectory, "failed.json"),
            JsonSerializer.Serialize(new { reason }));
        Close();
    }
}
