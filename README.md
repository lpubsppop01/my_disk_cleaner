# My Disk Cleaner

**my_disk_cleaner** is a cross-platform disk cleaning application for Windows and Mac, designed to help users identify and remove unnecessary files that accumulate during regular system use.

## Features

- **Platform Support:** Windows and Mac
- **Purpose:** Check and delete files that waste disk space, tailored to typical directories that grow over time on each OS.
- **GUI Desktop Application:** Built with Python and tkinter, providing an intuitive graphical interface.
- **Easy Setup:** Runs on standard Python environments; no external dependencies required for basic usage.
- **Smart Directory Selection:** Automatically selects initial target directories based on OS characteristics:
  - **Mac:** `~/Library/Caches` (commonly grows large)
  - **Windows:** `AppData/Local` (frequently accumulates unnecessary files)
- **Usage Overview:**
  - Displays the disk usage of the initial target directory.
  - Allows users to inspect subdirectories and files for more detailed analysis.
  - Enables selection and deletion of files and directories directly from the app.
- **Windows-Specific Considerations:** Handles hard links appropriately to avoid double-counting disk usage and ensure accurate space recovery.

## Getting Started

1. **Requirements:**  
   - Python 3.x (standard installation)
2. **Installation:**  
   - Clone this repository:
     ```
     git clone https://github.com/lpubsppop01/my_disk_cleaner.git
     ```
   - Run the application:
     ```
     python my_disk_cleaner.py
     ```
3. **Usage:**  
   - On launch, the app will display the size of the default target directory for your OS.
   - Browse, inspect, and select files or directories to delete as needed.

## Author

- **Name:** lpubsppop01
- **Email:** lpubsppop01@gmail.com

## License

License to be decided.
