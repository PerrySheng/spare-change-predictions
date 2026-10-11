import React from 'react';
import './swarmMascot.css';

export default function SwarmMascot({size=28,working=false}){
 return <svg className={'swarm-bee'+(working?' working':'')} width={size} height={size} viewBox="0 0 64 64" role="img" aria-label="Swarm, your research bee">
  <g className="swarm-bee-wings" fill="#eaf5ff" stroke="#9ab7d6" strokeWidth="1.5"><ellipse cx="25" cy="20" rx="9" ry="13" transform="rotate(-35 25 20)"/><ellipse cx="39" cy="20" rx="9" ry="13" transform="rotate(35 39 20)"/></g>
  <path d="M22 43 17 48M31 46 31 52M40 43 46 48" stroke="#463d35" strokeWidth="2.5" strokeLinecap="round"/>
  <ellipse cx="32" cy="34" rx="21" ry="16" fill="#ffd75a" stroke="#463d35" strokeWidth="1.8"/>
  <path d="M25 19c-4 8-4 20 0 30M36 18c-4 8-4 22 0 32" fill="none" stroke="#463d35" strokeWidth="6"/>
  <circle cx="45" cy="33" r="14" fill="#ffe478" stroke="#463d35" strokeWidth="1.8"/>
  <path d="m43 20-3-8m12 11 3-8" stroke="#463d35" strokeWidth="2.2" strokeLinecap="round"/><circle cx="40" cy="11" r="2.5" fill="#463d35"/><circle cx="55" cy="14" r="2.5" fill="#463d35"/>
  <circle cx="42" cy="32" r="2" fill="#463d35"/><circle cx="51" cy="32" r="2" fill="#463d35"/>
  <path d="M43 38q4 4 7 0" fill="none" stroke="#463d35" strokeWidth="1.5" strokeLinecap="round"/><circle cx="39" cy="37" r="2.5" fill="#f5a67c" opacity=".7"/><circle cx="54" cy="37" r="2.5" fill="#f5a67c" opacity=".7"/>
 </svg>;
}
