// Windows Shell recycling only. A progress sink vetoes permanent deletion.
using System;
using System.Runtime.InteropServices;

namespace StorageLensNative {
    [ComImport, Guid("43826D1E-E718-42EE-BC55-A1E261C37BFE"), InterfaceType(ComInterfaceType.InterfaceIsIUnknown)]
    public interface IShellItem {
        void BindToHandler(IntPtr pbc, ref Guid bhid, ref Guid riid, out IntPtr ppv);
        void GetParent(out IShellItem parent);
        void GetDisplayName(uint sigdn, [MarshalAs(UnmanagedType.LPWStr)] out string name);
        void GetAttributes(uint mask, out uint attrs);
        void Compare(IShellItem other, uint hint, out int order);
    }

    [ComImport, Guid("947AAB5F-0A5C-4C13-B4D6-4BF7836FC9F8"), InterfaceType(ComInterfaceType.InterfaceIsIUnknown)]
    public interface IFileOperation {
        void Advise(IFileOperationProgressSink sink, out uint cookie);
        void Unadvise(uint cookie);
        void SetOperationFlags(uint flags);
        void SetProgressMessage([MarshalAs(UnmanagedType.LPWStr)] string message);
        void SetProgressDialog(IntPtr dialog);
        void SetProperties(IntPtr properties);
        void SetOwnerWindow(IntPtr window);
        void ApplyPropertiesToItem(IShellItem item);
        void ApplyPropertiesToItems(IntPtr items);
        void RenameItem(IShellItem item, [MarshalAs(UnmanagedType.LPWStr)] string name, IFileOperationProgressSink sink);
        void RenameItems(IntPtr items, [MarshalAs(UnmanagedType.LPWStr)] string name);
        void MoveItem(IShellItem item, IShellItem dest, [MarshalAs(UnmanagedType.LPWStr)] string name, IFileOperationProgressSink sink);
        void MoveItems(IntPtr items, IShellItem dest);
        void CopyItem(IShellItem item, IShellItem dest, [MarshalAs(UnmanagedType.LPWStr)] string name, IFileOperationProgressSink sink);
        void CopyItems(IntPtr items, IShellItem dest);
        void DeleteItem(IShellItem item, IFileOperationProgressSink sink);
        void DeleteItems(IntPtr items);
        void NewItem(IShellItem dest, uint attrs, [MarshalAs(UnmanagedType.LPWStr)] string name, [MarshalAs(UnmanagedType.LPWStr)] string template, IFileOperationProgressSink sink);
        void PerformOperations();
        void GetAnyOperationsAborted([MarshalAs(UnmanagedType.Bool)] out bool aborted);
    }

    [ComVisible(true), Guid("04B0F1A7-9490-44BC-96E1-4296A31252E2"), InterfaceType(ComInterfaceType.InterfaceIsIUnknown)]
    public interface IFileOperationProgressSink {
        [PreserveSig] int StartOperations();
        [PreserveSig] int FinishOperations(int result);
        [PreserveSig] int PreRenameItem(uint flags, IShellItem item, [MarshalAs(UnmanagedType.LPWStr)] string name);
        [PreserveSig] int PostRenameItem(uint flags, IShellItem item, [MarshalAs(UnmanagedType.LPWStr)] string name, int result, IShellItem created);
        [PreserveSig] int PreMoveItem(uint flags, IShellItem item, IShellItem dest, [MarshalAs(UnmanagedType.LPWStr)] string name);
        [PreserveSig] int PostMoveItem(uint flags, IShellItem item, IShellItem dest, [MarshalAs(UnmanagedType.LPWStr)] string name, int result, IShellItem created);
        [PreserveSig] int PreCopyItem(uint flags, IShellItem item, IShellItem dest, [MarshalAs(UnmanagedType.LPWStr)] string name);
        [PreserveSig] int PostCopyItem(uint flags, IShellItem item, IShellItem dest, [MarshalAs(UnmanagedType.LPWStr)] string name, int result, IShellItem created);
        [PreserveSig] int PreDeleteItem(uint flags, IShellItem item);
        [PreserveSig] int PostDeleteItem(uint flags, IShellItem item, int result, IShellItem recycled);
        [PreserveSig] int PreNewItem(uint flags, IShellItem dest, [MarshalAs(UnmanagedType.LPWStr)] string name);
        [PreserveSig] int PostNewItem(uint flags, IShellItem dest, [MarshalAs(UnmanagedType.LPWStr)] string name, [MarshalAs(UnmanagedType.LPWStr)] string template, uint attrs, int result, IShellItem created);
        [PreserveSig] int UpdateProgress(uint total, uint completed);
        [PreserveSig] int ResetTimer();
        [PreserveSig] int PauseTimer();
        [PreserveSig] int ResumeTimer();
    }

    [ComVisible(true), ClassInterface(ClassInterfaceType.None)]
    public class RecycleSink : IFileOperationProgressSink {
        public bool SawRecycle, RefusedPermanent, Completed;
        public int LastResult;
        public string RecycledPath;
        public int StartOperations() { return 0; }
        public int FinishOperations(int hr) { LastResult=hr; return 0; }
        public int PreRenameItem(uint f, IShellItem i, string n) { return unchecked((int)0x80004005); }
        public int PostRenameItem(uint f, IShellItem i, string n, int h, IShellItem x) { return 0; }
        public int PreMoveItem(uint f, IShellItem i, IShellItem d, string n) { return unchecked((int)0x80004005); }
        public int PostMoveItem(uint f, IShellItem i, IShellItem d, string n, int h, IShellItem x) { return 0; }
        public int PreCopyItem(uint f, IShellItem i, IShellItem d, string n) { return unchecked((int)0x80004005); }
        public int PostCopyItem(uint f, IShellItem i, IShellItem d, string n, int h, IShellItem x) { return 0; }
        public int PreDeleteItem(uint flags, IShellItem item) {
            // TSF_DELETE_RECYCLE_IF_POSSIBLE must be present for every delete.
            if ((flags & 0x80) == 0) { RefusedPermanent=true; return unchecked((int)0x80004005); }
            SawRecycle=true;
            return 0;
        }
        public int PostDeleteItem(uint flags, IShellItem item, int hr, IShellItem recycled) {
            LastResult=hr;
            Completed=hr >= 0 && recycled != null;
            if (Completed) {
                try { recycled.GetDisplayName(0x80058000, out RecycledPath); } catch { }
            }
            return 0;
        }
        public int PreNewItem(uint f, IShellItem d, string n) { return unchecked((int)0x80004005); }
        public int PostNewItem(uint f, IShellItem d, string n, string t, uint a, int h, IShellItem x) { return 0; }
        public int UpdateProgress(uint a, uint b) { return 0; }
        public int ResetTimer() { return 0; }
        public int PauseTimer() { return 0; }
        public int ResumeTimer() { return 0; }
    }

    public static class RecycleBridge {
        [DllImport("shell32.dll", CharSet=CharSet.Unicode, PreserveSig=false)]
        static extern void SHCreateItemFromParsingName(string path, IntPtr context, ref Guid iid, [MarshalAs(UnmanagedType.Interface)] out IShellItem item);

        public static string Recycle(string path) {
            IFileOperation operation=null;
            IShellItem item=null;
            var sink=new RecycleSink();
            try {
                operation=(IFileOperation)Activator.CreateInstance(Type.GetTypeFromCLSID(new Guid("3AD05575-8857-4850-9277-11B85BDB8E09")));
                // Recycle, undo record, no confirmation/error UI, stop on first error.
                operation.SetOperationFlags(0x00080000 | 0x20000000 | 0x00100000 | 0x00000400 | 0x00000010 | 0x00000004);
                var iid=new Guid("43826D1E-E718-42EE-BC55-A1E261C37BFE");
                SHCreateItemFromParsingName(path, IntPtr.Zero, ref iid, out item);
                operation.DeleteItem(item, sink);
                operation.PerformOperations();
                bool aborted;
                operation.GetAnyOperationsAborted(out aborted);
                if (sink.RefusedPermanent) throw new InvalidOperationException("Windows could not recycle this item. Permanent deletion was blocked.");
                if (aborted || !sink.SawRecycle || !sink.Completed || sink.LastResult < 0)
                    throw new InvalidOperationException("The Recycle Bin operation did not complete. No permanent-delete fallback is enabled. Windows result: 0x"+sink.LastResult.ToString("X8"));
                return sink.RecycledPath;
            } finally {
                if (item != null) Marshal.ReleaseComObject(item);
                if (operation != null) Marshal.ReleaseComObject(operation);
                GC.KeepAlive(sink);
            }
        }
    }
}
