"""Optional actual Neo4j import and roundtrip; requires a dedicated database.

Never clears databases or reads/saves credentials from files. Supply a local
NEO4J_PASSWORD environment variable; credentials are not printed or recorded.
"""
from __future__ import annotations
import argparse, csv, hashlib, json, os
from pathlib import Path
from neo4j import GraphDatabase
ROOT = Path(__file__).resolve().parents[2]
SNAPSHOT = "kbs_v33_frozen_stkg_20261013"
OUT = ROOT / "outputs/neo4j_snapshot"
RELATIONS = {"FORMALIZED_AS", "USES_TEMPLATE", "IMPLEMENTED_BY", "EXECUTED_BY", "READS_SIGNAL", "HAS_PARAMETER_BINDING", "BINDS_PARAMETER", "APPLIES_TO_SIGNAL"}
LABELS = {"Entity", "Requirement", "STLFormula", "STLTemplate", "RuntimeMonitor", "FormulaParameter", "ParameterBinding", "Signal", "Threshold", "RuntimeParameter", "NumericTolerance"}

def rows(path: Path) -> list[dict]:
    with path.open(encoding="utf-8-sig", newline="") as handle:
        return list(csv.DictReader(handle))

def sha(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()

def write_json(path: Path, value: object) -> None:
    path.write_text(json.dumps(value, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")

def write_csv(path: Path, records: list[dict], fields: list[str]) -> None:
    with path.open("w", encoding="utf-8-sig", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=fields)
        writer.writeheader()
        writer.writerows(records)

def counts(tx) -> tuple[int, int]:
    nodes = tx.run("MATCH (n:STKGSnapshot {_snapshot_id:$snapshot}) RETURN count(n) AS count", snapshot=SNAPSHOT).single()["count"]
    edges = tx.run("MATCH (:STKGSnapshot {_snapshot_id:$snapshot})-[r {_snapshot_id:$snapshot}]->(:STKGSnapshot {_snapshot_id:$snapshot}) RETURN count(r) AS count", snapshot=SNAPSHOT).single()["count"]
    return nodes, edges

def import_graph(driver, nodes: list[dict], edges: list[dict]) -> dict:
    for node in nodes:
        if set(node["labels"].split(";")) - LABELS:
            raise ValueError("Input contains an unsupported node label")
    if {edge["relation"] for edge in edges} - RELATIONS:
        raise ValueError("Input contains an unsupported relation")
    with driver.session(database="neo4j") as session:
        session.run("CREATE CONSTRAINT v33_snapshot_identity IF NOT EXISTS FOR (n:STKGSnapshot) REQUIRE (n._snapshot_id,n.id) IS UNIQUE").consume()
        before = session.execute_read(counts)

        def write(tx):
            for labels in sorted({node["labels"] for node in nodes}):
                payload = [dict(row, properties=json.loads(row["properties_json"]), display_caption=display_caption(row)) for row in nodes if row["labels"] == labels]
                label_clause = ":".join(labels.split(";"))
                tx.run(
                    f"UNWIND $rows AS row MERGE (n:STKGSnapshot {{_snapshot_id:$snapshot,id:row.id}}) "
                    f"SET n:{label_clause} SET n += row.properties SET n.name=row.name,n.properties_json=row.properties_json,n._display_caption=row.display_caption",
                    rows=payload, snapshot=SNAPSHOT,
                ).consume()
            for relation in sorted(RELATIONS):
                payload = [dict(row, properties=json.loads(row["properties_json"])) for row in edges if row["relation"] == relation]
                tx.run(
                    "UNWIND $rows AS row MATCH (a:STKGSnapshot {_snapshot_id:$snapshot,id:row.source}),"
                    "(b:STKGSnapshot {_snapshot_id:$snapshot,id:row.target}) "
                    f"MERGE (a)-[r:{relation} {{_snapshot_id:$snapshot}}]->(b) "
                    "SET r += row.properties SET r.properties_json=row.properties_json",
                    rows=payload, snapshot=SNAPSHOT,
                ).consume()
        session.execute_write(write)
        first = session.execute_read(counts)
        session.execute_write(write)
        second = session.execute_read(counts)
        if first != (len(nodes), len(edges)) or second != first:
            raise AssertionError("Database counts or repeated-import idempotence failed")
        return {"before": list(before), "first_import": list(first), "second_import": list(second), "idempotent": True}

def display_caption(row: dict) -> str:
    """Deterministic short view labels; archived source properties stay exact."""
    identifier = row["id"]
    data = json.loads(row["properties_json"])
    if identifier.startswith("requirement:"):
        return row["name"] + " req"
    if identifier.startswith("formula:"):
        return row["name"] + " STL"
    if identifier.startswith("binding:"):
        return {"upper_bound": "bound b", "trigger_upper": "trigger u", "recovery_upper": "recovery r", "deadline_seconds": "deadline d", "dwell_seconds": "dwell tau", "value_epsilon": "tolerance eps"}[data["role"]]
    if identifier.startswith("signal:"):
        return {"speed_3d_mps": "speed 3D", "height_m": "rel. height", "abs_roll_rad": "abs. roll", "abs_pitch_rad": "abs. pitch", "ang_rate_norm_rps": "ang. rate"}[data["signal_id"]]
    if identifier.startswith("template:"):
        return "invariant" if row["name"] == "invariant_upper" else "response"
    if identifier.startswith("monitor:"):
        return "invariant monitor" if "invariant_upper" in identifier else "response monitor"
    if identifier.startswith("parameter:"):
        # Display only; source precision is retained and compared separately.
        value = format(float(data["value"]), ".5g")
        unit = str(data["unit"])
        return value + " " + unit
    return row["name"]

def roundtrip(driver, source_nodes: list[dict], source_edges: list[dict]) -> dict:
    with driver.session(database="neo4j") as session:
        dbnodes = session.run("MATCH (n:STKGSnapshot {_snapshot_id:$snapshot}) RETURN n.id AS id,labels(n) AS labels,properties(n) AS props ORDER BY id", snapshot=SNAPSHOT).data()
        dbedges = session.run("MATCH (a:STKGSnapshot {_snapshot_id:$snapshot})-[r {_snapshot_id:$snapshot}]->(b:STKGSnapshot {_snapshot_id:$snapshot}) RETURN a.id AS source,type(r) AS relation,b.id AS target,properties(r) AS props ORDER BY source,relation,target", snapshot=SNAPSHOT).data()
    original_nodes = {row["id"]: row for row in source_nodes}
    original_edges = {(row["source"], row["relation"], row["target"]): row for row in source_edges}
    exported_nodes, exported_edges = [], []
    for row in dbnodes:
        original = original_nodes[row["id"]]
        properties = dict(row["props"])
        if properties.pop("_snapshot_id") != SNAPSHOT or properties.pop("id") != original["id"] or properties.pop("name") != original["name"]:
            raise AssertionError("Node wrapper metadata does not match")
        raw = properties.pop("properties_json")
        if properties.pop("_display_caption") != display_caption(original):
            raise AssertionError("Derived display caption does not match the frozen record")
        if raw != original["properties_json"] or properties != json.loads(raw):
            raise AssertionError("Node property roundtrip mismatch")
        if set(row["labels"]) != set(original["labels"].split(";")) | {"STKGSnapshot"}:
            raise AssertionError("Node label roundtrip mismatch")
        exported_nodes.append(dict(original))
    for row in dbedges:
        original = original_edges[(row["source"], row["relation"], row["target"])]
        properties = dict(row["props"])
        if properties.pop("_snapshot_id") != SNAPSHOT:
            raise AssertionError("Relationship snapshot metadata does not match")
        raw = properties.pop("properties_json")
        if raw != original["properties_json"] or properties != json.loads(raw):
            raise AssertionError("Relationship property roundtrip mismatch")
        exported_edges.append(dict(original))
    if len(exported_nodes) != len(source_nodes) or len(exported_edges) != len(source_edges):
        raise AssertionError("Missing database entities during roundtrip")
    write_csv(OUT / "roundtrip_nodes.csv", exported_nodes, list(source_nodes[0]))
    write_csv(OUT / "roundtrip_relationships.csv", exported_edges, list(source_edges[0]))
    return {"nodes_compared": len(dbnodes), "relationships_compared": len(dbedges), "all_source_labels_properties_and_endpoints_equal": True, "comparison": "logical IDs, exact names, label sets, original JSON and flattened typed property maps; Neo4j internal IDs excluded; snapshot wrapper metadata and separately verified derived display captions excluded", "display_metadata": "_display_caption is deterministic from logical ID, role and rounded value/unit; source precision is unchanged"}

def queries(driver) -> dict:
    n06 = """MATCH (req:STKGSnapshot {id:'requirement:N06',_snapshot_id:$snapshot})-[rf:FORMALIZED_AS]->(f:STKGSnapshot)
MATCH (f)-[ft:USES_TEMPLATE]->(t:STKGSnapshot)-[tm:IMPLEMENTED_BY]->(m:STKGSnapshot)
MATCH (f)-[fm:EXECUTED_BY]->(m)
MATCH (f)-[fs:READS_SIGNAL]->(s:STKGSnapshot)
MATCH (f)-[fb:HAS_PARAMETER_BINDING]->(b:STKGSnapshot)-[bp:BINDS_PARAMETER]->(p:STKGSnapshot)
MATCH (b)-[bs:APPLIES_TO_SIGNAL]->(s)
RETURN req,rf,f,ft,t,tm,m,fm,fs,s,fb,b,bp,p,bs ORDER BY b.role"""
    entire = "MATCH (a:STKGSnapshot {_snapshot_id:$snapshot}) OPTIONAL MATCH (a)-[r {_snapshot_id:$snapshot}]->(b:STKGSnapshot {_snapshot_id:$snapshot}) RETURN a,r,b"
    (OUT / "n06_graph.cypher").write_text(n06.replace("$snapshot", "'" + SNAPSHOT + "'") + ";\n", encoding="utf-8")
    (OUT / "full_graph.cypher").write_text(entire.replace("$snapshot", "'" + SNAPSHOT + "'") + ";\n", encoding="utf-8")
    with driver.session(database="neo4j") as session:
        graph = session.run(n06, snapshot=SNAPSHOT).graph()
        if len(graph.nodes) != 15 or len(graph.relationships) != 20:
            raise AssertionError("Actual Neo4j N06 query differs from frozen representative subgraph")
        binding = session.run("MATCH (f:STKGSnapshot {id:'formula:N06',_snapshot_id:$snapshot})-[:HAS_PARAMETER_BINDING]->(b)-[:BINDS_PARAMETER]->(p) RETURN b.role AS role,p.id AS parameter_id,p.value AS value,p.unit AS unit,p.source_type AS source_type,p.source_reference AS source_reference,p.vehicle_context AS vehicle_context,p.flight_mode_context AS flight_mode_context,p.firmware_context AS firmware_context ORDER BY role", snapshot=SNAPSHOT).data()
        write_json(OUT / "n06_binding_query_result.json", binding)
        full = session.run(entire, snapshot=SNAPSHOT).graph()
        full_ids = {node["id"] for node in full.nodes}
        orphan_nodes = session.run("MATCH (n:STKGSnapshot {_snapshot_id:$snapshot}) WHERE NOT (n)--() RETURN n.id AS id", snapshot=SNAPSHOT).data()
        node_inventory = session.run("MATCH (n:STKGSnapshot {_snapshot_id:$snapshot}) UNWIND labels(n) AS label WITH label,count(*) AS count WHERE label <> 'STKGSnapshot' AND label <> 'Entity' RETURN label,count ORDER BY label", snapshot=SNAPSHOT).data()
        relation_inventory = session.run("MATCH (:STKGSnapshot {_snapshot_id:$snapshot})-[r {_snapshot_id:$snapshot}]->(:STKGSnapshot {_snapshot_id:$snapshot}) RETURN type(r) AS relation,count(*) AS count ORDER BY relation", snapshot=SNAPSHOT).data()
        version = session.run("CALL dbms.components() YIELD name,versions,edition RETURN name,versions,edition").data()
    write_json(OUT / "database_inventory.json", {"node_labels": node_inventory, "relation_types": relation_inventory, "isolated_nodes": orphan_nodes})
    return {"n06_query_nodes": len(graph.nodes), "n06_query_relationships": len(graph.relationships), "n06_binding_rows": len(binding), "full_query_nodes": len(full_ids), "full_query_relationships": len(full.relationships), "isolated_nodes": orphan_nodes, "database_components": version}

if __name__ == "__main__":
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--uri", default=os.getenv("NEO4J_URI", "bolt://127.0.0.1:7687"))
    parser.add_argument("--database", default=os.getenv("NEO4J_DATABASE", "neo4j"))
    parser.add_argument("--output", type=Path, default=OUT)
    args=parser.parse_args()
    if args.database != "neo4j":
        parser.error("This snapshot script targets a dedicated neo4j database; use a separate instance.")
    credential=os.getenv("NEO4J_PASSWORD")
    if not credential:
        parser.error("Set NEO4J_PASSWORD locally; no credential file is read or saved.")
    OUT=args.output.resolve()
    if OUT==ROOT or any(OUT.is_relative_to(ROOT/folder) for folder in ("data","src","research")):
        parser.error("Output must not overwrite release inputs or evidence.")
    OUT.mkdir(parents=True,exist_ok=True)
    node_file=ROOT/"data/graph/nodes.csv"
    edge_file=ROOT/"data/graph/relationships.csv"
    nodes,edges=rows(node_file),rows(edge_file)
    with GraphDatabase.driver(args.uri,auth=(os.getenv("NEO4J_USER","neo4j"),credential)) as driver:
        driver.verify_connectivity()
        imported=import_graph(driver,nodes,edges)
        compared=roundtrip(driver,nodes,edges)
        queried=queries(driver)
    result={"status":"passed","snapshot":SNAPSHOT,"import":imported,"roundtrip":compared,"queries":queried,
        "input_sha256":{"data/graph/nodes.csv":sha(node_file),"data/graph/relationships.csv":sha(edge_file)},
        "credential_saved":False,"physical_applicability_verified":False,"backend_migrated":False}
    write_json(OUT/"neo4j_roundtrip_receipt.json",result)
    write_json(OUT/"native_display_caption_mapping.json",{row["id"]:display_caption(row) for row in nodes})
    print(json.dumps({"status":"passed","nodes":compared["nodes_compared"],"relationships":compared["relationships_compared"]},indent=2))
