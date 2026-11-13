import { describe, it, expect } from 'vitest';
import { suggestCover, coverKey, coverChoices, coverImage } from './project-covers';
describe('Project name-based cover suggestions (v7.1.44)',()=>{
  it.each([
    ['Ski Trip 2027','mountain'],['Vacanță în Grecia','beach'],['Nuntă cu familia','wedding'],
    ['Petrecere cu prietenii','party'],['Home Renovation','home'],['Office team','work'],
    ['Birthday party','birthday'],['Weekend Brasov','mountain'],['Dinner with friends','party'],
    ['Camping by the lake','camping'],['Unknown project','default'],
  ])('recognizes %s', (name,expected)=>expect(suggestCover(name)).toBe(expected));
  it('persists explicit preference over name suggestion',()=>expect(coverKey('Ski Trip','beach')).toBe('beach'));
  it('does not fetch remote assets',()=>expect(coverChoices.every(([key])=>!/^https?:\/\//.test(coverImage('test',key)))).toBe(true));
});
