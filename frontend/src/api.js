export const API_BASE=import.meta.env.DEV?'/api':'';
export async function api(path,options={}) {
  const response=await fetch(API_BASE+path,{...options,headers:{'Content-Type':'application/json',...options.headers}});
  let data; try { data=await response.json(); } catch { throw new Error('The server returned an unreadable response. Check that the backend is running.'); }
  if (!response.ok) {
    const detail=data.detail; throw new Error(Array.isArray(detail)?detail.map(d=>d.msg).join(' '):(detail||'Request failed.'));
  }
  return data;
}
export const post=(path,data)=>api(path,{method:'POST',body:JSON.stringify(data)});
export const money=cents=>cents==null?'Unavailable':new Intl.NumberFormat('en-US',{style:'currency',currency:'USD'}).format(cents/100);
export const closeDate=value=>value?new Date(value).toLocaleString(undefined,{month:'short',day:'numeric',hour:'numeric',minute:'2-digit'}):'Not published';
