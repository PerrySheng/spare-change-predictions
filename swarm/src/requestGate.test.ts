import test from 'node:test';
import assert from 'node:assert/strict';
import {requestGate} from './requestGate.js';
test('parallel agents keep independent calls within the real request-start budget',async()=>{
 let time=0;const waits:number[]=[];const starts:number[]=[];
 const acquire=requestGate(4,61000,()=>time,async ms=>{waits.push(ms);time+=ms});
 await Promise.all(Array.from({length:9},async()=>{await acquire();starts.push(time)}));
 assert.deepEqual(waits,[61000,61000]);
 assert.equal(starts.filter(t=>t===0).length,4);
 assert.equal(starts.filter(t=>t===61000).length,4);
 assert.equal(starts.at(-1),122000);
});
