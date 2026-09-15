PDF Safe Normalizer

Batch PDF Compatibility & Structural Normalization Tool • 100% Local-First & Privacy-Preserving


PDF Safe Normalizer is a cross-platform, local-first web application designed for batch normalization of PDF documents. It creates clean, structurally simplified PDFs that downstream medical, office, and archival systems can reliably process without rejection due to unsupported or problematic PDF structures.



🎯 Purpose & Design Principles


No Visual Content Alteration: Preserves physical page dimensions, orientation, vector layout, QR codes, stamps, signatures, tables, watermarks, and visual appearance exactly.

100% Local-First & Privacy: PDF files are never uploaded to any cloud service, external API, or third-party server. The backend binds strictly to 127.0.0.1.

Cross-Platform: Operates identically on macOS, Windows, and Linux without platform-specific assumptions.

Large Batch Resiliency: Handles large batches (10 to 1,000+ files) via an asynchronous, memory-controlled queue. Failures in individual files are isolated and never halt the batch.





⚙️ Processing Modes




Mode
Workflow
Best Used For




Automatic (Default / Recommended)
Inspects document $\rightarrow$ Attempts Standard Normalization $\rightarrow$ Validates output. If validation fails or forbidden actions persist $\rightarrow$ Automatically falls back to Maximum Compatibility (ASCIIHex) $\rightarrow$ Validates output.
General daily workflow across varied document sources.


Standard
Strips dangerous objects (/JS, /AA, /OpenAction, /Launch, /EmbeddedFiles, /XFA, /AcroForm, annotations) while preserving vector paths, fonts, and text layers.
Clean document pipelines where selectable text and minimal file size are required.


Maximum Compatibility
Renders every page at high resolution (150–300 DPI) $\rightarrow$ Encodes image stream using pure ASCIIHex (/Filter /ASCIIHexDecode) $\rightarrow$ Constructs a pristine PDF with 1 image/page and zero active features $\rightarrow$ Validates.
Strict downstream office / medical sanitizers that reject complex structures or raw signatures (e.g. signature literal still ditemukan: /JS=2).






📂 File Handling & AppleDouble Filtering

The directory scanner automatically filters system metadata and non-PDF files:

001.pdf, 002.PDF $\rightarrow$ PROCESSED

._001.pdf (macOS AppleDouble metadata) $\rightarrow$ SAFELY IGNORED

.DS_Store, Thumbs.db, desktop.ini $\rightarrow$ SAFELY IGNORED

notes.txt, image.png, ~$lock.pdf $\rightarrow$ SAFELY IGNORED



Safe Collision Handling
Outputs are saved as [filename]_clean.pdf. If a file already exists in the destination folder, the application safely increments to [filename]_clean_1.pdf without overwriting source or existing output files.



🏗️ Architecture

RS SATITI/BPJS/
├── backend/
│   ├── app/
│   │   ├── main.py                 # FastAPI application & static mounting
│   │   ├── config.py               # Local settings & limits
│   │   ├── api/
│   │   │   ├── routes.py           # REST endpoints & SSE progress stream
│   │   │   └── system.py           # Diagnostics & local directory browser
│   │   ├── pdf/
│   │   │   ├── inspector.py        # PDF object tree inspector
│   │   │   ├── standard_normalizer.py # Vector/text cleaning engine
│   │   │   ├── max_compat_normalizer.py # Page renderer + ASCIIHex builder
│   │   │   ├── asciihex.py         # Pure ISO 32000-1 ASCIIHex stream encoder
│   │   │   └── pipeline.py         # Pipeline coordinator (Auto/Standard/MaxCompat)
│   │   ├── validators/
│   │   │   └── validator.py        # 5-stage structural & rendering validator
│   │   ├── services/
│   │   │   ├── fs_scanner.py       # Cross-platform scanner (ignores ._*, .DS_Store, etc.)
│   │   │   ├── batch_processor.py  # Async queue & SSE broadcaster
│   │   │   └── system_diag.py      # Cross-platform engine diagnostics
│   │   └── utils/
│   │       ├── path_utils.py       # Collision handling
│   │       └── logger.py           # Technical logger (no document content logged)
│   └── requirements.txt
├── frontend/
│   ├── src/
│   │   ├── components/             # FolderSelector, ModeSelector, ProgressCard, LiveLog, ResultTable, Modals
│   │   ├── services/api.js         # API client & EventSource stream
│   │   ├── App.jsx                 # Workspace view
│   │   └── index.css               # Modern utility design system
│   ├── package.json
│   └── vite.config.js
├── tests/                          # Automated test suite (15 unit/integration tests)
├── scripts/
│   ├── start.py                    # Cross-platform unified Python launcher
│   ├── run_dev.sh                  # Development runner
│   ├── run_prod.sh                 # Production runner
│   └── run_tests.sh                # Test runner
└── README.md
Copy



🚀 Getting Started

Prerequisites

Python 3.10+ (Tested on Python 3.12)

Node.js 18+ & npm



(Optional) Ghostscript (gs / gswin64c) can be installed on the system for additional PDF operations; the application includes native PyMuPDF and Pillow engines so it works out of the box even without Ghostscript.



Installation


Clone or Navigate to the project directory:
cd "/Users/bayu/Documents/Kerja/RS SATITI/BPJS"
Copy

Create Python Virtual Environment and Install Dependencies:
python3 -m venv .venv
source .venv/bin/activate    # On Windows: .venv\Scripts\activate
pip install -r backend/requirements.txt
Copy

Install Frontend Dependencies & Build:
cd frontend
npm install
npm run build
cd ..
Copy





Running the Application

Option 1: Cross-Platform Universal Launcher (Recommended)
python3 scripts/start.py
Copy
Automatically checks dependencies, builds the frontend if needed, launches the server on http://127.0.0.1:8000, and opens your default browser.

Option 2: Production Shell Script
./scripts/run_prod.sh
Copy

Option 3: Development Mode (Hot Reload)
./scripts/run_dev.sh
Copy

Backend runs on http://127.0.0.1:8000

Vite frontend runs on http://127.0.0.1:5173





🧪 Running Automated Tests

Run the complete test suite (file filtering, structural inspection, ASCIIHex encoding, standard normalization, max compat pipeline, batch error isolation, and golden test case):

# Using helper script
./scripts/run_tests.sh

# Or directly with pytest
source .venv/bin/activate
pytest tests/ -v
Copy



🔍 Validation Pipeline

Every generated output file undergoes a 5-stage validation:

File Existence & Size: Verifies the file is written and non-zero bytes.

Parser & XRef Integrity: Verifies header, cross-reference table, and trailer.

Page Count & Order: Verifies page count matches expected source count.

Page Rendering: Renders every single page to verify streams are corruption-free.

Structural Safety: Traverses object tree to guarantee no forbidden triggers (/JS, /AA, /OpenAction, /Launch, /EmbeddedFiles, /XFA) remain.





🛠️ Troubleshooting




Issue
Cause
Solution




Address already in use
Another process is using port 8000
Set custom port: PORT=8080 python3 scripts/start.py


Ghostscript not found
Ghostscript is not in system PATH
Optional. Native PyMuPDF engine is active. To install Ghostscript: brew install ghostscript (macOS) or sudo apt install ghostscript (Linux).


AppleDouble files showing up
Network share or macOS Finder copy
The application automatically ignores ._* files during scanning and processing.


Rejection by downstream office system (/JS=2)
Strict scanner rejected active signatures
Use Automatic or Maximum Compatibility mode. The ASCIIHex rendering workflow eliminates all signature action dictionaries while preserving visual stamps.






📄 License & Privacy Notice
This software is intended for local on-premise execution. It contains no telemetry, analytics, or external API calls.
