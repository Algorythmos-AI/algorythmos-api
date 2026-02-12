# Algorythmos Frontend

Enterprise-grade document intelligence dashboard built with Next.js 14, React 19, and TypeScript.

## 🚀 Quick Start

```bash
# Install dependencies
npm install

# Setup environment
cp .env.example .env.local

# Run development server
npm run dev
```

Open [http://localhost:3000](http://localhost:3000) with your browser to see the result.

## 🛠 Tech Stack

-   **Framework**: Next.js 14 (App Router)
-   **Language**: TypeScript
-   **Styling**: CSS Modules (Scoped CSS) + Global Tokens (`app/globals.css`)
-   **Icons**: Lucide React
-   **Charts**: Recharts
-   **API Client**: Custom `fetch` wrapper with typed interfaces (`lib/api.ts`)

## 📂 Project Structure

```bash
frontend/
├── app/                    # App Router (Pages & Layouts)
│   ├── dashboard/          # Analytics Dashboard
│   ├── upload/             # Upload & Extraction Interface
│   ├── extractors/         # CRUD for Extractors
│   ├── schemas/            # CRUD for Schemas
│   ├── settings/           # API Keys & Config
│   └── globals.css         # Global Styles & Variables
│
├── components/             # Reusable UI Components
│   ├── ui/                 # Buttons, inputs, modals (Design System)
│   └── layout/             # Sidebar, TopBar
│
├── lib/                    # Core Utilities
│   ├── api.ts              # API Client (Auth, Error Handling)
│   ├── types.ts            # TypeScript Interfaces
│   └── utils.ts            # Helper functions
│
└── public/                 # Static Assets
```

## 🔐 Environment Variables (.env.local)

| Variable | Description |
|----------|-------------|
| `NEXT_PUBLIC_API_URL` | The URL of the backend API (e.g. `http://localhost:8000/api`) |
| `NEXT_PUBLIC_GOOGLE_CLIENT_ID` | Optional: Your Google OAuth Client ID |

## 📜 Available Scripts

| Command | Description |
|---------|-------------|
| `npm run dev` | Starts the development server on port 3000 |
| `npm run build` | Builds the application for production |
| `npm run start` | Starts the production server |
| `npm run lint` | Runs ESLint to check for code quality issues |

## 🧪 Testing

We use a custom test generator script to create realistic test PDFs.

```bash
# Generate test PDFs in frontend/test-files/
node generate_pdfs.js
```

## 🎨 Design System

The application uses a custom design system defined in `app/globals.css`. Key concepts:
-   **Variables**: All colors, spacing, and typography are CSS variables.
-   **Dark Mode**: The theme is dark by default, optimized for data density.
-   **Responsive**: All layouts adapt to mobile and desktop screens.
