// Presentation examples only. These identifiers never belong to Gemini.
const contract=(event,id,label,yes,no)=>({id:`demo-${id}`,event_ticker:event.id,title:event.title,label,category:event.category,topic:event.topic,closes_at:null,source:'demo',prices:{yes,no},implied_probability:yes});
function example(id,title,category,topic,rows){
 const event={id:`demo-${id}`,title,category,topic,closes_at:null,source:'demo'};
 return {...event,outcomes:rows.map(([id,label,yes,no])=>contract(event,id,label,yes,no))};
}

export const demoMarketEvents=[
 example('bitcoin','Will Bitcoin close above $100,000 this month?','Crypto','crypto',[
  ['bitcoin-above','Above $100,000',.68,.34],
 ]),
 example('basketball','Who will win the basketball championship?','Sports','sports',[
  ['basketball-warriors','Golden State Warriors',.17,.85],
  ['basketball-celtics','Boston Celtics',.32,.70],
  ['basketball-nuggets','Denver Nuggets',.24,.78],
  ['basketball-lakers','Los Angeles Lakers',.13,.89],
  ['basketball-knicks','New York Knicks',.08,.94],
  ['basketball-bucks','Milwaukee Bucks',.06,.96],
 ]),
 example('riverside','Who will win the Riverside mayoral election?','Politics','politics',[
  ['riverside-chen','Ava Chen',.46,.56],
  ['riverside-wright','Jordan Wright',.27,.75],
  ['riverside-garcia','Maya Garcia',.15,.87],
  ['riverside-cole','Sam Cole',.08,.94],
  ['riverside-other','Another candidate',.04,.98],
 ]),
 example('rain','Will San Francisco have rain this weekend?','Weather','weather',[
  ['rain-yes','Measurable rain',.41,.61],
 ]),
 example('inflation','Will the next inflation reading fall below 3%?','Economy','economy',[
  ['inflation-below','Below 3%',.57,.45],
 ]),
 example('album','Will a surprise album debut at No. 1 this month?','Culture','entertainment',[
  ['album-top','No. 1 debut',.36,.66],
 ]),
];
