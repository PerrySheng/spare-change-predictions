import test from 'node:test';
import assert from 'node:assert/strict';
import {shouldShowIntro,rememberIntro} from './introPolicy.js';

const tabStorage=()=>{
 const entries=new Map();
 return {getItem:key=>entries.get(key)??null,setItem:(key,value)=>entries.set(key,value)};
};

test('brand opening appears once in a tab session, then lets the app open directly',()=>{
 const storage=tabStorage();
 assert.equal(shouldShowIntro({pathname:'/',storage}),true);
 rememberIntro(storage);
 assert.equal(shouldShowIntro({pathname:'/',storage}),false);
 assert.equal(shouldShowIntro({pathname:'/',storage:tabStorage()}),true);
});

test('purchase and swarm deep links, and reduced motion, bypass the opening',()=>{
 const storage=tabStorage();
 for(const pathname of ['/roundup','/swarm/a-real-run','/invite']) assert.equal(shouldShowIntro({pathname,storage}),false);
 assert.equal(shouldShowIntro({pathname:'/',storage,reducedMotion:true}),false);
});

test('blocked browser storage cannot prevent the app from opening',()=>{
 const storage={getItem(){throw new Error('Storage blocked')},setItem(){throw new Error('Storage blocked')}};
 assert.equal(shouldShowIntro({pathname:'/',storage}),true);
 assert.doesNotThrow(()=>rememberIntro(storage));
});
