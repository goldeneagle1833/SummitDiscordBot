# Summit Web App

A lightweight Flask web application for the Summit community.

## Setup

1. **Create a virtual environment** (recommended):
   ```bash
   python -m venv venv
   venv\Scripts\activate  # Windows
   ```

2. **Install dependencies**:
   ```bash
   pip install -r requirements.txt
   ```

3. **Run the app**:
   ```bash
   python app.py
   ```

4. **Open in browser**:
   Navigate to `http://localhost:5000`

## Project Structure

```
web-app/
├── app.py              # Main Flask application
├── requirements.txt    # Python dependencies
├── README.md          # This file
├── templates/         # HTML templates
│   ├── index.html     # Home page
│   └── about.html     # About page
└── static/            # Static assets
    └── css/
        └── style.css  # Stylesheet
```

## API Endpoints

- `GET /` - Home page
- `GET /about` - About page
- `GET /api/status` - API health check (returns JSON)

## Development

The app runs in debug mode by default, so changes to Python files will auto-reload the server.
