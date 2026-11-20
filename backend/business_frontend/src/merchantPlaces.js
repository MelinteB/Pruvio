import {useEffect,useRef,useState} from 'react';

const API=(import.meta.env.VITE_API_BASE||'').replace(/\/$/,'');
export async function merchantPlacesRequest(path,token,{method='GET',body,signal}={}){
  const response=await fetch(API+path,{method,signal,headers:{
    Authorization:'Bearer '+token,
    ...(body?{'Content-Type':'application/json'}:{})
  },...(body?{body:JSON.stringify(body)}:{})});
  const data=await response.json().catch(()=>({}));
  if(response.status===401)window.dispatchEvent(new Event('pruvs-business-auth-expired'));
  if(!response.ok)throw new Error(typeof data.detail==='string'?data.detail:'Google Places could not be reached.');
  return data;
}

export function useMerchantPlaces(token,language,enabled=true){
  const [readiness,setReadiness]=useState(null);
  const [readinessAttempt,setReadinessAttempt]=useState(0);
  const [query,setQuery]=useState('');
  const [places,setPlaces]=useState([]);
  const [status,setStatus]=useState('idle');
  const [searchError,setSearchError]=useState('');
  const activeSearch=useRef(null);

  useEffect(()=>{
    if(!enabled)return;
    const controller=new AbortController();
    setReadiness(null);
    merchantPlacesRequest('/v1/merchant/places/readiness',token,{signal:controller.signal})
      .then(data=>{
        if(controller.signal.aborted)return;
        if(typeof data.places_search_enabled!=='boolean'||typeof data.place_links_migrated!=='boolean'){
          setReadiness({unreachable:true});
          return;
        }
        setReadiness(data);
      })
      .catch(()=>{if(!controller.signal.aborted)setReadiness({unreachable:true})});
    return()=>controller.abort();
  },[enabled,token,readinessAttempt]);

  useEffect(()=>{
    setPlaces([]);
    setStatus('idle');
    setSearchError('');
    return()=>activeSearch.current?.abort();
  },[language,token,enabled,readinessAttempt]);
  const unavailable=readiness?.places_search_enabled===false
    ?'Google Maps search is unavailable here.'
    :readiness?.place_links_migrated===false
      ?'Google Maps linking is unavailable here.'
      :'';
  const canLink=readiness?.places_search_enabled===true&&readiness?.place_links_migrated===true;

  function changeQuery(value){
    activeSearch.current?.abort();
    setQuery(value);
    setPlaces([]);
    setStatus('idle');
    setSearchError('');
  }

  async function search(){
    if(!enabled||!canLink||query.trim().length<3||status==='searching')return;
    activeSearch.current?.abort();
    const controller=new AbortController();
    activeSearch.current=controller;
    setPlaces([]);
    setStatus('searching');
    setSearchError('');
    try{
      const params=new URLSearchParams({q:query.trim(),language});
      const data=await merchantPlacesRequest('/v1/merchant/places/search?'+params,token,{signal:controller.signal});
      if(controller.signal.aborted)return;
      setPlaces(data.places||[]);
      setStatus(data.places?.length?'results':'empty');
    }catch(error){
      if(!controller.signal.aborted){setSearchError(error.message);setStatus('error');}
    }
  }

  return {query,changeQuery,places,status,search,searchError,unavailable,canLink,readiness,
    retryReadiness:()=>setReadinessAttempt(current=>current+1)};
}
