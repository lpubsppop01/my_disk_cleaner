import enum
import multiprocessing
import os
import shutil
import sqlite3
import sys
import tkinter as tk
import tkinter.font
from tkinter import messagebox, ttk


def get_admin_db_path() -> str:
    """Get the path to the admin SQLite database."""
    if sys.platform.startswith("win"):
        local_appdata = os.environ.get(
            "LOCALAPPDATA", os.path.expanduser("~\\AppData\\Local")
        )
        db_dir = os.path.join(local_appdata, "lpubsppop01_my_disk_cleaner")
    else:
        db_dir = os.path.expanduser("~/.lpubsppop01_my_disk_cleaner")
    return os.path.join(db_dir, "admin.db")


ADMIN_DB_PATH = get_admin_db_path()
"""Path to the admin SQLite database."""


def init_admin_db() -> None:
    """Initialize the admin SQLite database."""
    os.makedirs(os.path.dirname(ADMIN_DB_PATH), exist_ok=True)
    conn = sqlite3.connect(ADMIN_DB_PATH)
    c = conn.cursor()
    c.execute(
        """
        CREATE TABLE IF NOT EXISTS directory_size_cache (
            path TEXT PRIMARY KEY,
            size INTEGER,
            mtime INTEGER
        )
        """
    )
    c.execute(
        """
        CREATE TABLE IF NOT EXISTS target_directories (
            platform TEXT NOT NULL,
            path TEXT NOT NULL,
            PRIMARY KEY (platform, path)
        )
        """
    )
    conn.commit()
    conn.close()


class Platform(enum.StrEnum):
    """Enumeration of supported platforms."""

    MAC = "mac"
    WINDOWS = "windows"
    OTHER = "other"


def load_target_directories(platform: Platform) -> list[str]:
    """Load target directories for the given platform from the database."""
    conn = sqlite3.connect(ADMIN_DB_PATH)
    c = conn.cursor()
    c.execute("SELECT path FROM target_directories WHERE platform=?", (platform,))
    rows = c.fetchall()
    conn.close()
    return [row[0] for row in rows]


def save_target_directories(platform: Platform, dirs: list[str]) -> None:
    """Save target directories for the given platform to the database."""
    conn = sqlite3.connect(ADMIN_DB_PATH)
    c = conn.cursor()
    c.execute("DELETE FROM target_directories WHERE platform=?", (platform,))
    for dir_path in dirs:
        c.execute(
            "INSERT INTO target_directories (platform, dir) VALUES (?, ?)",
            (platform, dir_path),
        )
    conn.commit()
    conn.close()


def is_mac() -> bool:
    return sys.platform == "darwin"


def is_windows() -> bool:
    return sys.platform.startswith("win")


def get_platform() -> Platform:
    """Get the current platform."""
    if is_mac():
        return Platform.MAC
    elif is_windows():
        return Platform.WINDOWS
    else:
        return Platform.OTHER


class PresetTargetDirectoryListKind(enum.StrEnum):
    """Enumeration of preset target directory list kinds."""

    ROOT = "root"
    USER = "user"
    CACHE = "cache"


def get_mac_preset_target_directories(kind: PresetTargetDirectoryListKind) -> list[str]:
    """Get preset target directories for Mac based on the specified kind."""
    if kind == PresetTargetDirectoryListKind.ROOT:
        return [os.path.join("/", d) for d in os.listdir("/")]
    elif kind == PresetTargetDirectoryListKind.USER:
        return [
            os.path.join(os.path.expanduser("~"), d)
            for d in os.listdir(os.path.expanduser("~"))
        ]
    elif kind == PresetTargetDirectoryListKind.CACHE:
        return [
            os.path.expanduser("~/Desktop"),
            os.path.expanduser("~/Downloads"),
            os.path.expanduser("~/Library/Application Support"),
            os.path.expanduser("~/Library/Caches"),
            os.path.expanduser("~/Library/Containers"),
            os.path.expanduser("~/Library/Developer"),
            os.path.expanduser("~/Library/Logs"),
        ]


def get_windows_preset_target_directories(
    kind: PresetTargetDirectoryListKind,
) -> list[str]:
    """Get preset target directories for Windows based on the specified kind."""
    if kind == PresetTargetDirectoryListKind.ROOT:
        return [os.path.join("C:\\", d) for d in os.listdir("C:\\")]
    elif kind == PresetTargetDirectoryListKind.USER:
        return [
            os.path.join(os.path.expanduser("~"), d)
            for d in os.listdir(os.path.expanduser("~"))
        ]
    elif kind == PresetTargetDirectoryListKind.CACHE:
        return [
            os.path.expanduser(r"~\AppData\Local\npm-cache"),
            os.path.expanduser(r"~\AppData\Local\Packages"),
            os.path.expanduser(r"~\AppData\Local\pip\Cache"),
            os.path.expanduser(r"~\AppData\Local\Temp"),
            os.path.expanduser(r"~\AppData\Roaming\Code\Backups"),
            os.path.expanduser(r"~\AppData\Roaming\Code\Cache"),
            r"C:\cygwin64\var\cache\setup",
            r"C:\ProgramData",
            r"C:\Windows\SoftwareDistribution\Download",
            r"C:\Windows\Temp",
        ]


def get_preset_target_directories(kind: PresetTargetDirectoryListKind) -> list[str]:
    """Get preset target directories based on the current platform and specified kind."""
    if is_mac():
        return get_mac_preset_target_directories(kind)
    elif is_windows():
        return get_windows_preset_target_directories(kind)
    else:
        return []


def is_windows_hardlink(path: str) -> bool:
    """Check if the given path is a Windows hard link."""
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


def get_directory_size(
    path: str,
    queue: (
        multiprocessing.Queue[tuple[str, str] | tuple[str, list[dict[str, object]]]]
        | None
    ) = None,
) -> int:
    """Get the size of a directory, using cache if available."""
    # Get mtime of the directory
    mtime = None
    try:
        mtime = int(os.path.getmtime(path))
    except Exception:
        mtime = None
    if mtime is None:
        return 0

    # Try to get cached size if mtime is available
    size: int | None = None
    try:
        conn = sqlite3.connect(ADMIN_DB_PATH)
        c = conn.cursor()
        c.execute("SELECT size, mtime FROM directory_size_cache WHERE path=?", (path,))
        row = c.fetchone()
        if row and row[1] == mtime:
            size = row[0]
        conn.close()
    except Exception:
        size = None
    if size is not None:
        return size

    # If cache is missing or mtime is different, recalculate
    dir_path_to_size: dict[str, int] = {}
    total_size = 0
    total_count = 0
    for root, dirs, files in os.walk(path):
        for f in files:
            try:
                # Exclude symbolic links and Windows hard links
                file_path = os.path.join(root, f)
                if os.path.islink(file_path) or is_windows_hardlink(file_path):
                    continue

                # Get file size
                size = os.path.getsize(file_path)
                total_size += size
                total_count += 1

                # Report progress every 100 files
                if queue is not None and total_count % 100 == 0:
                    queue.put(("progress", file_path))

                # Add size to each ancestor directory
                ancestor = file_path
                ancestors = []
                while True:
                    ancestor = os.path.dirname(ancestor)
                    if ancestor.startswith(path):
                        ancestors.append(ancestor)
                        if ancestor == path:
                            break
                    else:
                        break
                for dir_path in ancestors:
                    new_dir_size = dir_path_to_size.get(dir_path, 0) + size
                    dir_path_to_size[dir_path] = new_dir_size
            except Exception:
                pass

    # Update cache in a single transaction
    try:
        # Open DB connection
        conn = sqlite3.connect(ADMIN_DB_PATH)
        c = conn.cursor()

        # Cache the size of each directory
        for dir_path, size in dir_path_to_size.items():
            dir_mtime = None
            try:
                dir_mtime = int(os.path.getmtime(dir_path))
            except Exception:
                dir_mtime = None
            if dir_mtime is not None:
                c.execute(
                    "INSERT OR REPLACE INTO directory_size_cache (path, size, mtime) VALUES (?, ?, ?)",
                    (dir_path, size, dir_mtime),
                )

        # Also cache (path, total, mtime) in the same transaction
        c.execute(
            "INSERT OR REPLACE INTO directory_size_cache (path, size, mtime) VALUES (?, ?, ?)",
            (path, total_size, mtime),
        )

        # Commit and close
        conn.commit()
        conn.close()
    except Exception:
        pass
    return total_size


def delete_items(items: list[str]) -> None:
    """Delete the specified files and directories."""
    for item in items:
        try:
            if os.path.isdir(item):
                shutil.rmtree(item)
            else:
                os.remove(item)
        except Exception:
            pass


class DiskCleanerApp(tk.Tk):
    """Main application class for the disk cleaner."""

    def __init__(self) -> None:
        """Initialize the main application window and its components."""
        super().__init__()
        self.title("My Disk Cleaner")
        self.geometry("800x600")
        self.selected_dir_path: str | None = None
        self.dir_entries: list[dict[str, object]] = []
        self.selected_items: set[str] = set()
        self.loading: bool = False
        self.show_dir_sizes: tk.BooleanVar = tk.BooleanVar(value=False)
        self.sort_column: str | None = None
        self.sort_reverse: bool = False
        self._queue: multiprocessing.Queue[str] | None = None
        self.create_widgets()
        self.refresh_list_view_by_target_dirs()
        self.update_breadcrumbs()

    @staticmethod
    def get_display_name(entry: dict[str, object]) -> str:
        """Get the display name for a file or directory entry."""
        # Add separator at the end of directory names
        if entry.get("is_dir", False):
            sep = "\\" if is_windows() else "/"
            name = str(entry["name"])
            # Add separator only if not already present
            if not name.endswith(sep):
                name += sep
            return name
        return str(entry["name"])

    def create_widgets(self) -> None:
        """Create and layout the widgets in the main application window."""
        # Configure grid weights for main window
        self.grid_rowconfigure(3, weight=1)
        self.grid_columnconfigure(0, weight=1)
        self.grid_columnconfigure(1, weight=0)

        # Canvas + Frame + Scrollbar for breadcrumb navigation (height fixed, horizontal scroll)
        self.breadcrumb_frame = tk.Frame(self)
        self.breadcrumb_frame.grid(row=0, column=0, columnspan=2, sticky="ew")
        self.breadcrumb_canvas = tk.Canvas(
            self.breadcrumb_frame, height=32, highlightthickness=0, bd=0
        )
        self.breadcrumb_canvas.pack(side="top", fill="x", expand=True)
        self.breadcrumb_inner_frame = tk.Frame(self.breadcrumb_canvas)
        self.breadcrumb_window = self.breadcrumb_canvas.create_window(
            (0, 0), window=self.breadcrumb_inner_frame, anchor="nw"
        )
        self.breadcrumb_scrollbar = tk.Scrollbar(
            self.breadcrumb_frame,
            orient="horizontal",
            command=self.breadcrumb_canvas.xview,
        )
        self.breadcrumb_scrollbar.pack(side="bottom", fill="x")
        self.breadcrumb_canvas.configure(xscrollcommand=self.breadcrumb_scrollbar.set)
        self.breadcrumb_inner_frame.bind(
            "<Configure>",
            lambda e: self.breadcrumb_canvas.configure(
                scrollregion=self.breadcrumb_canvas.bbox("all")
            ),
        )
        self.breadcrumb_canvas.pack_propagate(False)

        # Frame for buttons (Show directory sizes & Clear Cache)
        self.button_frame = tk.Frame(self)
        self.button_frame.grid(
            row=1, column=0, columnspan=2, sticky="ew", padx=10, pady=5
        )
        self.button_frame.grid_columnconfigure(0, weight=0)
        self.button_frame.grid_columnconfigure(1, weight=0)
        self.button_frame.grid_columnconfigure(2, weight=0)

        # Edit Target Directories button (leftmost)
        self.edit_target_dirs_btn = tk.Button(
            self.button_frame,
            text="Edit Target Directories",
            command=self.show_edit_target_directory_list_dialog,
        )
        self.edit_target_dirs_btn.grid(row=0, column=0, sticky="w", padx=0, pady=0)

        # Clear Cache button (next to Edit Initial Directories)
        self.clear_cache_btn = tk.Button(
            self.button_frame, text="Clear Cache", command=self.on_clear_cache
        )
        self.clear_cache_btn.grid(row=0, column=1, sticky="w", padx=10, pady=0)

        # Checkbox for toggling directory size calculation (next to Clear Cache)
        self.size_checkbox = tk.Checkbutton(
            self.button_frame,
            text="Show directory sizes",
            variable=self.show_dir_sizes,
            command=self.on_toggle_dir_sizes,
        )
        self.size_checkbox.grid(row=0, column=2, sticky="w", padx=5, pady=0)

        # Status label (Unified label)
        self.status_label = tk.Label(self, text="", anchor="w")
        self.status_label.grid(
            row=2, column=0, columnspan=2, sticky="ew", padx=10, pady=5
        )

        # File/Directory list
        self.tree = ttk.Treeview(self, columns=("size",), selectmode="extended")
        self.tree.heading(
            "#0", text="Name", command=lambda: self.on_tree_heading_click("name")
        )
        self.tree.heading(
            "size",
            text="Size (bytes)",
            command=lambda: self.on_tree_heading_click("size"),
        )
        self.tree.column("#0", width=400)
        self.tree.column("size", width=120, anchor="e")
        self.tree.grid(row=3, column=0, columnspan=2, sticky="nsew", padx=10, pady=5)
        self.tree.bind("<Double-1>", self.on_tree_double_click)

        # Delete button
        self.delete_btn = tk.Button(
            self, text="Delete Selected Items", command=self.on_delete
        )
        self.delete_btn.grid(row=4, column=1, sticky="e", padx=10, pady=10)

    def set_status_text(self, text: str) -> None:
        """Set the status text, truncating if necessary to fit the label width."""
        label_width = self.status_label.winfo_width()
        font = tkinter.font.Font(font=self.status_label.cget("font"))
        char_width = font.measure("A") or 8  # Assume 8px if unable to get width
        if label_width > 1 and char_width > 0:
            max_len = label_width // char_width
        else:
            max_len = 100  # Default if width is not determined yet
        if len(text) > max_len:
            text = text[: max_len - 3] + "..."
        self.status_label.config(text=text)

    def show_edit_target_directory_list_dialog(self) -> None:
        """Show a dialog to edit the list of target directories."""
        # Dialog window
        dialog = tk.Toplevel(self)
        dialog.title("Edit Target Directories")
        dialog.geometry("650x400")
        dialog.transient(self)
        dialog.grab_set()

        # Get current list
        dirs = load_target_directories(get_platform())

        # Text box
        text_box = tk.Text(dialog, wrap="none")
        text_box.pack(fill="both", expand=True, padx=10, pady=10)
        text_box.insert("1.0", "\n".join(dirs))

        # Button frame
        btn_frame = tk.Frame(dialog)
        btn_frame.pack(fill="x", padx=10, pady=5)

        def on_save() -> None:
            """Save the edited list of target directories."""
            new_dirs = text_box.get("1.0", "end").strip().splitlines()
            # Remove empty lines
            new_dirs = [d for d in new_dirs if d.strip()]
            save_target_directories(get_platform(), new_dirs)
            dialog.destroy()
            self.refresh_list_view_by_target_dirs()

        def on_cancel() -> None:
            """Cancel editing and close the dialog."""
            dialog.destroy()

        # Save and Cancel buttons
        save_btn = tk.Button(btn_frame, text="Save", command=on_save)
        save_btn.pack(side="left", padx=5)
        cancel_btn = tk.Button(btn_frame, text="Cancel", command=on_cancel)
        cancel_btn.pack(side="left", padx=5)

        def on_reset(kind: PresetTargetDirectoryListKind) -> None:
            """Reset the text box to preset target directories based on the specified kind."""
            default_dirs = get_preset_target_directories(kind)
            text_box.delete("1.0", "end")
            text_box.insert("1.0", "\n".join(default_dirs))

        # Reset buttons for preset target directory lists
        reset_by_root_btn = tk.Button(
            btn_frame,
            text="Reset by root dir",
            command=lambda: on_reset(PresetTargetDirectoryListKind.ROOT),
        )
        reset_by_root_btn.pack(side="left", padx=5)
        reset_by_user_btn = tk.Button(
            btn_frame,
            text="Reset by user dirs",
            command=lambda: on_reset(PresetTargetDirectoryListKind.USER),
        )
        reset_by_user_btn.pack(side="left", padx=5)
        reset_by_cache_btn = tk.Button(
            btn_frame,
            text="Reset by cache dirs",
            command=lambda: on_reset(PresetTargetDirectoryListKind.CACHE),
        )
        reset_by_cache_btn.pack(side="left", padx=5)

    def on_clear_cache(self) -> None:
        """Clear the directory size cache."""
        try:
            conn = sqlite3.connect(ADMIN_DB_PATH)
            c = conn.cursor()
            c.execute("DELETE FROM directory_size_cache")
            conn.commit()
            conn.close()
        except Exception:
            pass

        # Refresh UI after clearing cache
        if self.selected_dir_path is None:
            self.refresh_list_view_by_target_dirs()
        else:
            self.refresh_list_view_by_child_items()

    def refresh_list_view_by_target_dirs(self) -> None:
        """Refresh the list view to show the initial target directories."""
        # Prevent double loading
        if self.loading:
            return

        # Get list from DB
        dirs = load_target_directories(get_platform())

        # Reset state
        self.selected_dir_path = None
        self.dir_entries = []
        self.tree.delete(*self.tree.get_children())

        # Update list view
        if self.show_dir_sizes.get():
            # Use multiprocessing to load directory sizes
            self._queue = multiprocessing.Queue()
            self._process = multiprocessing.Process(
                target=DiskCleanerApp._get_entries_process,
                args=(dirs, self._queue, True),
            )
            self._process.start()
            self.loading = True
            self.set_status_text("Loading...")
            self.delete_btn.config(state="disabled")
            self.after(100, self._poll_queue)
        else:
            # Just list directories without sizes
            for dir_path in dirs:
                entry: dict[str, object] = {
                    "name": dir_path,
                    "path": dir_path,
                    "is_dir": True,
                    "size": "-",
                }
                self.dir_entries.append(entry)
                display_name = self.get_display_name(entry)
                self.tree.insert(
                    "",
                    "end",
                    iid=str(dir_path),
                    text=display_name,
                    values=("-",),
                    tags=("dir",),
                )

        # Update status text and delete button
        if self.loading:
            self.set_status_text("Loading...")
        else:
            self.set_status_text("Directory size: -")
        self.delete_btn.config(state="disabled")

    def refresh_list_view_by_child_items(self) -> None:
        """Refresh the list view to show items under the selected directory."""
        # Prevent double loading
        if self.loading:
            return

        # Reset state
        self.set_status_text("Loading...")
        self.delete_btn.config(state="disabled")
        self.tree.delete(*self.tree.get_children())

        # Use multiprocessing to load directory contents
        self.loading = True
        self._queue = multiprocessing.Queue()
        self._process = multiprocessing.Process(
            target=DiskCleanerApp._get_entries_process,
            args=(self.selected_dir_path, self._queue, self.show_dir_sizes.get()),
        )
        self._process.start()
        self.after(100, self._poll_queue)

    @staticmethod
    def _get_entries_process(
        target_or_targets: str | list[str],
        queue: multiprocessing.Queue[
            tuple[str, str] | tuple[str, list[dict[str, object]]]
        ],
        show_dir_sizes: bool = True,
    ) -> None:
        """Get file and directory entries under the specified target directory or directories.

        targets: directory path or list of directory paths
        queue: multiprocessing.Queue for inter-process communication
        show_dir_sizes: bool
        """
        # Determine if target_or_targets is a single path or a list
        if isinstance(target_or_targets, str):
            target_path = target_or_targets
            target_paths = [
                os.path.join(target_path, c) for c in os.listdir(target_path)
            ]
            sets_name_to_path = False
        else:
            target_paths = target_or_targets
            sets_name_to_path = True

        # List entries
        entries: list[dict[str, object]] = []
        for target_path in target_paths:
            # Report progress
            queue.put(("progress", target_path))

            # Skip if path does not exist
            if not target_path or not os.path.exists(target_path):
                continue

            # Check if the path is a directory
            if os.path.isdir(target_path):
                # Get the list of items under the directory
                try:
                    size = (
                        get_directory_size(target_path, queue)
                        if show_dir_sizes
                        else "-"
                    )
                except Exception:
                    size = 0 if show_dir_sizes else "-"
                entry_dict: dict[str, object] = {
                    "name": (
                        target_path
                        if sets_name_to_path
                        else os.path.basename(target_path)
                    ),
                    "path": target_path,
                    "is_dir": True,
                    "size": size,
                }
                entries.append(entry_dict)
            else:
                # Get file size
                try:
                    size = os.path.getsize(target_path) if show_dir_sizes else "-"
                except Exception:
                    size = 0 if show_dir_sizes else "-"
                entry: dict[str, object] = {
                    "name": os.path.basename(target_path),
                    "path": target_path,
                    "is_dir": False,
                    "size": size,
                }
                entries.append(entry)

        # Add result to queue
        queue.put(("result", entries))

    def _poll_queue(self) -> None:
        """Poll the queue for updates from the background process."""
        # Check if the queue exists
        if not hasattr(self, "_queue") or self._queue is None:
            return

        # Try to get a message from the queue
        try:
            msg = self._queue.get_nowait()
            if isinstance(msg, tuple) and msg[0] == "progress":
                # Update status text with progress
                dir_path = msg[1]
                self.set_status_text(f"Loading...{dir_path}")
                self.after(100, self._poll_queue)
            elif isinstance(msg, tuple) and msg[0] == "result":
                # Update UI with the final result
                entries = msg[1]
                self._update_dir_view_ui(entries)

                # Clean up
                if hasattr(self, "_process"):
                    self._process.join(timeout=0.1)
                    del self._process
                del self._queue
        except Exception:
            self.after(100, self._poll_queue)

    def _update_dir_view_ui(self, entries: list[dict[str, object]]) -> None:
        """Update the directory view UI with the given entries."""
        # Update the Treeview with the given entries
        self.dir_entries = entries
        self.tree.delete(*self.tree.get_children())
        for entry in entries:
            tag = "dir" if entry["is_dir"] else "file"
            display_name = self.get_display_name(entry)
            display_size = (
                "{:,}".format(entry["size"])
                if isinstance(entry["size"], int)
                else entry["size"]
            )
            self.tree.insert(
                "",
                "end",
                iid=str(entry["path"]),
                text=display_name,
                values=(display_size,),
                tags=(tag,),
            )

        # Update status text and delete button
        dir_size_str = "-"
        if self.show_dir_sizes.get() and self.selected_dir_path is not None:
            dir_size_str = "{:,} bytes".format(
                get_directory_size(self.selected_dir_path)
            )
        self.set_status_text(f"Directory size: {dir_size_str}")
        self.delete_btn.config(state="normal")

        # Reset loading state
        self.loading = False

    def on_toggle_dir_sizes(self) -> None:
        """Handle toggling of the Show directory sizes checkbox."""
        # If loading, terminate the current process to cancel loading
        if getattr(self, "loading", False):
            self.loading = False
            self.set_status_text("")
            self.delete_btn.config(state="disabled")
            self.tree.delete(*self.tree.get_children())
        if hasattr(self, "_process"):
            try:
                self._process.terminate()
            except Exception:
                pass
            del self._process
        if hasattr(self, "_queue"):
            del self._queue

        # Refresh the list view
        if self.selected_dir_path is None:
            self.refresh_list_view_by_target_dirs()
        else:
            self.refresh_list_view_by_child_items()

    def on_tree_heading_click(self, column: str) -> None:
        """Handle clicking on a column header to sort the list."""
        # Determine sort order
        if self.sort_column == column:
            self.sort_reverse = not self.sort_reverse
        else:
            self.sort_column = column
            self.sort_reverse = False

        # Execute sorting
        if column == "name":
            entries = sorted(
                self.dir_entries,
                key=lambda e: str(e["name"]).lower(),
                reverse=self.sort_reverse,
            )
        elif column == "size":
            entries = sorted(
                self.dir_entries,
                key=lambda e: (e["size"] if isinstance(e["size"], int) else 0),
                reverse=self.sort_reverse,
            )
        else:
            entries = self.dir_entries

        # Update UI
        self._update_dir_view_ui(entries)

    def on_tree_double_click(self, event: tk.Event) -> None:
        """Handle double-clicking on an item in the list to navigate into a directory."""
        # Get selected item
        item_id = self.tree.focus()
        if not item_id:
            return
        entry = next(
            (e for e in self.dir_entries if str(e["path"]) == str(item_id)), None
        )

        # If it's a directory, navigate into it
        if entry and entry["is_dir"]:
            self.selected_dir_path = str(entry["path"])
            self.refresh_list_view_by_child_items()
            self.update_breadcrumbs()

    def on_delete(self) -> None:
        """Handle deletion of selected items."""
        # Get selected items
        selected = self.tree.selection()
        if not selected:
            messagebox.showinfo("Delete", "Please select items to delete.")
            return

        # Confirm deletion
        confirm = messagebox.askyesno(
            "Confirm", "Are you sure you want to delete the selected items?"
        )
        if not confirm:
            return

        # Delete selected items
        delete_items([str(s) for s in selected])

        # Refresh the list view
        self.refresh_list_view_by_child_items()

    def update_breadcrumbs(self) -> None:
        """Update the breadcrumb navigation display."""
        # Clear existing widgets
        for widget in self.breadcrumb_inner_frame.winfo_children():
            widget.destroy()

        # First item is either "Target Directories" label or button
        if self.selected_dir_path is None:
            # Just a label for target directories
            lbl = tk.Label(
                self.breadcrumb_inner_frame, text="Target Directories", relief=tk.FLAT
            )
            lbl.pack(side="left", padx=2, pady=2)
            self.breadcrumb_canvas.update_idletasks()
            self.breadcrumb_canvas.configure(
                scrollregion=self.breadcrumb_canvas.bbox("all")
            )
            return
        else:
            # Button to go back to target directories
            btn = tk.Button(
                self.breadcrumb_inner_frame,
                text="Target Directories",
                relief=tk.FLAT,
                command=lambda: self.on_breadcrumb_click(""),
            )
            btn.pack(side="left")
            sep = tk.Label(self.breadcrumb_inner_frame, text=" > ")
            sep.pack(side="left")

        # Breadcrumb navigation
        home_dir = os.path.expanduser("~")
        parts = []
        path = self.selected_dir_path
        matched_target_dir = ""
        target_dir_paths = load_target_directories(
            Platform.MAC
            if is_mac()
            else Platform.WINDOWS if is_windows() else Platform.OTHER
        )
        for target_dir_path in target_dir_paths:
            if path == target_dir_path or path.startswith(target_dir_path + os.sep):
                parts.append((target_dir_path, target_dir_path))
                matched_target_dir = target_dir_path
                break
        while path != matched_target_dir:
            head, tail = os.path.split(path)
            if tail:
                parts.insert(1, (tail, path))
                path = head
            else:
                if head:
                    parts.insert(1, (head, head))
                break

        def shorten_path(p: str) -> str:
            """Shorten the path by replacing home directory with "~"."""
            if isinstance(p, str) and p.startswith(home_dir):
                return p.replace(home_dir, "~", 1)
            return str(p)

        # Create buttons/labels for each part
        # - Last part is a label, others are buttons
        for i, (name, full_path) in enumerate(parts):
            # Shorten the display name if possible
            display_name = shorten_path(name)

            # Create button or label
            if i == len(parts) - 1:
                lbl = tk.Label(
                    self.breadcrumb_inner_frame, text=display_name, relief=tk.FLAT
                )
                lbl.pack(side="left")
            else:

                from typing import Callable

                def make_callback(p: str) -> Callable[[], None]:
                    return lambda: self.on_breadcrumb_click(p)

                btn = tk.Button(
                    self.breadcrumb_inner_frame,
                    text=display_name,
                    relief=tk.FLAT,
                    command=make_callback(full_path),
                )
                btn.pack(side="left")

            # Separator
            if i < len(parts) - 1:
                sep = tk.Label(self.breadcrumb_inner_frame, text=" > ")
                sep.pack(side="left")

        # Update canvas scroll region
        self.breadcrumb_canvas.update_idletasks()
        self.breadcrumb_canvas.configure(
            scrollregion=self.breadcrumb_canvas.bbox("all")
        )

    def on_breadcrumb_click(self, path: str) -> None:
        """Handle clicking on a breadcrumb item to navigate."""
        if not path:
            self.refresh_list_view_by_target_dirs()
            self.update_breadcrumbs()
        elif path != self.selected_dir_path:
            self.selected_dir_path = str(path)
            self.refresh_list_view_by_child_items()
            self.update_breadcrumbs()


if __name__ == "__main__":
    init_admin_db()
    app = DiskCleanerApp()
    app.mainloop()
