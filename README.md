# CSV Script Manager

A web-based CSV file editor and script manager for processing CSV files with Python scripts, specifically designed for NCM (Network Control Manager) API operations.

## Features

- **CSV File Management**: Load, edit, and save CSV files through a modern web interface
- **Script Management**: Create, edit, download, and execute Python scripts that process CSV files
- **API Key Management**: Securely set and manage API keys through the web interface
- **GitHub Integration**: Download scripts directly from GitHub URLs (supports individual files and folders)
- **NCM Library Integration**: Automatically downloads and updates the `ncm.py` library from the Cradlepoint API samples repository
- **Cross-Platform**: Works on Windows, macOS, and Linux

## Screenshots

<img width="1645" height="854" alt="image" src="https://github.com/user-attachments/assets/42b3be8d-9b11-45f9-85dc-2e7b6118a85c" />
<img width="1645" height="854" alt="image" src="https://github.com/user-attachments/assets/22309051-02be-49c4-a320-81e72facd4c6" />
<img width="1645" height="854" alt="image" src="https://github.com/user-attachments/assets/86dbf08b-4570-43c9-a6ae-96e3737d18ba" />

## Installation

1. **Clone or download this repository**

2. **Install Python dependencies**:
   ```bash
   pip install -r requirements.txt
   ```

   This will install:
   - `requests` - For HTTP requests and downloading scripts from GitHub

3. **Run the application**:
   ```bash
   python csv_script_manager.py
   ```

   Or on Unix-like systems:
   ```bash
   python3 csv_script_manager.py
   ```

4. **Open your web browser** and navigate to:
   ```
   http://localhost:8000
   ```

## Usage

### Working with CSV Files

1. **Load a CSV file**: Click on a file from the list or upload a new one
2. **Edit data**: Modify cells directly in the web interface
3. **Save changes**: Click the save button to persist your changes
4. **Download**: Export your CSV file at any time

### Managing Scripts

1. **View available scripts**: All Python scripts in the `scripts/` directory are automatically listed
2. **Create new scripts**: Use the script editor to create new Python scripts
3. **Download from GitHub**: Paste a GitHub URL to download scripts directly
4. **Run scripts**: Select a script and CSV file, then execute them together

### Setting API Keys

The web interface allows you to securely set API keys as environment variables:

- `X_CP_API_ID` / `X_CP_API_KEY` - Cradlepoint API credentials
- `X_ECM_API_ID` / `X_ECM_API_KEY` - ECM API credentials
- `TOKEN` / `NCM_API_TOKEN` - NCM API token

**Note**: API keys are stored in environment variables for the current session only. They are not persisted between application restarts.

### Script Format

Scripts should follow a standardized format with detailed docstrings. See [SCRIPT_FORMAT_GUIDE.md](SCRIPT_FORMAT_GUIDE.md) for complete documentation on:
- Required docstring format
- CSV column naming conventions
- API key handling
- Script structure guidelines

## Project Structure

```
csv_script_manager/
├── csv_script_manager.py    # Main application file
├── ncm.py                   # NCM API library (auto-downloaded if missing)
├── requirements.txt         # Python dependencies
├── csv_files/               # Directory for CSV files
├── scripts/                 # Directory for Python scripts
│   ├── ncm_bulk_configure_devices.py
│   ├── ncm_get_router_status.py
│   ├── ncm_unregister_routers_batch.py
│   ├── ncm_v3_create_users.py
│   ├── ncm_v3_regrade_subscriptions_by_mac.py
│   └── ncm_v3_unlicense_devices_by_mac.py
├── static/                  # Web interface files
│   ├── index.html
│   ├── css/
│   └── js/
└── README.md
```

## NCM Library

The application automatically downloads the `ncm.py` library from the [Cradlepoint API samples repository](https://github.com/cradlepoint/api-samples) if it's missing or needs updating. This library provides the core functionality for interacting with the NCM API.

## Requirements

- Python 3.6 or higher
- `requests` library (installed via `requirements.txt`)

## License

See [LICENSE](LICENSE) file for details.
