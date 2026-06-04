# dummy-meeting-data-ingestion

OpenGIN client utilities for reading and ingesting graph entities, plus a hardcoded script to extend a legal/governance graph.

## Quick Run

From the project root:

```bash
cp .env.template .env
python3 -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
cd scripts
python extend_legal_graph.py
```

If you want to declare `.env` manually instead of copying template:

```bash
cat > .env <<'EOF'
READ_BASE_URL="http://localhost:8081"
INGESTION_BASE_URL="http://localhost:8080"
EOF
```

## Requirements

- Python 3.10+
- Local OpenGIN services:
  - read API on `READ_BASE_URL` (default `http://localhost:8081`)
  - ingestion API on `INGESTION_BASE_URL` (default `http://localhost:8080`)

Install dependencies in a virtual environment:

```bash
python3 -m venv .venv
.venv/bin/pip install -r requirements.txt
```

## Configuration

Create a `.env` file:

```bash
READ_BASE_URL="http://localhost:8081"
INGESTION_BASE_URL="http://localhost:8080"
```

## Graph Extension Script

Script path: `scripts/extend_legal_graph.py`

What it does:

- Resolves `Anura Kumara Dissanayake` as `Person/citizen`
- Traverses `AS_MINISTER` to resolve ministries (`MOE`, `MOJ`, `MOD`)
- Traverses `AS_DEPARTMENT` to resolve departments (`UGC`, `TVEC`, `OMP`, `DMC`)
- Creates 8 new entities (Document/act and Event/meeting)
- Writes 16 relationships (one `PUT` per edge; required because duplicate relation keys in one update are not yet supported by OpenGIN)
- Writes metadata on 4 act nodes and 3 meeting nodes from [`data/act_metadata.json`](data/act_metadata.json) and [`data/meeting_metadata.json`](data/meeting_metadata.json) as OpenGIN `{key, value}` arrays (logic in [`scripts/node_metadata.py`](scripts/node_metadata.py))
- Writes `rti_statuses` tabular attributes on each department (`UGC`, `TVEC`, `OMP`, `DMC`); data and write logic live in [`scripts/department_rti_attributes.py`](scripts/department_rti_attributes.py)

Run:

```bash
cd scripts
python extend_legal_graph.py
```

## Notes

- The script is intentionally hardcoded for this ingestion task.
- Relationship IDs are generated with `uuid4()` at write time.
- Re-running creates new nodes again (not fully idempotent for entity creation).
- Act/meeting metadata and `rti_statuses` writes are skipped when data already exists on the target entity.