import React from 'react';
import {afterEach,beforeEach,describe,expect,it,vi} from 'vitest';
import {cleanup,fireEvent,render,screen,waitFor} from '@testing-library/react';
import CustomerReceiptCode from './CustomerReceiptCode';
import {send} from './api';
import {getLocalReceipt} from './localReceipts';
vi.mock('./api',()=>({send:vi.fn()}));
vi.mock('./localReceipts',()=>({getLocalReceipt:vi.fn()}));
const programs=[{merchant_name:'Bistro Central',store:{name:'Bistro Central'},
  program:{id:'12345678-1234-4234-9234-1234567890ab',title:'Breakfast · Bistro Central Rewards'}}];
beforeEach(()=>{
  send.mockResolvedValue({display_code:'PRV-AABB-CCDD-EEFF',expires_at:'2026-11-18T12:00:00Z',claim_id:'test-only'});
});
afterEach(()=>{cleanup();vi.resetAllMocks();});
function open(props={}){
  const r=render(<CustomerReceiptCode caseId={42} userId={6}
    storageMode="local" programs={programs} {...props}/>);
  fireEvent.click(screen.getByRole('button',{name:'Earn a stamp'}));
  return r;
}
describe('Verification dialog reuses the already scanned receipt',()=>{
  it('renders a readable consent and no upload field',()=>{
    open();
    expect(screen.getByRole('heading',{name:'Verify your purchase'})).toBeTruthy();
    expect(screen.getByText('Receipt photo ready')).toBeTruthy();
    expect(screen.getByRole('checkbox')).toBeTruthy();
    expect(screen.queryByLabelText(/Choose File/i)).toBeNull();
    expect(document.querySelector('.pruvs-v12-form input[type=file]')).toBeNull();
    expect(document.querySelector('.pruvs-v12-consent span strong')).toBeTruthy();
    expect(screen.getByRole('button',{name:'Create verification QR'}).disabled).toBe(true);
  });
  it('reads saved local image and passes it securely with consent',async()=>{
    const blob=new File([new Uint8Array([255,216,255,1,2,3,255,217])],'original.jpg',{type:'image/jpeg'});
    getLocalReceipt.mockResolvedValue({blob,filename:'original.jpg'});
    open();
    fireEvent.click(screen.getByRole('checkbox'));
    fireEvent.click(screen.getByRole('button',{name:'Create verification QR'}));
    await waitFor(()=>expect(send).toHaveBeenCalledTimes(1));
    expect(getLocalReceipt).toHaveBeenCalledWith(6,42);
    const [url,payload]=send.mock.calls[0];
    expect(url).toBe('/loyalty/receipts/42/customer-code-v12');
    expect(payload.share_consent).toBe(true);
    expect(payload.program_id).toBe(programs[0].program.id);
    expect(typeof payload.photo_base64).toBe('string');
    expect(payload.photo_base64.length).toBeGreaterThan(0);
    expect(await screen.findByText(/QR ready for merchant review/)).toBeTruthy();
  });
  it('cloud fallback does not ask for a second receipt',async()=>{
    getLocalReceipt.mockResolvedValue(undefined);
    open({storageMode:'cloud'});
    fireEvent.click(screen.getByRole('checkbox'));
    fireEvent.click(screen.getByRole('button',{name:'Create verification QR'}));
    await waitFor(()=>expect(send).toHaveBeenCalledTimes(1));
    expect(send.mock.calls[0][1].photo_base64).toBeNull();
  });
  it('fails closed when a free-plan scan is missing from the device',async()=>{
    getLocalReceipt.mockResolvedValue(undefined);
    open();
    fireEvent.click(screen.getByRole('checkbox'));
    fireEvent.click(screen.getByRole('button',{name:'Create verification QR'}));
    expect(await screen.findByRole('alert')).toBeTruthy();
    expect(screen.getByText(/scanned receipt photo is missing from this device/i)).toBeTruthy();
    expect(send).not.toHaveBeenCalled();
  });
});
