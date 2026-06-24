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
