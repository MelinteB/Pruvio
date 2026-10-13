import React from 'react';
import {afterEach,describe,expect,it,vi} from 'vitest';
import {cleanup,fireEvent,render,screen} from '@testing-library/react';
import {MemoryRouter} from 'react-router-dom';
import {Context} from './common';
import {CompanySettings} from './Account';
import {ExpenseNew} from './Expenses';
import {request,send} from './api';

vi.mock('./api',()=>({request:vi.fn(),send:vi.fn(),money:(amount,currency)=>`${amount} ${currency}`,headers:vi.fn()}));
const companies=[{id:1,name:'Acme Ltd',tax_id:'123'}];
function mockSources(){
  request.mockImplementation(path=>Promise.resolve(path==='/expenses/companies'?companies:path==='/expenses/trip-profiles'?[]:path.startsWith('/expenses/sources/tree?')?{rows:[],has_more:false}:[]));
  send.mockResolvedValue({id:1});
}
afterEach(()=>{cleanup();vi.resetAllMocks()});

describe('company trip profile window',()=>{
  it('opens from Account as a modal, closes on Escape and restores focus',async()=>{
    mockSources();
    render(<MemoryRouter><CompanySettings/></MemoryRouter>);
    const open=screen.getByRole('button',{name:'Open trip profiles'});
    expect(screen.queryByRole('dialog',{name:'Company trip profiles'})).toBeNull();
    fireEvent.click(open);
    const dialog=screen.getByRole('dialog',{name:'Company trip profiles'});
    expect(dialog.contains(screen.getByRole('button',{name:'Add trip profile'}))).toBe(true);
    expect(document.body.style.overflow).toBe('hidden');
    expect(document.activeElement).toBe(screen.getByRole('button',{name:'Close trip profiles'}));
    fireEvent.keyDown(document,{key:'Escape'});
    expect(screen.queryByRole('dialog',{name:'Company trip profiles'})).toBeNull();
    expect(document.body.style.overflow).toBe('');
    expect(document.activeElement).toBe(open);
  });

  it('opens from expense preparation without inserting the editor into the page',async()=>{
    mockSources();
    render(<MemoryRouter><Context.Provider value={{config:{currencies:{RON:'Leu'}}}}><ExpenseNew/></Context.Provider></MemoryRouter>);
    await screen.findByRole('option',{name:/Acme Ltd/});
    fireEvent.change(screen.getByLabelText('Company profile'),{target:{value:'1'}});
    const open=screen.getByRole('button',{name:'Create or edit trip profile here'});
    fireEvent.click(open);
    const dialog=screen.getByRole('dialog',{name:'Company trip profiles'});
    expect(dialog.querySelector('.trip-profiles-panel')).not.toBeNull();
    expect(screen.getByRole('button',{name:'Create or edit trip profile here'})).toBe(open);
    fireEvent.click(screen.getByRole('button',{name:'Close trip profiles'}));
    expect(screen.queryByRole('dialog',{name:'Company trip profiles'})).toBeNull();
  });
});
