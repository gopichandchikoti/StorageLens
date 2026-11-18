using System.Reflection;
using System.IO;
using System.Text.Json;

namespace StorageLens.Desktop;

internal static class AppText
{
    private static readonly JsonDocument Model = Resource("storagelens.model.json");
    public static readonly string Version = Resource("product.json").RootElement.GetProperty("version").GetString()!;

    public static string T(string key, params (string Name, object Value)[] values)
    {
        var text = Model.RootElement.GetProperty("locales").GetProperty("en").GetProperty(key).GetString()!;
        foreach (var item in values) text = text.Replace("{" + item.Name + "}", item.Value.ToString());
        return text;
    }

    private static JsonDocument Resource(string suffix)
    {
        var assembly = Assembly.GetExecutingAssembly();
        var resource = assembly.GetManifestResourceNames().Single(n => n.EndsWith(suffix, StringComparison.Ordinal));
        using var stream = assembly.GetManifestResourceStream(resource)!;
        return JsonDocument.Parse(stream);
    }
}

internal sealed record CommandLine(string? DataDirectory, string? VerifyDirectory)
{
    public static CommandLine Parse(string[] args)
    {
        string? data = null, verify = null;
        for (var i = 0; i < args.Length; i++)
        {
            if (i + 1 >= args.Length) continue;
            if (args[i] == "--data-dir") data = Path.GetFullPath(args[++i]);
            else if (args[i] == "--verify") verify = Path.GetFullPath(args[++i]);
        }
        return new(data, verify);
    }
}
