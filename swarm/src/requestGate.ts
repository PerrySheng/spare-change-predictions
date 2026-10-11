/** Limit actual request starts. Waiting does not emit invented agent activity. */
export function requestGate(limit=4,windowMs=61000,now=Date.now,wait=(ms:number)=>new Promise<void>(r=>setTimeout(r,ms))){
  const starts:number[]=[];
  let queue=Promise.resolve();
  return ()=>{
    const next=queue.then(async()=>{
      while(starts.length>=limit){
        const delay=starts[0]+windowMs-now();
        if(delay>0) await wait(delay);
        while(starts.length && starts[0]+windowMs<=now()) starts.shift();
      }
      starts.push(now());
    });
    queue=next.catch(()=>{});
    return next;
  };
}
