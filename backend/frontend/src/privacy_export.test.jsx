import React from 'react';
import { afterEach, describe, expect, it, vi } from 'vitest';
import { render, screen, fireEvent, cleanup, waitFor } from '@testing-library/react';
import { MemoryRouter } from 'react-router-dom';
import { vi as mock } from 'vitest';

vi.mock('./common', async () => {
 const m = await vi.importActual('./common');
 return {...m, useApp:()=>({user:{id:11,name:'Test',username:'test',email:'test@example.com'},
     refresh:vi.fn(),logout:vi.fn(),accept:vi.fn(),config:{}}),
   useLoad:()=>({data:[],reload:vi.fn(),error:null})};
});
vi.mock('./api', async () => ({
  request:vi.fn(async()=>[]),send:vi.fn(async(path)=>path==='/account/data-export'?{format:'pruvs-account-activity-v1'}:{}),credential:vi.fn()
}));
vi.mock('./Membership',()=>({default:()=>null}));
vi.mock('./Notifications',()=>({default:()=>null}));
vi.mock('./CompanyProfiles',()=>({default:()=>null}));
vi.mock('./TripProfiles',()=>({TripProfilesDialog:()=>null}));
vi.mock('./PaymentProfiles',()=>({default:()=>null}));
vi.mock('./professional/SupportDiagnostics',()=>({default:()=>null}));
vi.mock('./professional/CorePages',()=>({ProfileHeader:()=>null}));

import Account from './Account';
import { send } from './api';

afterEach(()=>{cleanup();vi.restoreAllMocks()});

describe('Privacy activity download',()=>{
 it('is on demand, scoped to Account, and uses the authenticated API',async()=>{
   const create = vi.fn(()=> 'blob:pruvs-test');
   const revoke = vi.fn();
   Object.defineProperty(URL,'createObjectURL',{configurable:true,value:create});
   Object.defineProperty(URL,'revokeObjectURL',{configurable:true,value:revoke});
   const click = vi.spyOn(HTMLAnchorElement.prototype,'click').mockImplementation(()=>{});
   render(<MemoryRouter><Account/></MemoryRouter>);
   fireEvent.click(screen.getByRole('button',{name:/privacy & account deletion/i}));
   fireEvent.click(screen.getByRole('button',{name:/download my activity/i}));
   await waitFor(()=>expect(send).toHaveBeenCalledWith('/account/data-export'));
   expect(create).toHaveBeenCalledTimes(1);
   expect(click).toHaveBeenCalled();
 });
});
