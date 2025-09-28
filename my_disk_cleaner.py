import os
import sys
import shutil
import tkinter as tk
from tkinter import ttk, messagebox

# Initial candidate directories (for Mac)
MAC_INITIAL_DIRS = [
    os.path.expanduser('~/Library/Caches'),
    os.path.expanduser('~/Library/Logs'),
    os.path.expanduser('~/Library/Application Support'),
    os.path.expanduser('~/Library/Containers'),
]

WINDOWS_INITIAL_DIRS = [
    r"C:\Windows\Temp",
    r"C:\ProgramData",
    r"C:\System Volume Information",
    r"C:\Windows\SoftwareDistribution\Download",
    r"C:\Cygwin64\var\cache\setup",
    os.path.expanduser(r'~\AppData\Local\Temp'),
    os.path.expanduser('~\\AppData\\Local\\Packages'),
    os.path.expanduser('~\\AppData\\Local\\pip\\Cache'),
    os.path.expanduser('~\\AppData\\Local\\npm-cache'),
    os.path.expanduser('~\\AppData\\Roaming\\Code\\Cache'),
    os.path.expanduser('~\\AppData\\Roaming\\Code\\Backups'),
    os.path.expanduser('~\\AppData\\Local\\BraveSoftware\\Brave-Browser\\User Data\\Default\\Cache'),
    os.path.expanduser('~\\.ollama'),
]

def is_mac():
    return sys.platform == 'darwin'

def is_windows():
    return sys.platform.startswith('win')

def is_windows_hardlink(path) -> bool:
    # Check if a file is a hard link on Windows
    if not is_windows():
        return False
    if not os.path.exists(path):
        return False
    try:
        import ctypes
        FILE_ATTRIBUTE_REPARSE_POINT = 0x0400
        attrs = ctypes.windll.kernel32.GetFileAttributesW(str(path))  # type: ignore
        if attrs == -1:
            return False
        return bool(attrs & FILE_ATTRIBUTE_REPARSE_POINT)
    except Exception:
        return False

# Directory size calculation for Mac
def get_dir_size(path, queue=None):
    total = 0
    for root, dirs, files in os.walk(path):
        for f in files:
            try:
                fp = os.path.join(root, f)
                # Exclude symbolic links from size calculation
                if os.path.islink(fp) or is_windows_hardlink(fp):
                    continue
                if queue is not None:
                    queue.put(("progress", fp))
                total += os.path.getsize(fp)
            except Exception:
                pass
    return total

# List files and directories for Mac
def list_dir(path):
    try:
        entries = []
        with os.scandir(path) as it:
            for entry in it:
                if os.path.islink(entry.path) or is_windows_hardlink(entry.path):
                    continue
                size = 0
                if entry.is_file():
                    try:
                        size = entry.stat().st_size
                    except Exception:
                        size = 0
                elif entry.is_dir():
                    try:
                        size = get_dir_size(entry.path)
                    except Exception:
                        size = 0
                entries.append({
                    'name': entry.name,
                    'path': entry.path,
                    'is_dir': entry.is_dir(),
                    'size': size
                })
        return entries
    except Exception:
        return []

# Delete files and directories for Mac
def delete_items(items):
    for item in items:
        try:
            if os.path.isdir(item):
                shutil.rmtree(item)
            else:
                os.remove(item)
        except Exception:
            pass

class DiskCleanerApp(tk.Tk):
    def __init__(self):
        super().__init__()
        self.title("My Disk Cleaner")
        self.geometry("800x600")
        self.selected_dir = None
        self.dir_entries = []
        self.selected_items = set()
        self.loading = False
        self.show_dir_sizes = tk.BooleanVar(value=False)
        self.create_widgets()
        self.refresh_initial_dirs()
        self.update_breadcrumbs()

    @staticmethod
    def get_display_name(entry):
        # Add separator at the end of directory names
        if entry.get('is_dir', False):
            sep = '\\' if is_windows() else '/'
            name = entry['name']
            # Add separator only if not already present
            if not name.endswith(sep):
                name += sep
            return name
        return entry['name']

    def create_widgets(self):
        # Frame for breadcrumb navigation
        self.breadcrumb_frame = tk.Frame(self)
        self.breadcrumb_frame.pack(anchor='nw', fill='x', padx=10, pady=5)

        # Checkbox for toggling directory size calculation
        self.size_checkbox = tk.Checkbutton(self, text="Show directory sizes", variable=self.show_dir_sizes, command=self.on_toggle_dir_sizes)
        self.size_checkbox.pack(anchor='nw', padx=10, pady=5)

        # Directory size display
        self.size_label = tk.Label(self, text="Directory size: ")
        self.size_label.pack(anchor='nw', padx=10, pady=5)

        # Loading indicator
        self.loading_label = tk.Label(self, text="", fg="blue")
        self.loading_label.pack(anchor='nw', padx=10, pady=5)

        # File/Directory list
        self.tree = ttk.Treeview(self, columns=("size",), selectmode="extended")
        self.tree.heading("#0", text="Name")
        self.tree.heading("size", text="Size (bytes)")
        self.tree.column("#0", width=400)
        self.tree.column("size", width=120, anchor='e')
        self.tree.pack(fill='both', expand=True, padx=10, pady=5)
        self.tree.bind("<Double-1>", self.on_tree_double_click)

        # Delete button
        self.delete_btn = tk.Button(self, text="Delete selected items", command=self.on_delete)
        self.delete_btn.pack(anchor='se', padx=10, pady=10)

    def refresh_initial_dirs(self):
        if is_mac():
            dirs = MAC_INITIAL_DIRS
        elif is_windows():
            dirs = WINDOWS_INITIAL_DIRS
        else:
            dirs = []
        self.selected_dir = None
        self.dir_entries = []
        self.tree.delete(*self.tree.get_children())
        if self.show_dir_sizes.get():
            # Calculate directory sizes in background process
            import multiprocessing
            self._init_dirs_queue = multiprocessing.Queue()
            p = multiprocessing.Process(target=self._calc_initial_dirs_sizes_process, args=(dirs, self._init_dirs_queue))
            p.start()
            self._init_dirs_process = p
            self.loading_label.config(text="Loading...")
            self.delete_btn.config(state="disabled")
            self.after(100, self._poll_init_dirs_queue)
        else:
            # No size calculation
            for dir_path in dirs:
                entry = {
                    'name': dir_path,
                    'path': dir_path,
                    'is_dir': True,
                    'size': "-"
                }
                self.dir_entries.append(entry)
                display_name = self.get_display_name(entry)
                self.tree.insert("", "end", iid=dir_path, text=display_name, values=("-",), tags=("dir",))
            self.size_label.config(text="Directory size: -")
            self.loading_label.config(text="")
            self.delete_btn.config(state="disabled")

    def start_refresh_dir_view(self):
        if self.loading:
            return  # Prevent double loading
        self.loading = True
        self.loading_label.config(text="Loading...")
        self.delete_btn.config(state="disabled")
        self.tree.delete(*self.tree.get_children())
        # Start multiprocessing for directory view refresh
        import multiprocessing
        self._mp_queue = multiprocessing.Queue()
        p = multiprocessing.Process(target=DiskCleanerApp._refresh_dir_view_process, args=(self.selected_dir, self._mp_queue, self.show_dir_sizes.get()))
        p.start()
        self._mp_process = p
        self.after(100, self._poll_mp_queue)

    @staticmethod
    def _refresh_dir_view_process(selected_dir, queue, show_dir_sizes=True):
        def get_display_name_static(entry):
            if entry.get('is_dir', False):
                sep = '\\' if is_windows() else '/'
                name = entry['name']
                if not name.endswith(sep):
                    name += sep
                return name
            return entry['name']

        if not selected_dir:
            size = "-"
            entries = []
        else:
            if show_dir_sizes:
                size = get_dir_size(selected_dir, queue)
                entries = list_dir(selected_dir)
            else:
                size = "-"
                entries = []
                try:
                    with os.scandir(selected_dir) as it:
                        for entry in it:
                            if os.path.islink(entry.path) or is_windows_hardlink(entry.path):
                                continue
                            size_val = "-" if entry.is_dir() else (entry.stat().st_size if entry.is_file() else "-")
                            entry_dict = {
                                'name': entry.name,
                                'path': entry.path,
                                'is_dir': entry.is_dir(),
                                'size': size_val
                            }
                            entry_dict['name'] = get_display_name_static(entry_dict)
                            entries.append(entry_dict)
                except Exception:
                    pass
            # Update display name when directory size display is ON
            if show_dir_sizes:
                for entry in entries:
                    entry['name'] = get_display_name_static(entry)
        # Progress notification (only when directory size calculation is ON)
        if show_dir_sizes:
            for entry in entries:
                queue.put(("progress", entry['name']))
        queue.put(("result", size, entries))

    def _update_dir_view_ui(self, size, entries):
        self.size_label.config(text=f"Directory size: {size if isinstance(size, str) else f'{size:,} bytes'}")
        self.dir_entries = entries
        for entry in entries:
            tag = "dir" if entry['is_dir'] else "file"
            display_name = self.get_display_name(entry)
            display_size = "{:,}".format(entry['size']) if isinstance(entry['size'], int) else entry['size']
            self.tree.insert("", "end", iid=entry['path'], text=display_name, values=(display_size,), tags=(tag,))
        self.loading_label.config(text="")
        self.delete_btn.config(state="normal")
        self.loading = False

    def on_toggle_dir_sizes(self):
        # Callback for checkbox toggle
        # If loading, terminate the current process to cancel loading
        if getattr(self, "loading", False) and hasattr(self, "_mp_process"):
            try:
                self._mp_process.terminate()
            except Exception:
                pass
            self.loading = False
            self.loading_label.config(text="")
            self.delete_btn.config(state="disabled")
            self.tree.delete(*self.tree.get_children())
            if hasattr(self, "_mp_process"):
                del self._mp_process
            if hasattr(self, "_mp_queue"):
                del self._mp_queue
        if self.selected_dir is None:
            self.refresh_initial_dirs()
        else:
            self.start_refresh_dir_view()

    def _poll_mp_queue(self):
        if hasattr(self, "_mp_queue"):
            try:
                msg = self._mp_queue.get_nowait()
                if isinstance(msg, tuple) and msg[0] == "progress":
                    filename = msg[1]
                    self.loading_label.config(text=f"Loading...{filename}")
                    self.after(100, self._poll_mp_queue)
                elif isinstance(msg, tuple) and msg[0] == "result":
                    size, entries = msg[1], msg[2]
                    self._update_dir_view_ui(size, entries)
                    # Process termination handling
                    if hasattr(self, "_mp_process"):
                        self._mp_process.join(timeout=0.1)
                        del self._mp_process
                    del self._mp_queue
                else:
                    # Old format (backward compatibility)
                    size, entries = msg
                    self._update_dir_view_ui(size, entries)
                    if hasattr(self, "_mp_process"):
                        self._mp_process.join(timeout=0.1)
                        del self._mp_process
                    del self._mp_queue
            except Exception:
                # If the queue is empty, call again with after
                self.after(100, self._poll_mp_queue)

    def on_tree_double_click(self, event):
        item_id = self.tree.focus()
        if not item_id:
            return
        entry = next((e for e in self.dir_entries if e['path'] == item_id), None)
        if entry and entry['is_dir']:
            self.selected_dir = entry['path']
            self.start_refresh_dir_view()
            self.update_breadcrumbs()

    def on_delete(self):
        selected = self.tree.selection()
        if not selected:
            messagebox.showinfo("Delete", "Please select items to delete.")
            return
        confirm = messagebox.askyesno("Confirm", "Are you sure you want to delete the selected items?")
        if not confirm:
            return
        delete_items(selected)
        self.start_refresh_dir_view()

    def update_breadcrumbs(self):
        # Update breadcrumb navigation display
        for widget in self.breadcrumb_frame.winfo_children():
            widget.destroy()
        if self.selected_dir is None:
            # Initial directories list view label
            lbl = tk.Label(self.breadcrumb_frame, text="Initial Directories", relief=tk.FLAT)
            lbl.pack(side='left')
            return
        else:
            # Initial directories list view button
            btn = tk.Button(self.breadcrumb_frame, text="Initial Directories", relief=tk.FLAT, command=self.refresh_initial_dirs)
            btn.pack(side='left')
            sep = tk.Label(self.breadcrumb_frame, text=" > ")
            sep.pack(side='left')
        home_dir = os.path.expanduser('~')
        # Breadcrumb navigation
        parts = []
        path = self.selected_dir
        for initial in (MAC_INITIAL_DIRS if is_mac() else WINDOWS_INITIAL_DIRS):
            if path == initial or path.startswith(initial + os.sep):
                parts.append((initial, initial))
                path = path[len(initial):].lstrip(os.sep)
                break
        while True:
            head, tail = os.path.split(path)
            if tail:
                parts.insert(1, (tail, path))
                path = head
            else:
                if head:
                    parts.insert(1, (head, head))
                break
        # Shorten display using "~" for home directory
        def short_path(p):
            if p.startswith(home_dir):
                return p.replace(home_dir, "~", 1)
            return p
        # The last item is a Label (not selectable), others are buttons
        for i, (name, full_path) in enumerate(parts):
            display_name = short_path(name)
            if i == len(parts) - 1:
                lbl = tk.Label(self.breadcrumb_frame, text=display_name, relief=tk.FLAT)
                lbl.pack(side='left')
            else:
                btn = tk.Button(self.breadcrumb_frame, text=display_name, relief=tk.FLAT, command=lambda p=full_path: self.on_breadcrumb_click(p))
                btn.pack(side='left')
            if i < len(parts) - 1:
                sep = tk.Label(self.breadcrumb_frame, text=" > ")
                sep.pack(side='left')

    def on_breadcrumb_click(self, path):
        # Navigate to the directory when breadcrumb is clicked
        if path != self.selected_dir:
            self.selected_dir = path
            self.start_refresh_dir_view()
            self.update_breadcrumbs()

    @staticmethod
    def _calc_initial_dirs_sizes_process(dirs, queue):
        entries = []
        for dir_path in dirs:
            queue.put(("progress", dir_path))
            try:
                size = get_dir_size(dir_path, queue)
            except Exception:
                size = 0
            entry = {
                'name': dir_path,
                'path': dir_path,
                'is_dir': True,
                'size': size
            }
            entries.append(entry)
        queue.put(("result", entries))

    def _poll_init_dirs_queue(self):
        if hasattr(self, "_init_dirs_queue"):
            try:
                entries = self._init_dirs_queue.get_nowait()
                self.dir_entries = entries
                for entry in entries:
                    display_name = self.get_display_name(entry)
                    display_size = "{:,}".format(entry['size']) if isinstance(entry['size'], int) else entry['size']
                    self.tree.insert("", "end", iid=entry['path'], text=display_name, values=(display_size,), tags=("dir",))
                self.loading_label.config(text="")
                self.delete_btn.config(state="disabled")
                if hasattr(self, "_init_dirs_process"):
                    self._init_dirs_process.join(timeout=0.1)
                    del self._init_dirs_process
                del self._init_dirs_queue
            except Exception:
                self.after(100, self._poll_init_dirs_queue)

if __name__ == "__main__":
    app = DiskCleanerApp()
    app.mainloop()
