import React,{lazy,Suspense,useCallback,useEffect,useRef,useState} from 'react';
import {Coins,ArrowRight} from 'lucide-react';
import {rememberIntro,shouldShowIntro} from './introPolicy';
import './brandIntro.css';

const PatternWaves=lazy(()=>import('./reactbits/PatternWaves'));
// A decorative chunk can fail offline without taking the dashboard down with it.
class DecorativeBoundary extends React.Component{
 state={failed:false};
 static getDerivedStateFromError(){return {failed:true}}
 render(){return this.state.failed?null:this.props.children}
}
function sessionStorage(){try{return window.sessionStorage}catch{return undefined}}

export function useBrandIntro(){
 const [visible,setVisible]=useState(()=>typeof window!=='undefined'&&shouldShowIntro({
  pathname:window.location.pathname,storage:sessionStorage(),
  reducedMotion:window.matchMedia?.('(prefers-reduced-motion: reduce)').matches??false
 }));
 const finish=useCallback(()=>{rememberIntro(sessionStorage());setVisible(false)},[]);
 return {visible,finish};
}

export default function BrandIntro({onComplete}){
 const skip=useRef(null);
 useEffect(()=>{
  const previousFocus=document.activeElement,previousOverflow=document.body.style.overflow;
  document.body.style.overflow='hidden';skip.current?.focus();
  function handleKey(event){
   if(event.key==='Escape'){event.preventDefault();onComplete()}
   if(event.key==='Tab'){event.preventDefault();skip.current?.focus()}
  }
  const preference=window.matchMedia?.('(prefers-reduced-motion: reduce)');
  const reduce=()=>{if(preference?.matches)onComplete()};
  document.addEventListener('keydown',handleKey);preference?.addEventListener('change',reduce);
  // Only a brand sequence: this timeout never represents a network call or agent state.
  const fallback=window.setTimeout(onComplete,3600);
  return()=>{
   window.clearTimeout(fallback);document.removeEventListener('keydown',handleKey);
   preference?.removeEventListener('change',reduce);document.body.style.overflow=previousOverflow;
   if(previousFocus!==document.body&&previousFocus?.isConnected)previousFocus.focus();
   else document.querySelector('.app-header .wordmark')?.focus();
  };
 },[onComplete]);
 return <section className="brand-intro" role="dialog" aria-modal="true" aria-labelledby="intro-brand" aria-describedby="intro-caption" onAnimationEnd={event=>{
  if(event.target===event.currentTarget&&event.animationName==='spare-opening')onComplete();
 }}>
  <div className="intro-wave intro-wave-left" aria-hidden="true"><DecorativeBoundary><Suspense fallback={null}><PatternWaves preset="silk" pattern="dot" color="#88f7d9" backgroundColor="transparent" spacing={9} depth={.8} opacity={.9} speed={.65} intro={false} interactive={false}/></Suspense></DecorativeBoundary></div>
  <div className="intro-wave intro-wave-right" aria-hidden="true"><DecorativeBoundary><Suspense fallback={null}><PatternWaves preset="lines" color="#8db8ff" backgroundColor="transparent" spacing={12} depth={.8} opacity={.75} speed={.5} intro={false} interactive={false}/></Suspense></DecorativeBoundary></div>
  <div className="intro-orbit" aria-hidden="true"/>
  <div className="intro-identity"><div className="intro-mark" aria-hidden="true"><Coins size={64} strokeWidth={1.35}/></div><h1 id="intro-brand">spare<span>.</span></h1><p id="intro-caption">Your change. Your choice.</p></div>
  <button ref={skip} className="intro-skip" type="button" onClick={onComplete}>Skip intro <ArrowRight size={16}/></button>
 </section>;
}
