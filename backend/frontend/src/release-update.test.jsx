import React from 'react';
import {beforeEach,afterEach,describe,it,expect,vi} from 'vitest';
import {cleanup,fireEvent,render,screen,waitFor} from '@testing-library/react';
import {CLIENT_RELEASE,isNewerRelease,shouldOfferUpdate,ReleaseUpdateBanner} from './professional/ReleaseUpdateBanner';

const dismissedKey='pruvs:release-update:dismissed-v1';
const reloadedKey='pruvs:release-update:reload-attempted-v1';
const [major,minor,patch]=CLIENT_RELEASE.split('.').map(Number);
const nextRelease=`${major}.${minor}.${patch+1}`;
const laterRelease=`${major}.${minor}.${patch+2}`;
function serve(version,status='ready'){
  globalThis.fetch=vi.fn(async()=>({ok:true,json:async()=>({version,status})}));
}
beforeEach(()=>{
  window.localStorage.clear();
  window.sessionStorage.clear();
  Object.defineProperty(document,'hidden',{configurable:true,value:false});
});
afterEach(()=>{cleanup();vi.restoreAllMocks();});

describe('Core release update banner',()=>{
  it('uses current compiled Core version, with semantic comparison',()=>{
    expect(CLIENT_RELEASE).toBe('7.1.65');
    expect(isNewerRelease(CLIENT_RELEASE)).toBe(false);
    expect(isNewerRelease('7.1.62')).toBe(false);
    expect(isNewerRelease('7.1.58')).toBe(false);
    expect(isNewerRelease(nextRelease)).toBe(true);
    expect(isNewerRelease('7.2.0')).toBe(true);
    expect(isNewerRelease('7.1.invalid')).toBe(false);
  });
  it('does not offer a reload after browser already matches the server release',async()=>{
    serve(CLIENT_RELEASE);
    render(<ReleaseUpdateBanner/>);
    await waitFor(()=>expect(fetch).toHaveBeenCalledTimes(1));
    expect(screen.queryByRole('button',{name:'Reload'})).toBeNull();
  });
  it('allows dismissing a specific update across component remounts',async()=>{
    serve(nextRelease);
    render(<ReleaseUpdateBanner/>);
    expect(await screen.findByText('A newer Pruvs version is ready.')).toBeTruthy();
    fireEvent.click(screen.getByRole('button',{name:'Dismiss update notice'}));
    expect(screen.queryByRole('button',{name:'Reload'})).toBeNull();
    expect(window.localStorage.getItem(dismissedKey)).toBe(nextRelease);
    cleanup();
    render(<ReleaseUpdateBanner/>);
    await waitFor(()=>expect(fetch).toHaveBeenCalledTimes(2));
    expect(screen.queryByRole('button',{name:'Reload'})).toBeNull();
    cleanup();
    // Dismissal of one release must not hide a newer update.
    serve(laterRelease);
    render(<ReleaseUpdateBanner/>);
    expect(await screen.findByText('A newer Pruvs version is ready.')).toBeTruthy();
  });
  it('does not repeat a reload prompt already attempted during this session',async()=>{
    window.sessionStorage.setItem(reloadedKey,nextRelease);
    serve(nextRelease);
    render(<ReleaseUpdateBanner/>);
    await waitFor(()=>expect(fetch).toHaveBeenCalledTimes(1));
    expect(screen.queryByRole('button',{name:'Reload'})).toBeNull();
    expect(shouldOfferUpdate({status:'ready',version:nextRelease},CLIENT_RELEASE,null,nextRelease)).toBe(false);
    expect(shouldOfferUpdate({status:'ready',version:laterRelease},CLIENT_RELEASE,null,nextRelease)).toBe(true);
  });
  it('does not show a banner when server is not ready or version is invalid',()=>{
    expect(shouldOfferUpdate({status:'unavailable',version:nextRelease})).toBe(false);
    expect(shouldOfferUpdate({status:'ready',version:'broken'})).toBe(false);
  });
});
