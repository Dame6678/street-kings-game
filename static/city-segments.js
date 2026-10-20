// Persistent STREET KINGS city segment registry. Existing game rendering remains authoritative.
(function(){
'use strict';
const segments=new Map();
const sharedRoads=new Map();
window.STREET_KINGS_CITY={
  register(segment){
    if(!segment||!segment.id||!segment.division||typeof segment.build!=='function')throw Error('Invalid city segment');
    if(segments.has(segment.id))throw Error('Duplicate segment '+segment.id);
    segments.set(segment.id,Object.freeze({...segment}));
  },
  registerSharedRoad(road){
    if(!road||!road.id||!Array.isArray(road.divisions)||typeof road.build!=='function')throw Error('Invalid shared road');
    if(sharedRoads.has(road.id))throw Error('Duplicate shared road '+road.id);
    sharedRoads.set(road.id,Object.freeze({...road,divisions:[...road.divisions]}));
  },
  buildDivision(id,context){
    // Called on each canvas redraw. Geometry is emitted exactly once per segment/road per frame.
    const drawn=new Set();
    for(const segment of segments.values())if(segment.division===id&&!drawn.has(segment.id)){
      drawn.add(segment.id);segment.build(context);
    }
    for(const road of sharedRoads.values())if(road.divisions.includes(id)&&!drawn.has(road.id)){
      drawn.add(road.id);road.build(context);
    }
  },
  listDivision(id){return [...segments.values()].filter(s=>s.division===id).map(s=>({id:s.id,street:s.street,from:s.from,to:s.to}));},
  listSharedRoads(id){return [...sharedRoads.values()].filter(r=>r.divisions.includes(id)).map(r=>r.id);}
};
})();
