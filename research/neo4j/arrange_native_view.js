(() => {
 const positions={
  'requirement:N06':[-1050,-610],'formula:N06':[-1050,0],
  'template:bounded_response':[-1700,180],
  'monitor:sampled_point_bounded_response_v2':[-1700,850],
  'signal:speed_3d_mps':[1300,350],
  'binding:N06:trigger_upper':[0,-1220],
  'binding:N06:recovery_upper':[0,-610],
  'binding:N06:deadline_seconds':[0,0],
  'binding:N06:dwell_seconds':[0,610],
  'binding:N06:value_epsilon':[0,1220]
 };
 const nodes=Array.from(document.querySelectorAll('svg g.node')).map(e=>e.__data__);
 if(nodes.length!==15)throw new Error('Expected the actual fifteen-node N06 query');
 for(const d of nodes){const id=d.propertyMap.id;
  if(d.labels.includes('FormulaParameter')){
   const binding=nodes.find(b=>b.labels.includes('ParameterBinding')&&b.propertyMap.parameter_id===id);
   if(!binding)throw new Error('Actual parameter has no returned binding');
   const xy=positions[binding.propertyMap.id];positions[id]=[xy[0],xy[1]+330];
  }
 }
 const changed=[];
 for(const d of nodes){const id=d.propertyMap.id,p=positions[id];if(!p)throw new Error('Unmapped returned node '+id);
  d.fx=p[0];d.fy=p[1];d.x=p[0];d.y=p[1];d.vx=0;d.vy=0;
  changed.push({id,x:p[0],y:p[1]});
 }
 return {nodeCount:nodes.length,viewPositions:changed,databasePropertiesChanged:false,renderer:'unchanged native Neo4j Browser; fixed view coordinates only'};
})()
