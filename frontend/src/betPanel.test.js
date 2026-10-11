import {test} from 'node:test';
import assert from 'node:assert/strict';
import {createRequire} from 'node:module';
import {pathToFileURL} from 'node:url';
import React from 'react';
import {renderToStaticMarkup} from 'react-dom/server';
import {build} from 'esbuild';

const require=createRequire(import.meta.url);
const compiled=await build({
  entryPoints:[new URL('./NewsTab.jsx',import.meta.url).pathname],
  bundle:true,write:false,format:'esm',platform:'node',loader:{'.css':'empty'},
  define:{'import.meta.env.DEV':'false'},
  plugins:[{name:'shared-react',setup(builder){
    builder.onResolve({filter:/^(react|lucide-react)$/},args=>({path:pathToFileURL(require.resolve(args.path)).href,external:true}));
  }}],
});
const {DemoBetDialog,MarketBetDialog}=await import('data:text/javascript;base64,'+Buffer.from(compiled.outputFiles[0].text).toString('base64'));
const market={id:'demo',title:'Who wins the final?',label:'Boston',prices:{yes:'0.40',no:'0.63'}};

test('demo dialog displays the requested example and explicitly identifies the practice state',()=>{
  const html=renderToStaticMarkup(React.createElement(DemoBetDialog,{market,side:'yes',onClose(){}}));
  assert.match(html,/Win \$1\.83/);
  assert.match(html,/\+\$1\.10/);
  assert.match(html,/40% implied chance/);
  assert.match(html,/value="0.73"/);
  assert.match(html,/Who wins the final\?/);
  assert.match(html,/Boston/);
  assert.match(html,/Demo preview/);
  assert.match(html,/No order or position is created/);
  assert.doesNotMatch(html,/Record paper position|Place sandbox order/);
});

test('demo No preview uses the independent No quote without a complement',()=>{
  const html=renderToStaticMarkup(React.createElement(DemoBetDialog,{market,side:'no',onClose(){}}));
  assert.match(html,/Win \$1\.16/);
  assert.match(html,/63% implied chance/);
  assert.doesNotMatch(html,/60% implied chance/);
});

test('live dialog combines all purchase change plus rollover and waits for a quote',()=>{
  const html=renderToStaticMarkup(React.createElement(MarketBetDialog,{
    user:{id:'user',paused:false},market,side:'yes',
    purchases:[{roundup_id:'first',allocation:'pending',roundup_cents:20,merchant:'Cafe'},{roundup_id:'active',allocation:'pending',roundup_cents:73,merchant:'Shop'}],
    initialRoundupId:'active',rolloverCents:10,remainingCapCents:200,onClose(){},onDone(){},onPurchase(){},
  }));
  assert.match(html,/Your accumulated change/);
  assert.match(html,/2 purchases/);
  assert.match(html,/value="1.03"/);
  assert.match(html,/\$1\.03 available/);
  assert.match(html,/<button class="primary"[^>]*disabled=""[^>]*>[\s\S]*?Record paper position<\/button>/);
});

test('a legacy weekly cap no longer limits the accumulated change',()=>{
  const html=renderToStaticMarkup(React.createElement(MarketBetDialog,{
    user:{id:'user',paused:false},market,side:'yes',
    purchases:[{roundup_id:'active',allocation:'pending',roundup_cents:73,merchant:'Shop'}],
    rolloverCents:10,remainingCapCents:50,onClose(){},onDone(){},onPurchase(){},
  }));
  assert.match(html,/value="0.83"/);
  assert.match(html,/\$0.83 available/);
  assert.doesNotMatch(html,/weekly cap/);
});
