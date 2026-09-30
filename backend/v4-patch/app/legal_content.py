import os

TERMS_VERSION = "draft-2026-09-29"
PRIVACY_VERSION = "draft-2026-09-29"

LEGAL_ENTITY_NAME = os.getenv("PRUVIO_LEGAL_ENTITY_NAME", "[LEGAL ENTITY NAME]")
LEGAL_CONTACT_EMAIL = os.getenv("PRUVIO_LEGAL_CONTACT_EMAIL", "support@pruvio.app")
LEGAL_ADDRESS = os.getenv("PRUVIO_LEGAL_ADDRESS", "[REGISTERED ADDRESS]")

TERMS_TITLE = "Pruvio Terms of Use — Draft"
PRIVACY_TITLE = "Pruvio Privacy Notice — Draft"

TERMS_SECTIONS = [
    (
        "1. About Pruvio",
        f"These Terms govern your use of Pruvio, currently operated by {LEGAL_ENTITY_NAME}. "
        "Pruvio helps users upload receipts, extract receipt data using OCR, translate item names, "
        "store receipt information and calculate shared expenses. These Terms are a product-stage draft "
        "and should be reviewed by qualified legal counsel before commercial launch.",
    ),
    (
        "2. Eligibility and account",
        "You must provide accurate registration information and keep access to your verified email and phone number. "
        "You are responsible for activity performed through your authenticated session. Pruvio may restrict or suspend "
        "accounts used fraudulently, unlawfully or in a way that harms the service or other users.",
    ),
    (
        "3. Verification and security",
        "Pruvio may require one-time verification codes by email and SMS and may support passkeys through WebAuthn. "
        "Passkeys can use device security such as fingerprint, face recognition, device PIN, Windows Hello or a security key. "
        "Biometric templates remain under the control of your device/platform and are not sent to Pruvio. Verification codes are "
        "time-limited and must not be shared. You should contact support if you suspect unauthorized access to your account.",
    ),
    (
        "4. Receipt processing",
        "Receipt OCR, language detection, translation and item extraction are automated and may contain errors. You must "
        "review quantities, prices, currencies, totals and translations before relying on them. The original receipt or "
        "merchant record remains the authoritative source.",
    ),
    (
        "5. Split-bill calculations",
        "Pruvio provides calculation and coordination tools only. It does not guarantee that participants will pay, does "
        "not settle disputes between participants and, unless a separate regulated payment service is expressly offered, "
        "does not hold or transfer money on behalf of users.",
    ),
    (
        "6. User content",
        "You retain ownership of receipts and other content you upload. You grant Pruvio the limited right to process, "
        "store, transform and transmit that content only as needed to provide, secure and improve the service. You must "
        "have the right to upload the content you submit.",
    ),
    (
        "7. Prohibited use",
        "You must not use Pruvio to commit fraud, impersonate others, upload unlawful content, attempt unauthorized access, "
        "interfere with service operation, reverse engineer security controls, abuse OTP delivery, or process personal data "
        "where you do not have a lawful basis to do so.",
    ),
    (
        "8. Third-party services",
        "Pruvio may rely on hosting, OCR, translation, email and SMS providers. Their availability can affect the service. "
        "Where required, those providers are used as processors or independent service providers under their applicable terms.",
    ),
    (
        "9. Fees",
        "The current test version may be offered without charge. Pruvio may introduce paid plans or usage limits later. "
        "Any paid feature will display its price and material conditions before purchase.",
    ),
    (
        "10. Availability and changes",
        "The service is provided on a development-stage basis and may change, be interrupted or contain defects. Features, "
        "limits and integrations may be modified as the product evolves. Material changes to these Terms will be presented "
        "for acceptance when legally required.",
    ),
    (
        "11. Intellectual property",
        "The Pruvio name, software, visual design and service materials are protected by applicable intellectual-property laws. "
        "These Terms do not transfer ownership of Pruvio technology to users.",
    ),
    (
        "12. Disclaimers",
        "Pruvio is not accounting, tax, legal or financial advice. Automated OCR and translation can be inaccurate. You remain "
        "responsible for checking source documents and complying with tax, reimbursement, accounting and other obligations that "
        "apply to you.",
    ),
    (
        "13. Liability",
        "To the maximum extent permitted by applicable law, Pruvio is not responsible for indirect or consequential loss caused "
        "by inaccurate extraction, translation, participant choices, third-party outages or loss of access. Nothing in these Terms "
        "excludes liability that cannot legally be excluded, including mandatory consumer rights.",
    ),
    (
        "14. Termination and deletion",
        "You may stop using Pruvio at any time and may request account deletion. Pruvio may suspend or terminate access for serious "
        "or repeated violations, security threats or legal requirements. Some records may be retained where required by law or for "
        "security, fraud prevention and dispute handling.",
    ),
    (
        "15. Governing law and consumers",
        "The final governing-law and jurisdiction clause must be completed before launch. Mandatory consumer protections and rights "
        "available under the law of a user's country are not waived by this draft.",
    ),
    (
        "16. Contact",
        f"Questions about these Terms can be sent to {LEGAL_CONTACT_EMAIL}. Operator address: {LEGAL_ADDRESS}.",
    ),
]

PRIVACY_SECTIONS = [
    (
        "1. Controller",
        f"The intended controller for Pruvio user data is {LEGAL_ENTITY_NAME}, {LEGAL_ADDRESS}. Privacy contact: {LEGAL_CONTACT_EMAIL}. "
        "The controller details are placeholders until the operating legal entity is finalized.",
    ),
    (
        "2. Data we process",
        "Depending on the features you use, Pruvio may process your name, email address, phone number, verification status, account "
        "preferences, uploaded receipt images/PDFs, merchant and line-item data, split-bill selections, session information, support "
        "messages, technical logs, security events, passkey public credential data and limited device/browser information. Pruvio does "
        "not receive or store the fingerprint or face template used by your device to unlock a passkey.",
    ),
    (
        "3. Why we process data",
        "We process account and receipt data to provide the service, authenticate users, process receipts, calculate shared expenses, "
        "maintain history, provide support and prevent abuse. Security and service-integrity processing may rely on legitimate interests. "
        "Optional marketing or non-essential notifications should only be used where an appropriate consent or other lawful basis exists.",
    ),
    (
        "4. OCR, translation and automation",
        "Receipt images and extracted text may be sent to configured OCR and translation providers. Automated systems identify receipt "
        "fields, languages and translations. These outputs may be inaccurate and are presented for user review rather than as solely "
        "automated decisions producing legal or similarly significant effects.",
    ),
    (
        "5. Service providers",
        "Pruvio may use cloud hosting, database, OCR, translation, email, SMS, monitoring and support providers. Before production launch, "
        "the final notice should identify material provider categories and, where appropriate, named providers and international-transfer safeguards.",
    ),
    (
        "6. International transfers",
        "Where data is processed outside your country or the EEA, Pruvio will use an appropriate transfer mechanism where required, such "
        "as an adequacy decision, Standard Contractual Clauses or another lawful safeguard.",
    ),
    (
        "7. Retention",
        "This prototype does not yet define final retention periods. Before launch, Pruvio should establish documented periods for account data, "
        "receipt files, extracted data, OTP records, audit/security logs and support records. Users should be able to delete receipts and request "
        "account deletion subject to legally required retention.",
    ),
    (
        "8. Security",
        "Pruvio uses authentication, hashed OTP codes, WebAuthn/passkey public-key verification where enabled, access controls and encrypted "
        "HTTPS transport where deployed. Device biometric checks are performed locally by the device/platform; Pruvio receives only the resulting "
        "cryptographic WebAuthn response and related public credential metadata. No system is completely secure. Users should keep devices and "
        "verification codes secure and report suspected unauthorized access.",
    ),
    (
        "9. Your rights",
        "Depending on applicable law, including the GDPR where relevant, you may have rights of access, rectification, erasure, restriction, objection, "
        "data portability, withdrawal of consent and complaint to a supervisory authority. The production service should provide a verified process for "
        "handling these requests.",
    ),
    (
        "10. Cookies and local storage",
        "The current app uses essential browser/session storage to keep users authenticated and maintain application state. Non-essential analytics, "
        "advertising or tracking technologies should not be enabled without the required notice and consent controls.",
    ),
    (
        "11. Children",
        "Pruvio is not intentionally designed for young children. The final minimum age and parental-consent rules must be aligned with the countries "
        "where the service launches.",
    ),
    (
        "12. Changes and contact",
        f"Material privacy changes should be communicated to users and, where required, consent should be refreshed. Privacy questions can be sent to {LEGAL_CONTACT_EMAIL}.",
    ),
]
