/** Packaged, deterministic covers. No external image requests or paid generation. */
import mountain from './project-covers/mountain.svg';
import beach from './project-covers/beach.svg';
import city from './project-covers/city.svg';
import camping from './project-covers/camping.svg';
import family from './project-covers/family.svg';
import party from './project-covers/party.svg';
import home from './project-covers/home.svg';
import roadtrip from './project-covers/roadtrip.svg';
import food from './project-covers/food.svg';
import work from './project-covers/work.svg';
import sports from './project-covers/sports.svg';
import birthday from './project-covers/birthday.svg';
import wedding from './project-covers/wedding.svg';
import nature from './project-covers/nature.svg';
import fallback from './project-covers/default.svg';

const covers = {mountain,beach,city,camping,family,party,home,roadtrip,food,work,sports,birthday,wedding,nature,default:fallback};
export const coverChoices = [
  ['mountain','Ski & mountains'],['beach','Beach & holidays'],['city','City break'],
  ['camping','Camping'],['family','Family'],['party','Party & friends'],
  ['home','Home'],['roadtrip','Road trip'],['food','Food & dining'],
  ['work','Work'],['sports','Sports'],['birthday','Birthday'],
  ['wedding','Wedding'],['nature','Nature'],['default','Other']
];
const priorities = [
  ['birthday',/(birthday|aniversar|ziua mea|zi de nastere|majorat|anniversary)/],
  ['wedding',/(wedding|nunta|casatorie|cununi|marriage)/],
  ['mountain',/(ski|snow|munte|montan|cabana|alpin|mountain|winter|zapada|meribel|poiana|brasov)/],
  ['beach',/(beach|mare|plaja|beach|vacant|holiday|holidays|summer|seaside|island|grecia|greece|sea|skiathos)/],
  ['camping',/(camp|cort|drumetie|hiking|outdoor|bonfire)/],
  ['roadtrip',/(road.?trip|drive|masina|auto|travel|journey|excursie|trip cu masina)/],
  ['family',/(family|famil|copii|kids|parents|parinti|rude)/],
  ['party',/(party|petrecere|club|festival|friends|prieteni|nightlife)/],
  ['home',/(home|casa|apartament|renov|mutare|chirie|household)/],
  ['food',/(food|mancare|restaurant|dinner|lunch|brunch|meal|cina|gratar|groceries|cumparaturi)/],
  ['work',/(work|business|office|team|colegi|job|conferinta|training)/],
  ['sports',/(sport|football|fotbal|tenis|gym|fitness|cycling|bike|run)/],
  ['nature',/(nature|natura|forest|padure|lake|lac|park|picnic)/],
  ['city',/(city|urban|oras|bucuresti|bucharest|london|paris|rome|vienna|weekend|week.?end)/]
];
export function suggestCover(name='') {
  const normalized = String(name).normalize('NFD').replace(/[\u0300-\u036f]/g,'').toLowerCase();
  for (const [key,pattern] of priorities) if(pattern.test(normalized)) return key;
  return 'default';
}
export function coverKey(name='', override=null){return Object.hasOwn(covers,override)?override:suggestCover(name);}
export function coverImage(name='',override=null){return covers[coverKey(name,override)];}
export function coverAlt(name='',override=null){return `${coverChoices.find(([key])=>key===coverKey(name,override))?.[1]||'Project'} illustration`;}
