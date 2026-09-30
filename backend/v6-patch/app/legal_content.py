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
        "does not hold or transfer money on behalf of users. Owners may choose to share their own bank-transfer or Revolut payment details with participants; any payment is made directly between users.",
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
        "messages, payment details that an owner chooses to save for sharing (for example beneficiary name, IBAN, bank/BIC, payment note or Revolut link), technical logs, security events, passkey public credential data and limited device/browser information. Pruvio does "
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

TERMS_TITLE_RO = "Termeni de utilizare Pruvio — Draft"
PRIVACY_TITLE_RO = "Notă de confidențialitate Pruvio — Draft"

TERMS_SECTIONS_RO = [
    ("1. Despre Pruvio", f"Acești Termeni reglementează utilizarea Pruvio, operat în prezent de {LEGAL_ENTITY_NAME}. Pruvio ajută utilizatorii să încarce bonuri, să extragă date prin OCR, să traducă denumiri de produse, să păstreze informații despre bonuri și să calculeze cheltuieli comune. Documentul este un draft de etapă de produs și trebuie revizuit juridic înainte de lansarea comercială."),
    ("2. Eligibilitate și cont", "Trebuie să furnizezi informații corecte la înregistrare și să păstrezi accesul la emailul și numărul de telefon verificate. Ești responsabil pentru activitatea realizată prin sesiunea ta autentificată. Pruvio poate restricționa sau suspenda conturile utilizate fraudulos, ilegal sau într-un mod care afectează serviciul ori alți utilizatori."),
    ("3. Verificare și securitate", "Pruvio poate solicita coduri unice prin email și SMS și poate suporta passkey-uri prin WebAuthn. Passkey-urile pot folosi amprenta, recunoașterea facială, PIN-ul dispozitivului, Windows Hello sau o cheie de securitate. Datele biometrice rămân pe dispozitiv și nu sunt transmise către Pruvio. Codurile de verificare sunt temporare și nu trebuie divulgate."),
    ("4. Procesarea bonurilor", "OCR-ul, detectarea limbii, traducerea și extragerea produselor sunt automate și pot conține erori. Trebuie să verifici cantitățile, prețurile, moneda, totalurile și traducerile înainte de utilizare. Bonul original sau documentul comerciantului rămâne sursa de referință."),
    ("5. Calculul notelor împărțite", "Pruvio oferă doar instrumente de calcul și coordonare. Nu garantează plata participanților, nu soluționează dispute și, dacă nu este oferit separat un serviciu de plată reglementat, nu deține și nu transferă bani în numele utilizatorilor. Proprietarul notei poate alege să distribuie participanților propriile date pentru transfer bancar sau linkul Revolut; plata se face direct între utilizatori."),
    ("6. Conținutul utilizatorului", "Păstrezi drepturile asupra bonurilor și conținutului încărcat. Acordi Pruvio dreptul limitat de a procesa, stoca, transforma și transmite acel conținut numai cât este necesar pentru furnizarea, securizarea și îmbunătățirea serviciului. Trebuie să ai dreptul de a încărca materialele transmise."),
    ("7. Utilizare interzisă", "Nu trebuie să folosești Pruvio pentru fraudă, uzurparea identității, conținut ilegal, acces neautorizat, perturbarea serviciului, ocolirea controalelor de securitate, abuzarea livrării OTP sau procesarea datelor personale fără un temei legal."),
    ("8. Servicii terțe", "Pruvio poate utiliza furnizori de găzduire, OCR, traducere, email și SMS. Disponibilitatea acestora poate afecta serviciul. Unde este necesar, furnizorii sunt utilizați în baza termenilor și acordurilor aplicabile."),
    ("9. Costuri", "Versiunea curentă de test poate fi oferită gratuit. Pruvio poate introduce ulterior planuri plătite sau limite de utilizare. Orice funcție plătită va afișa prețul și condițiile importante înainte de cumpărare."),
    ("10. Disponibilitate și modificări", "Serviciul este într-o etapă de dezvoltare și poate fi modificat, întrerupt sau poate conține defecte. Funcțiile, limitele și integrările se pot schimba pe măsură ce produsul evoluează. Modificările importante ale Termenilor vor fi prezentate pentru acceptare atunci când legea o cere."),
    ("11. Proprietate intelectuală", "Numele Pruvio, software-ul, designul vizual și materialele serviciului sunt protejate de legislația aplicabilă privind proprietatea intelectuală. Acești Termeni nu transferă utilizatorilor dreptul de proprietate asupra tehnologiei Pruvio."),
    ("12. Limitări și avertismente", "Pruvio nu oferă consultanță contabilă, fiscală, juridică sau financiară. OCR-ul și traducerea automată pot fi inexacte. Rămâi responsabil pentru verificarea documentelor sursă și pentru respectarea obligațiilor aplicabile."),
    ("13. Răspundere", "În limita permisă de lege, Pruvio nu răspunde pentru pierderi indirecte sau consecvențiale cauzate de extrageri ori traduceri inexacte, alegerile participanților, indisponibilitatea serviciilor terțe sau pierderea accesului. Drepturile obligatorii ale consumatorilor nu sunt excluse."),
    ("14. Încetare și ștergere", "Poți înceta utilizarea Pruvio oricând și poți solicita ștergerea contului. Pruvio poate suspenda sau opri accesul pentru încălcări grave/repetate, amenințări de securitate sau cerințe legale. Unele evidențe pot fi păstrate dacă legea sau necesități de securitate, prevenire a fraudei ori soluționare a disputelor o impun."),
    ("15. Lege aplicabilă și consumatori", "Clauza finală privind legea aplicabilă și jurisdicția trebuie completată înainte de lansare. Protecțiile obligatorii ale consumatorilor și drepturile acordate de legea țării utilizatorului nu sunt înlăturate de acest draft."),
    ("16. Contact", f"Întrebările despre acești Termeni pot fi trimise la {LEGAL_CONTACT_EMAIL}. Adresa operatorului: {LEGAL_ADDRESS}."),
]

PRIVACY_SECTIONS_RO = [
    ("1. Operator", f"Operatorul avut în vedere pentru datele utilizatorilor Pruvio este {LEGAL_ENTITY_NAME}, {LEGAL_ADDRESS}. Contact pentru confidențialitate: {LEGAL_CONTACT_EMAIL}. Datele operatorului sunt provizorii până la stabilirea entității juridice finale."),
    ("2. Date prelucrate", "În funcție de funcțiile utilizate, Pruvio poate prelucra numele, emailul, telefonul, starea verificării, preferințele contului, imagini/PDF-uri cu bonuri, date despre comercianți și produse, selecții pentru split bill, informații despre sesiuni, mesaje de suport, date de plată pe care proprietarul alege să le salveze pentru distribuire (de exemplu nume beneficiar, IBAN, bancă/BIC, referință sau link Revolut), loguri tehnice, evenimente de securitate, date publice ale passkey-urilor și informații limitate despre dispozitiv/browser. Pruvio nu primește și nu stochează amprenta sau șablonul facial folosit de dispozitiv pentru passkey."),
    ("3. Scopurile prelucrării", "Prelucrăm datele de cont și bonuri pentru furnizarea serviciului, autentificare, procesarea bonurilor, calculul cheltuielilor comune, istoricul utilizatorului, suport și prevenirea abuzurilor. Pentru securitate și integritatea serviciului poate fi utilizat interesul legitim. Marketingul opțional trebuie utilizat numai în baza unui temei legal corespunzător."),
    ("4. OCR, traducere și automatizare", "Imaginile bonurilor și textul extras pot fi transmise furnizorilor configurați de OCR și traducere. Sistemele automate identifică câmpuri, limbi și traduceri. Rezultatele pot fi inexacte și sunt prezentate pentru verificare de către utilizator, nu ca decizii exclusiv automate cu efecte juridice sau similare semnificative."),
    ("5. Furnizori de servicii", "Pruvio poate utiliza furnizori de cloud, baze de date, OCR, traducere, email, SMS, monitorizare și suport. Înainte de lansarea în producție, nota finală trebuie să identifice categoriile relevante și, unde este potrivit, furnizorii importanți și garanțiile pentru transferuri internaționale."),
    ("6. Transferuri internaționale", "Dacă datele sunt prelucrate în afara țării tale sau a SEE, Pruvio va utiliza un mecanism legal adecvat acolo unde este necesar, precum o decizie de adecvare, Clauze Contractuale Standard sau altă garanție permisă."),
    ("7. Păstrarea datelor", "Prototipul nu definește încă perioadele finale de retenție. Înainte de lansare trebuie stabilite perioade documentate pentru datele contului, fișierele de bonuri, datele extrase, înregistrările OTP, logurile de securitate și suport. Utilizatorii trebuie să poată șterge bonuri și solicita ștergerea contului, sub rezerva păstrării impuse de lege."),
    ("8. Securitate", "Pruvio utilizează autentificare, coduri OTP stocate sub formă hash, verificare cu cheie publică WebAuthn/passkey unde este activată, controale de acces și HTTPS. Verificarea biometrică are loc local pe dispozitiv; Pruvio primește doar răspunsul criptografic WebAuthn și metadatele publice aferente. Niciun sistem nu este complet sigur."),
    ("9. Drepturile tale", "În funcție de legea aplicabilă, inclusiv GDPR unde este relevant, poți avea drepturi de acces, rectificare, ștergere, restricționare, opoziție, portabilitate, retragerea consimțământului și plângere la o autoritate de supraveghere. Serviciul de producție trebuie să ofere un proces verificat pentru aceste solicitări."),
    ("10. Cookie-uri și stocare locală", "Aplicația curentă utilizează stocare esențială în browser/sesiune pentru autentificare și menținerea stării aplicației. Tehnologiile neesențiale de analiză, publicitate sau tracking nu trebuie activate fără informarea și consimțământul necesar."),
    ("11. Copii", "Pruvio nu este proiectat intenționat pentru copii mici. Vârsta minimă finală și regulile de consimțământ parental trebuie aliniate cu țările în care serviciul va fi lansat."),
    ("12. Modificări și contact", f"Modificările importante privind confidențialitatea trebuie comunicate utilizatorilor și, când este necesar, consimțământul trebuie reînnoit. Întrebările pot fi trimise la {LEGAL_CONTACT_EMAIL}."),
]
