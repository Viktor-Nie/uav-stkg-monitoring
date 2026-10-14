MATCH (req:STKGSnapshot {id:'requirement:N06',_snapshot_id:'kbs_v33_frozen_stkg_20261013'})-[rf:FORMALIZED_AS]->(f:STKGSnapshot)
MATCH (f)-[ft:USES_TEMPLATE]->(t:STKGSnapshot)-[tm:IMPLEMENTED_BY]->(m:STKGSnapshot)
MATCH (f)-[fm:EXECUTED_BY]->(m)
MATCH (f)-[fs:READS_SIGNAL]->(s:STKGSnapshot)
MATCH (f)-[fb:HAS_PARAMETER_BINDING]->(b:STKGSnapshot)-[bp:BINDS_PARAMETER]->(p:STKGSnapshot)
MATCH (b)-[bs:APPLIES_TO_SIGNAL]->(s)
RETURN req,rf,f,ft,t,tm,m,fm,fs,s,fb,b,bp,p,bs ORDER BY b.role;
