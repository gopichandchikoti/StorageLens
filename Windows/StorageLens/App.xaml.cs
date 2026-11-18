using System.Windows;

namespace StorageLens.Desktop;

public partial class App : Application
{
    protected override void OnStartup(StartupEventArgs e)
    {
        base.OnStartup(e);
        var args = CommandLine.Parse(e.Args);
        var window = new MainWindow(args);
        MainWindow = window;
        window.Show();
    }
}
