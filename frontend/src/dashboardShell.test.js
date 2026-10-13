import test from 'node:test';
import assert from 'node:assert/strict';
import React from 'react';
import {renderToStaticMarkup} from 'react-dom/server';
import {createServer} from 'vite';
import {fileURLToPath} from 'node:url';

test('dashboard navigation preserves destinations and balances show real values or unavailable data',async()=>{
 const server=await createServer({root:fileURLToPath(new URL('../',import.meta.url)),optimizeDeps:{noDiscovery:true,include:[]},server:{middlewareMode:true,hmr:false},appType:'custom'});
 try{
  const {DashboardSidebar,BalanceOverview}=await server.ssrLoadModule('/src/DashboardShell.jsx');
  const navigation=renderToStaticMarkup(React.createElement(DashboardSidebar,{user:{name:'Perry'},tab:'group',page:'change',mode:'paper',onNavigate:()=>{},onAddPurchase:()=>{}}));
  assert.match(navigation,/aria-current="page"[^>]*>[\s\S]*?Group betting/);
  assert.match(navigation,/Spare/);assert.match(navigation,/News/);assert.match(navigation,/Add a purchase/);
  const balances=renderToStaticMarkup(React.createElement(BalanceOverview,{dashboard:{available_cents:337,savings_cents:1200,market_value_cents:null}}));
  assert.match(balances,/\$3\.37/);assert.match(balances,/\$12\.00/);
  assert.match(balances,/Unavailable/);assert.doesNotMatch(balances,/\$0\.00|NaN/);
 }finally{await server.close()}
});
