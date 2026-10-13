const INTRO_SESSION_KEY='spare-brand-opening-v1';

export function shouldShowIntro({pathname='/',storage,reducedMotion=false}={}){
 if(pathname!=='/'||reducedMotion)return false;
 try{return storage?.getItem(INTRO_SESSION_KEY)!=='seen'}catch{return true}
}

export function rememberIntro(storage){
 try{storage?.setItem(INTRO_SESSION_KEY,'seen')}catch{/* Restricted storage never blocks access. */}
}
