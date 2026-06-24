# Pruvio Architecture

## Vision

Pruvio is a WhatsApp-first modular assistant.

Users send:

- Receipts
- Invoices
- Screenshots
- QR Codes
- PDFs
- Text

Pruvio identifies the intent and activates the correct service module.

---

# Core Components

## Input Engine

Receives:

- WhatsApp Messages
- Images
- PDFs
- QR Codes

---

## Case Engine

Creates and manages cases.

Each user interaction belongs to a case.

Example:

Case #1 = Restaurant Bill Split

Case #2 = Refund Claim

Case #3 = Warranty Claim

---

## Document Engine

Stores:

- Original files
- OCR results
- Metadata

---

## Module Router

Chooses the correct module.

Examples:

- Split Bill
- Refund Claim
- Warranty
- Subscription

---

## Output Engine

Produces:

- WhatsApp Replies
- PDFs
- Payment Links
- Reminders

---

## Dashboard

Admin interface.

Functions:

- View users
- View cases
- View documents
- View OCR
- Trigger modules
