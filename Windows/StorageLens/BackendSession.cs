using System.Diagnostics;
using System.IO;
using System.Net.Http;
using System.Security.Cryptography;
using System.Text;
using System.Text.Json;

namespace StorageLens.Desktop;

internal sealed class BackendSession : IDisposable
{
    private readonly HttpClient http = new() { Timeout = TimeSpan.FromSeconds(5) };
    private readonly ProcessJob job = new();
    private Process? process;
    private string? readyFile;
    public string Secret { get; } = Convert.ToHexString(RandomNumberGenerator.GetBytes(32));
    public Uri? Origin { get; private set; }
    public string DataDirectory { get; }
    public int ProcessId => process?.Id ?? 0;

    public BackendSession(string? dataDirectory)
    {
        DataDirectory = dataDirectory ?? Path.Combine(
            Environment.GetFolderPath(Environment.SpecialFolder.LocalApplicationData), "StorageLens", "data");
        Directory.CreateDirectory(DataDirectory);
        http.DefaultRequestHeaders.Add("X-StorageLens-Session", Secret);
    }

    public async Task StartAsync()
    {
        readyFile = Path.Combine(DataDirectory, "ready-" + Guid.NewGuid().ToString("N") + ".json");
        var executable = Path.Combine(AppContext.BaseDirectory, "backend", "StorageLens.Backend.exe");
        if (!File.Exists(executable)) throw new FileNotFoundException("Packaged backend is missing.");
        var start = new ProcessStartInfo(executable)
        {
            UseShellExecute = false, CreateNoWindow = true,
            WorkingDirectory = Path.GetDirectoryName(executable)!
        };
        start.ArgumentList.Add("--port"); start.ArgumentList.Add("0");
        start.ArgumentList.Add("--ready-file"); start.ArgumentList.Add(readyFile);
        start.Environment["STORAGELENS_DATA_DIR"] = DataDirectory;
        start.Environment["STORAGELENS_SESSION_TOKEN"] = Secret;
        process = Process.Start(start) ?? throw new InvalidOperationException("Backend process did not start.");
        job.Add(process);
        using var deadline = new CancellationTokenSource(TimeSpan.FromSeconds(40));
        while (!deadline.IsCancellationRequested)
        {
            if (process.HasExited) throw new InvalidOperationException("Backend exited before readiness.");
            if (File.Exists(readyFile))
            {
                using var receipt = JsonDocument.Parse(await File.ReadAllTextAsync(readyFile, deadline.Token));
                var origin = new Uri(receipt.RootElement.GetProperty("url").GetString()!);
                if (origin.Scheme != "http" || origin.Host != "127.0.0.1" ||
                    receipt.RootElement.GetProperty("pid").GetInt32() != process.Id)
                    throw new InvalidDataException("Unexpected backend readiness receipt.");
                Origin = origin;
                using var response = await http.GetAsync(new Uri(origin, "/api/health"), deadline.Token);
                response.EnsureSuccessStatusCode();
                return;
            }
            await Task.Delay(100, deadline.Token);
        }
        throw new TimeoutException("Backend readiness deadline expired.");
    }

    public async Task<bool> StopAsync()
    {
        if (process is null || process.HasExited || Origin is null) return true;
        using var summary = await GetAsync("summary");
        var token = summary.RootElement.GetProperty("token").GetString()!;
        using var cancel = await PostAsync("cancel-scan", token);
        for (var attempt = 0; attempt < 30; attempt++)
        {
            using var progress = await GetAsync("progress");
            var status = progress.RootElement.GetProperty("status").GetString();
            using var move = await GetAsync("move/status");
            var moving = move.RootElement.GetProperty("active").GetBoolean() &&
                move.RootElement.TryGetProperty("ownerPid", out var owner) && owner.GetInt32() == ProcessId;
            if (!moving && status is not ("starting" or "scanning" or "summarizing"))
            {
                using var stopped = await PostAsync("shutdown", token);
                stopped.EnsureSuccessStatusCode();
                using var timeout = new CancellationTokenSource(TimeSpan.FromSeconds(5));
                await process.WaitForExitAsync(timeout.Token);
                return true;
            }
            await Task.Delay(500);
        }
        return false;
    }

    private async Task<HttpResponseMessage> PostAsync(string method, string token)
    {
        using var request = new HttpRequestMessage(HttpMethod.Post, new Uri(Origin!, "/api/" + method));
        request.Headers.Add("X-StorageLens-Token", token);
        request.Content = new StringContent("{}", Encoding.UTF8, "application/json");
        return await http.SendAsync(request);
    }

    private async Task<JsonDocument> GetAsync(string method)
    {
        using var response = await http.GetAsync(new Uri(Origin!, "/api/" + method));
        response.EnsureSuccessStatusCode();
        using var stream = await response.Content.ReadAsStreamAsync();
        return await JsonDocument.ParseAsync(stream);
    }

    public void Dispose()
    {
        job.Dispose();
        process?.Dispose();
        http.Dispose();
        if (readyFile is not null && File.Exists(readyFile)) File.Delete(readyFile);
    }
}
