import test from 'node:test';
import assert from 'node:assert/strict';
import React from 'react';
import {renderToStaticMarkup} from 'react-dom/server';
import {createServer} from 'vite';
import {fileURLToPath} from 'node:url';

test('purchase history shows a short named list and keeps financial and zero-change clutter out',async()=>{
 const server=await createServer({root:fileURLToPath(new URL('../',import.meta.url)),optimizeDeps:{noDiscovery:true,include:[]},server:{middlewareMode:true,hmr:false},appType:'custom'});
 try{
  const {default:PurchaseHistory,purchaseHistoryRows}=await server.ssrLoadModule('/src/PurchaseHistory.jsx');
  const feed=[{id:'interest',merchant:'Interest charged',source:'plaid',is_purchase:false,roundup_cents:53,allocation:'pending'},...Array.from({length:9},(_,i)=>({id:'p'+i,merchant:i===0?'Blue Bottle Coffee':'Shop '+i,source:'plaid',is_purchase:true,roundup_cents:37,amount_cents:463,allocation:'pending',created_at:'2026-10-11T16:00:00Z'})),{id:'whole',merchant:'Whole-dollar purchase',source:'plaid',is_purchase:true,roundup_cents:0,amount_cents:500,allocation:'no_change'}];
  const html=renderToStaticMarkup(React.createElement(PurchaseHistory,{feed,onChoose:()=>{}}));
  assert.equal((html.match(/class="purchase-row"/g)||[]).length,6);
  assert.match(html,/Blue Bottle Coffee/);
  assert.doesNotMatch(html,/Interest charged|Whole-dollar purchase|\+0¢/);
  assert.match(html,/Show more purchases/);
  assert.equal(purchaseHistoryRows(feed).length,9);
 }finally{await server.close()}
});
