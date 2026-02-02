# Janki Chatbot Backend

FastAPI backend for Janki chatbot with Google Vertex AI Agent integration.

## Setup Instructions

### 1. Install Dependencies

```bash
cd backend
pip install -r requirements.txt
```

### 2. Configure Environment Variables

1. Copy `.env.example` to `.env`:
   ```bash
   cp .env.example .env
   ```

2. Update `.env` with your configuration:
   - `GOOGLE_CLOUD_PROJECT_ID`: Your Google Cloud project ID
   - `GOOGLE_CLOUD_LOCATION`: Your Google Cloud region (e.g., `us-central1`)
   - `GOOGLE_APPLICATION_CREDENTIALS`: Path to your service account JSON key file
   - `GOOGLE_OAUTH_CLIENT_ID`: Your Google OAuth Client ID (e.g., `931247202536-umuto0b7bo9j74s684gan29q8qpi3rs1.apps.googleusercontent.com`)
   - `VERTEX_AI_AGENT_ID`: Your Vertex AI Agent ID
   - `VERTEX_AI_AGENT_LOCATION`: Location of your agent (e.g., `us-central1`)
   - `NEXTAUTH_SECRET`: Same secret used in your Next.js frontend

### 3. Set Up Google Cloud Credentials

Option 1: Service Account Key File
- Download a service account JSON key from Google Cloud Console
- Set `GOOGLE_APPLICATION_CREDENTIALS` to the path of this file

Option 2: Application Default Credentials (ADC)
- Run: `gcloud auth application-default login`
- Leave `GOOGLE_APPLICATION_CREDENTIALS` empty

### 4. Run the Server

```bash
python run.py
```

Or using uvicorn directly:
```bash
uvicorn app.main:app --reload --host 0.0.0.0 --port 8000
```

The API will be available at `http://localhost:8000`

## API Endpoints

- `GET /` - Health check
- `GET /health` - Health check
- `POST /api/v1/auth/verify` - Verify Google OAuth token
- `POST /api/v1/chat` - Send chat message to Vertex AI Agent

## Frontend Configuration

Make sure your frontend `.env.local` includes:
```
NEXT_PUBLIC_API_URL=http://localhost:8000
```

