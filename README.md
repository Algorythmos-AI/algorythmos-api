<div align="center">

# 📄 Algorythmos — Document Intelligence Platform

### Enterprise-grade document extraction & analysis platform

[![Next.js 14](https://img.shields.io/badge/Next.js-14-black)](https://nextjs.org)
[![FastAPI](https://img.shields.io/badge/FastAPI-0.117+-00a393.svg?logo=fastapi)](https://fastapi.tiangolo.com)
[![Python 3.11](https://img.shields.io/badge/python-3.11-blue.svg)](https://www.python.org)
[![TypeScript](https://img.shields.io/badge/TypeScript-5.0-blue)](https://www.typescriptlang.org)

**[🌐 Live Demo](https://api.algorythmos.fr/api/)** · **[📚 API Docs](https://api.algorythmos.fr/api/docs)**

</div>

---

## What is this?

**Algorythmos** is a full-stack document intelligence platform that automates data extraction from complex documents (invoices, contracts, forms).

It consists of two parts:
1.  **Frontend (Next.js 14)**: A modern, enterprise dashboard for managing files, schemas, and reviewing extracted data.
2.  **Backend (FastAPI)**: A high-performance API that handles PDF parsing, OCR, and data extraction.

### ✨ Key Features

-   **Drag & Drop Upload**: Upload PDFs and see extraction results instantly.
-   **Schema Management**: Define exactly what data you want to extract (fields, types, descriptions).
-   **LLM Studio**: Experiment with AI-powered summarization, Q&A, and entity extraction.
-   **Dashboard**: Real-time health metrics, recent runs, and system status.
-   **API Key Management**: Generate and revoke keys for programmatic access.
-   **Multi-tenant**: Built for enterprise with data isolation per tenant.

---

## 🚀 Quick Start (Full Stack)

Follow these steps to run the entire platform locally.

### Prerequisites
-   **Node.js 18+** (for frontend)
-   **Python 3.11** (for backend)
-   **Git**

### 1. Download the project
```bash
git clone https://github.com/skalaliya/api-algorythmos.git
cd api-algorythmos
```

### 2. Setup Backend (API)
The backend runs on port `8000`.

```bash
# Install dependencies using uv (or pip)
curl -LsSf https://astral.sh/uv/install.sh | sh
uv sync

# Create environment file
cat > .env << EOF
ALG_API_KEY=test-api-key
ALG_TENANT_ID=test-tenant
ENV=dev
EOF

# Initialize database
uv run alembic upgrade head

# Start server
uv run uvicorn app:app --reload
```
*Backend is now running at [http://localhost:8000](http://localhost:8000)*

### 3. Setup Frontend (Dashboard)
The frontend runs on port `3000`. Open a new terminal tab:

```bash
cd frontend

# Install dependencies
npm install

# Create environment file
cat > .env.local << EOF
NEXT_PUBLIC_API_URL=http://localhost:8000/api
EOF

# Start development server
npm run dev
```
*Frontend is now running at [http://localhost:3000](http://localhost:3000)*

---

## 🛠 Usage Guide

### 1. Access the Dashboard
Open **[http://localhost:3000](http://localhost:3000)** in your browser.

### 2. Configure Authentication
To connect the frontend to your local backend:
1.  Go to **Settings** → **API Keys**.
2.  Enter the key `test-api-key` (configured in your backend `.env`).
3.  The frontend will now authenticate all requests using this key.

### 3. Upload & Extract
1.  Navigate to **Upload & Extract**.
2.  Drag and drop a PDF file (e.g., an invoice).
3.  Select a Schema (or use "Auto-detect").
4.  Click **Extract Data**.
5.  View the JSON results or Table view side-by-side with the PDF.

---

## ⚙️ Configuration

### Backend Environment (`.env`)
| Variable | Required | Description |
|----------|:--------:|-------------|
| `ALG_API_KEY` | ✅ | Master API key for correct operation. |
| `ALG_TENANT_ID` | ✅ | Default tenant ID for local dev. |
| `DATABASE_URL` | No | SQLite used by default (`./dev.db`). Use Postgres for prod. |
| `STATE_BACKEND` | No | `memory` (default) or `redis`. |

### Frontend Environment (`frontend/.env.local`)
| Variable | Required | Description |
|----------|:--------:|-------------|
| `NEXT_PUBLIC_API_URL` | ✅ | URL of the backend API (e.g., `http://localhost:8000/api`). |
| `NEXT_PUBLIC_GOOGLE_CLIENT_ID`| No | For Google Sign-In (optional). |

---

## 🏗 Project Structure

```bash
api-algorythmos/
├── app.py                  # Backend Entry Point (FastAPI)
├── app/                    # Backend Core Logic
├── document_processing/    # PDF Extraction Engine
├── alembic/                # Database Migrations
├── tests/                  # Backend Tests
│
└── frontend/               # Frontend Application (Next.js)
    ├── app/                # App Router Pages (Dashboard, Upload, etc.)
    ├── components/         # React Components (UI Library)
    ├── lib/                # API Client & Utilities
    └── public/             # Static Assets
```

---

## 🧪 Testing

### Backend Tests
```bash
# Run unit tests
uv run pytest

# Run API verification script (tests live endpoints)
./verify_api.sh
```

### Frontend Tests
```bash
cd frontend
# Generate test PDFs
node generate_pdfs.js
```

---

## 🚢 Deployment

### Vercel (Recommended)
This repo is configured for Vercel. Both the Next.js frontend and Python backend can be deployed to Vercel.

1.  Push your code to GitHub.
2.  Import the repo in Vercel.
3.  Set the Environment Variables in Vercel project settings.
4.  Deploy!

---

<div align="center">
  <br/>
  Built with ❤️ by Algorythmos Team
  <br/>
  <a href="https://api.algorythmos.fr/api/docs">API Documentation</a> · <a href="https://github.com/skalaliya/api-algorythmos/issues">Report Bug</a>
</div>
