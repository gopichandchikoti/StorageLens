using System.Runtime.InteropServices;
using System.Windows;
using System.Windows.Interop;

namespace StorageLens.Desktop;

internal static class NativeChrome
{
    public static void Apply(Window window)
    {
        if (SystemParameters.HighContrast) return;
        var enabled = 1;
        _ = DwmSetWindowAttribute(new WindowInteropHelper(window).Handle, 20, ref enabled, sizeof(int));
    }
    [DllImport("dwmapi.dll")]
    private static extern int DwmSetWindowAttribute(IntPtr window, int attribute, ref int value, int size);
}
