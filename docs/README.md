# MultiCloud Platform — Project Documentation

## Group Members

| Name | Matriculation Number |
|------|----------------------|
| *(Member 1)* | *(Number)* |
| *(Member 2)* | *(Number)* |
| *(Member 3)* | *(Number)* |
| *(Member 4)* | *(Number)* |

---

## Purpose

**MultiCloud Platform** is a prototype multi-cloud file management service that lets users upload, download, transfer, and copy files between cloud storage providers (Google Drive and Microsoft OneDrive) through three interfaces:

1. **Local server** — a Flask REST API running on the user's PC
2. **Web application** — a browser-based single-page app
3. **Mobile application** — a responsive PWA for smartphones

The application simulates real cloud providers using local directories, making it fully runnable offline without any cloud accounts.

---

## Course Topics Implemented

| Topic | Where |
|-------|-------|
| **Object-Oriented Programming** | `cloud_provider.py`, `transfer.py`, `database.py`, `cli.py` |
| **Command Line Interface** | `cli.py` (argparse sub-commands) |
| **Database Integration** | `database.py` (SQLite via stdlib `sqlite3`) |
| **Web API** | `server/server.py` (Flask REST API, 10 endpoints) |
| **Web Interface** | `web/index.html` (browser SPA) |

---

## Project Structure

```
multicloud/
├── cloud_provider.py      # OOP: base class + Google/OneDrive providers + registry
├── transfer.py            # Transfer engine (copy/move between providers)
├── database.py            # SQLite database layer
├── cli.py                 # Command Line Interface (argparse)
├── server/
│   └── server.py          # Flask REST API server
├── web/
│   └── index.html         # Web front-end (SPA)
├── mobile/
│   └── mobile_app.html    # Mobile PWA front-end
├── config/
│   └── config.json        # Configuration file
├── tests/
│   └── test_multicloud.py # Unit tests (unittest)
├── requirements.txt
└── docs/                  # This documentation
```

---

## Implementation & Structure

### `cloud_provider.py` — OOP Core
- **`CloudException`** and subclasses (`FileNotFoundException`, `AuthenticationException`, `QuotaExceededException`) form a custom exception hierarchy.
- **`CloudFile`** is a data-holding class for file metadata with `to_dict()` serialisation.
- **`CloudProvider`** (abstract base class) defines `authenticate()`, `list_files()`, `upload()`, `download()`, `delete()`, `get_quota()` — enforced via `abc.ABC` and `@abstractmethod`.
- **`GoogleDriveProvider`** and **`OneDriveProvider`** are concrete implementations that use local directories as simulated cloud storage.
- **`ProviderRegistry`** is a class-level dictionary that maps provider names to instances, acting as a simple service locator.

### `transfer.py` — Transfer Engine
- **`TransferRecord`** (Python `@dataclass`) stores the outcome of each operation.
- **`TransferEngine`** orchestrates cross-provider transfers: download → buffer → upload → (optionally delete source). All state is kept in an in-memory history list.

### `database.py` — Database Integration
- Wraps Python's `sqlite3` standard library.
- Creates two tables automatically: `cloud_files` and `transfer_history`.
- Uses parameterised queries throughout to prevent SQL injection.
- WAL journal mode enables concurrent reads.

### `server/server.py` — Web API (Flask)
- Application factory pattern (`create_app()`).
- Ten REST endpoints under `/api/`.
- Providers are initialised once and stored on the app object.
- Delegates business logic to `CloudProvider`, `TransferEngine`, and `Database`.

### `cli.py` — Command Line Interface
- `CLIApp` class wraps the full CLI lifecycle.
- `argparse` with sub-commands: `list`, `upload`, `download`, `delete`, `copy`, `move`, `quota`, `history`, `providers`.
- All output is formatted for a terminal (aligned columns, progress indicators).

### `web/index.html` / `mobile/mobile_app.html` — Interfaces
- Pure HTML + CSS + JavaScript (no external frameworks).
- Communicate with the Flask API over `fetch()`.
- The mobile app is a PWA with bottom navigation and touch-friendly controls.

---

## Usage Examples

### 1. Start the server

```bash
pip install -r requirements.txt
cd multicloud
python server/server.py
```

Open `http://127.0.0.1:5000` in a browser for the web interface.  
Open `mobile/mobile_app.html` on your phone (update `SERVER_URL` to your PC's LAN IP first).

### 2. CLI — list files

```bash
python cli.py providers
python cli.py list --provider "Google Drive"
python cli.py list --provider "Microsoft OneDrive" --path /documents
```

### 3. CLI — upload a file

```bash
python cli.py upload --provider "Google Drive" --file ./report.pdf --path /docs
```

### 4. CLI — download a file

```bash
python cli.py download --provider "Google Drive" --id <file_id> --dest ./downloads
```

### 5. CLI — copy between providers

```bash
python cli.py copy --src "Google Drive" --dst "Microsoft OneDrive" --id <file_id>
```

### 6. CLI — check storage quota

```bash
python cli.py quota --provider "Google Drive"
```

### 7. Run tests

```bash
python -m pytest tests/ -v
# or without pytest:
python tests/test_multicloud.py
```

---

## API Reference (summary)

| Method | Endpoint | Description |
|--------|----------|-------------|
| GET | `/api/providers` | List registered providers |
| GET | `/api/files?provider=X` | List files on provider X |
| POST | `/api/upload` | Upload file (multipart form) |
| GET | `/api/download/<provider>/<id>` | Download file |
| DELETE | `/api/delete/<provider>/<id>` | Delete file |
| POST | `/api/transfer` | Copy or move between providers |
| GET | `/api/history` | Transfer history |
| GET | `/api/quota?provider=X` | Storage quota |
| GET | `/api/stats` | Platform statistics |

---

## Design Decisions

- **Simulation over real APIs**: Real OAuth2 flows require registered apps and browser redirects. The prototype uses local directories so the instructor can run it immediately without any cloud accounts.
- **Single-file web & mobile apps**: Keeping the front-ends as single HTML files avoids any build tooling; they can be opened directly in a browser.
- **`abc.ABC` for the provider interface**: Enforces the contract at import time — any provider that forgets to implement `upload()` raises a `TypeError` immediately.
- **SQLite via stdlib**: No additional database server needed; the `multicloud.db` file is created automatically in the project directory.
