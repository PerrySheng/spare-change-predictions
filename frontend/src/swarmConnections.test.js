import test from 'node:test';
import assert from 'node:assert/strict';
import React from 'react';
import {renderToStaticMarkup} from 'react-dom/server';
import {createServer} from 'vite';
import {fileURLToPath} from 'node:url';

// Node component rendering only; this is not a browser/layout verification.
test('News related-market chip receives its profile and renders both live sides',async()=>{
 const server=await createServer({root:fileURLToPath(new URL('../',import.meta.url)),optimizeDeps:{noDiscovery:true,include:[]},server:{middlewareMode:true,hmr:false},appType:'custom'});
 try{
  const {RelatedMarket}=await server.ssrLoadModule('/src/NewsTab.jsx');
  const html=renderToStaticMarkup(React.createElement(RelatedMarket,{user:{id:'controlled-profile'},market:{id:'controlled-market',title:'Controlled contract',prices:{yes:'.3',no:'.8'}},onBet:()=>{},onSwarm:()=>{},onAdd:()=>{}}));
  assert.match(html,/30¢/);assert.match(html,/80¢/);assert.match(html,/Swarm research/);
 }finally{await server.close()}
});
