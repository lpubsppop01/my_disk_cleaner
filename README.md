# My Disk Cleaner

**My Disk Cleaner** is a cross-platform disk cleanup application for Windows and Mac. It helps you easily find and delete unnecessary files and directories to free up disk space efficiently.

## Features

- **Cross-platform:** Works on both Windows and Mac
- **GUI Desktop Application:** Intuitive interface built with Python and tkinter
- **Target Directory Management:** Uses a local SQLite database to manage target directories and cache directory sizes
- **Preset Selection:** Easily select preset directories ("root", "user", "cache") for each OS with a single click
- **Directory Size Display:** Toggle directory size calculation with a checkbox; clear the size cache with a button
- **Multiprocessing for Performance:** Directory size calculation and file listing are performed in the background for fast and responsive UI
- **Windows Hard Link Support:** Avoids double-counting disk usage for accurate space calculation
- **No External Dependencies:** Runs with only the Python standard library (Python 3.11+ recommended for StrEnum support)

## Usage

1. **Requirements**  
   - Python 3.11 or later (StrEnum is used)
2. **Installation**  
   - Clone the repository:
     ```
     git clone https://github.com/lpubsppop01/my_disk_cleaner.git
     ```
   - Run the application:
     ```
     python my_disk_cleaner.py
     ```
3. **Basic Operations**  
   - On launch, the app displays a list of preset target directories for your OS
   - Use the "Edit Target Directories" button to modify the target directories
   - Switch presets easily with "Reset by root dir", "Reset by user dirs", or "Reset by cache dirs" buttons
   - Toggle "Show directory sizes" to enable/disable size calculation
   - Use the "Clear Cache" button to clear cached directory sizes
   - Select files or directories and click "Delete Selected Items" to remove them
   - Navigate directory hierarchy using the breadcrumb navigation

## Preset Directory Examples

- **Mac**
  - root: All directories under `/`
  - user: All directories under `~/`
  - cache: `~/Desktop`, `~/Downloads`, `~/Library/Application Support`, `~/Library/Caches`, etc.
- **Windows**
  - root: All directories under `C:\`
  - user: All directories under `~\`
  - cache: `~\AppData\Local\npm-cache`, `~\AppData\Local\Packages`, `~\AppData\Local\Temp`, `C:\Windows\Temp`, etc.

## About the Database

- The management SQLite database (`admin.db`) is automatically created and stores target directories and cached directory sizes
- The database is located in the user's local environment (Windows: under `LOCALAPPDATA`, Mac: under `~/.lpubsppop01_my_disk_cleaner`)

## Author

[lpubsppop01](https://github.com/lpubsppop01)

## License

[zlib License](https://github.com/lpubsppop01/my_disk_cleaner/raw/master/LICENSE.txt)

