# MVP Scope

## Core MVP

### Users

Fields:

- id
- phone_number
- name
- created_at

### Cases

Fields:

- id
- user_id
- module
- status
- created_at

### Documents

Fields:

- id
- case_id
- type
- path
- ocr_text

### Messages

Fields:

- id
- case_id
- direction
- content

### Reminders

Fields:

- id
- case_id
- due_date
- status


## Day 6 - Document Classification v1

Pruvio can classify uploaded documents and text into service modules.

Supported classification outputs:

- receipt → split_bill
- invoice → refund_claim
- claim_document → refund_claim
- subscription_document → subscription
- qr_code → payment_assist
- unknown → unknown

Current classification is rule-based.

Future classification will use OCR text and AI extraction.