import React,{createContext,useContext,useEffect,useState} from 'react';

const STORAGE='pruvs-business-locale';
const rom = {
  'Overview':'Prezentare generală','Locations':'Locații','Loyalty programs':'Programe de fidelitate',
  'Verify purchases':'Verificare cumpărături','AI campaign studio':'Studio campanii AI',
  'Checkout & integrations':'Plăți și integrări','Campaign Library':'Bibliotecă de campanii',
  'Purchase codes':'Coduri de cumpărare','Customer demo':'Demo client',
  'Workspace':'Spațiu de lucru','Merchant workspace':'Spațiul comerciantului',
  'Sign out':'Deconectare','Pilot environment':'Mediu pilot',
  'Welcome back':'Bine ai revenit','Email address':'Adresă de e-mail','Password':'Parolă',
  'Sign in':'Autentificare','Signing in…':'Se autentifică…','Check API connection':'Verifică API-ul',
  'Secure merchant access · Campaigns require approval':'Acces securizat · Campaniile necesită aprobare',
  'Your loyalty business at a glance.':'Activitatea de fidelizare, pe scurt.',
  'Manage your merchant loyalty experience.':'Gestionează programele de fidelitate.',
  'Connect loyalty activity to your merchant checkout infrastructure.':'Conectează fidelizarea la sistemele de încasare.',
  'Campaigns':'Campanii','New campaign':'Campanie nouă',
  'Create a campaign':'Creează o campanie','Campaign Studio':'Studio de campanii',
  'Use your photo, refine the message and preview the offer before publishing.':
    'Adaugă fotografia, ajustează mesajul și previzualizează oferta înainte de publicare.',
  'Approval required before publishing':'Este necesară aprobarea înainte de publicare',
  'Photo':'Fotografie','Direction':'Direcție','Copy':'Text','Creative':'Material creativ',
  'Optional':'Opțional','Editable brief':'Descriere editabilă','Review required':'Necesită verificare',
  'Draft then publish':'Schiță, apoi publicare',
  'Published loyalty program':'Program de fidelitate publicat',
  'Campaign goal':'Obiectivul campaniei','Target audience':'Public-țintă',
  'Brand tone':'Tonul brandului','Creative format':'Formatul materialului',
  'Main campaign picture and subject':'Imaginea principală a campaniei',
  'Upload main campaign picture':'Încarcă fotografia principală',
  'Replace main picture':'Înlocuiește fotografia','Predefined campaign text':'Textul predefinit',
  'Your campaign instructions':'Instrucțiunile campaniei',
  'Restore predefined text':'Restabilește textul predefinit',
  'Promotion headline':'Titlul promoției','Promotional message':'Mesajul promoțional',
  'Display period (days)':'Durată de afișare (zile)',
  'Save promotion draft':'Salvează schița','Update promotion draft':'Actualizează schița',
  'Unpublished':'Nepublicate','Drafts':'Schițe','Paused':'Pauzate',
  'Live':'Active','Expired':'Expirate','Archived':'Arhivate',
  'All campaigns':'Toate campaniile','Draft':'Schiță','Paused':'Pauzată',
  'Expired':'Expirată','Archived':'Arhivată','Preview':'Previzualizare',
  'Edit':'Editează','Publish':'Publică','Unpublish':'Retrage',
  'Pause':'Pauzează','Resume':'Reia','Draft':'Schiță',
  'Republish now':'Republică acum','Duplicate':'Duplică','Archive':'Arhivează',
  'Restore draft':'Restaurează schița','Edit draft':'Editează schița',
  'New from this':'Campanie nouă din aceasta',
  'Search campaigns':'Caută campanii','Campaign management':'Administrarea campaniilor',
  'Your campaign library':'Biblioteca de campanii',
  'No unpublished campaigns':'Nu există campanii nepublicate',
  'Locations':'Locații','Add location':'Adaugă locație','Edit location':'Editează locația',
  'Store locations':'Locații comerciale','Find your business on Google Maps':'Caută afacerea pe Google Maps',
  'Location name':'Numele locației','Address':'Adresă','Latitude':'Latitudine',
  'Longitude':'Longitudine','Create location':'Creează locația','Save changes':'Salvează',
  'Cancel':'Anulează','Search':'Caută','Google rating & reviews':'Evaluări și recenzii Google',
  'View on Maps':'Vezi pe hartă','Directions':'Indicații de orientare',
  'Deactivate':'Dezactivează','Activate':'Activează','Active':'Activă','Inactive':'Inactivă',
  'My wallet':'Portofelul meu','Reviews':'Recenzii',
  'Manage loyalty programs':'Gestionează programele de fidelizare',
  'Refresh':'Reîmprospătează','Close':'Închide',
};
const Context=createContext({language:'en',setLanguage:()=>{},t:key=>key});
export function BusinessLocaleProvider({children}){
  const [language,setLanguage]=useState(()=>{
    try{return window.localStorage.getItem(STORAGE)==='ro'?'ro':'en'}
    catch{return 'en'}
  });
  useEffect(()=>{
    try{window.localStorage.setItem(STORAGE,language)}catch{}
    document.documentElement.lang=language;
  },[language]);
  const t=(key)=>language==='ro'?(rom[key]||key):key;
  return <Context.Provider value={{language,setLanguage,t}}>{children}</Context.Provider>;
}
export function useBusinessLocale(){return useContext(Context)}
export function LanguageSwitch(){
  const {language,setLanguage}=useBusinessLocale();
  return <div className="pruvs-business-language" role="group" aria-label="Platform language">
    <button type="button" aria-pressed={language==='en'} className={language==='en'?'selected':''}
      onClick={()=>setLanguage('en')}>EN</button>
    <button type="button" aria-pressed={language==='ro'} className={language==='ro'?'selected':''}
      onClick={()=>setLanguage('ro')}>RO</button>
  </div>;
}
