import React,{createContext,useContext,useEffect,useState} from 'react';

// UI language is a presentation setting, not a source of merchant reward terms.
// Add translations by key; never translate customer-entered content or financial rules.
const RO={
  'Overview':'Prezentare generală',
  'Locations':'Locații',
  'Loyalty programs':'Programe de fidelitate',
  'Verify purchases':'Verificare cumpărături',
  'AI campaign studio':'Studio campanii AI',
  'Checkout & integrations':'Casă și integrări',
  'Campaign Library':'Bibliotecă de campanii',
  'Purchase codes':'Coduri de cumpărare',
  'Customer demo':'Demonstrație client',
  'Sign in':'Autentificare',
  'Sign out':'Deconectare',
  'Welcome back':'Bine ai revenit',
  'Email address':'Adresă de e-mail',
  'Password':'Parolă',
  'Signing in…':'Autentificare…',
  'Check API connection':'Verifică conexiunea API',
  'Merchant workspace':'Spațiul comerciantului',
  'Your loyalty business at a glance.':'Activitatea programelor de fidelitate, pe scurt.',
  'Manage your merchant loyalty experience.':'Administrează programele și campaniile comerciantului.',
  'Add location':'Adaugă locație',
  'New program':'Program nou',
  'Store locations':'Locații comerciale',
  'No locations yet':'Nu există locații',
  'Manage loyalty programs':'Gestionează programele de fidelitate',
  'Create loyalty program':'Creează program de fidelitate',
  'Save as draft':'Salvează ca ciornă',
  'Save location':'Salvează locația',
  'Create a campaign':'Creează o campanie',
  'Use your photo, refine the message and preview the offer before publishing.':
    'Folosește fotografia, ajustează mesajul și verifică oferta înainte de publicare.',
  'Approval required before publishing':'Este necesară aprobarea înainte de publicare',
  'Campaign Studio':'Studio de campanii',
  'Photo':'Fotografie',
  'Direction':'Direcție',
  'Copy':'Text',
  'Creative':'Material vizual',
  'Published loyalty program':'Program de fidelitate publicat',
  'Campaign goal':'Obiectivul campaniei',
  'Target audience':'Public-țintă',
  'Brand tone':'Tonul brandului',
  'Creative format':'Formatul vizual',
  'Watermark text':'Text filigran',
  'Friendly':'Prietenos',
  'Premium':'Premium',
  'Playful':'Jucăuș',
  'Professional':'Profesional',
  'Branded image':'Imagine personalizată',
  'Animated GIF (3 seconds)':'GIF animat (3 secunde)',
  'Short video MP4 (3 seconds)':'Video MP4 scurt (3 secunde)',
  'Main campaign picture and subject':'Fotografia și subiectul campaniei',
  'Upload main campaign picture':'Încarcă fotografia principală',
  'Replace main picture':'Înlocuiește fotografia principală',
  'Predefined campaign text · edit before generating':'Text predefinit · editează înainte de generare',
  'Restore predefined text':'Restabilește textul predefinit',
  'Your campaign instructions':'Instrucțiunile campaniei',
  'Review copy':'Verifică textul',
  'Save promotion draft':'Salvează ciorna campaniei',
  'Update promotion draft':'Actualizează ciorna',
  'Display period (days)':'Durata afișării (zile)',
  'View customer preview':'Vezi previzualizarea clientului',
  'My campaigns':'Campaniile mele',
  'Unpublished':'Nepublicate',
  'Drafts':'Ciorne',
  'Paused':'Suspendate',
  'Live':'Active',
  'Expired':'Expirate',
  'Archived':'Arhivate',
  'All campaigns':'Toate campaniile',
  'Publish':'Publică',
  'Unpublish':'Retrage de la publicare',
  'Republish':'Republică',
  'Edit':'Editează',
  'Preview':'Previzualizează',
  'Archive':'Arhivează',
  'Duplicate':'Duplică',
  'Search campaigns':'Caută campanii',
  'Connect':'Conectează',
  'Disconnect':'Deconectează',
  'Google Maps':'Google Maps',
  'Location management':'Gestionare locații',
  'Search Google Maps':'Caută pe Google Maps',
  'Search':'Caută',
  'Directions':'Indicații de traseu',
  'Show reviews':'Afișează recenziile',
  'Save changes':'Salvează modificările',
  'Cancel':'Anulează',
  'Loading…':'Se încarcă…',
  'Retry':'Reîncearcă',
  'Refresh':'Actualizează',
  'Active':'Activ',
  'Pending':'În așteptare',
  'Redeemed':'Utilizat',
  'Welcome':'Bun venit',
  'Log in to manage your merchant loyalty programs.':
    'Autentifică-te pentru a gestiona programele de fidelitate.',
};

const Ctx=createContext({language:'en',setLanguage:()=>{},t:key=>key});
export function BusinessLanguageProvider({children}){
  const [language,setLanguage]=useState(()=>{
    try{return localStorage.getItem('pruvs-business-language')==='ro'?'ro':'en'}
    catch{return 'en'}
  });
  useEffect(()=>{
    try{localStorage.setItem('pruvs-business-language',language)}catch{}
    document.documentElement.lang=language;
  },[language]);
  const t=(key)=>language==='ro'?(RO[key]||key):key;
  return <Ctx.Provider value={{language,setLanguage,t}}>{children}</Ctx.Provider>;
}
export function useBusinessLanguage(){return useContext(Ctx);}
export function LanguageSwitcher(){
  const {language,setLanguage}=useBusinessLanguage();
  return <label className="pruvs-language-switch" title="Interface language / Limba interfeței">
    <span className="pruvs-language-label">Language / Limbă</span>
    <select aria-label="Interface language" value={language} onChange={e=>setLanguage(e.target.value)}>
      <option value="en">EN</option><option value="ro">RO</option>
    </select>
  </label>;
}
