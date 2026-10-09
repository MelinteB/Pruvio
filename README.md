# Pruvs

Pruvs is a web application for receipt processing, OCR, bill splitting and related workflows.

## Structure

- `backend/app` - application code, API, services and UI
- `backend/migrations` - database migrations
- `backend/tests` - automated tests
- `docs` - project documentation

## Backend

Python application deployed on Render.

Main features include:

- Receipt OCR
- Azure Document Intelligence integration
- OpenAI OCR fallback
- Receipt translation
- Split bill
- User accounts and authentication
- Email notifications
- Receipt history

## Environment

Local configuration is stored in:

`.env`

The `.env` file must never be committed to Git.

Example configuration:

`.env.example`

## Run locally

Activate the virtual environment:

```powershell
.\.pvenv\Scripts\Activate.ps1