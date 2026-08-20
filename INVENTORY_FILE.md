# Project File Inventory

This document provides an inventory of files generated and used during the
Summer 2026 CDSS project.

## Storage Locations

### GitHub
Contains source code, configuration files, clinical scenarios, documentation,
and project files that can be version controlled.

Repository:
(https://github.com/tiffhoang04-maker/CDSS)

### SharePoint
Contains large database backups and other project assets that are unsuitable
for GitHub due to file size and/or data-sharing requirements.

Location:
Please reach out to tiffhoang04@berkeley.edu

### `cdss-mcp-server/`

Contains the current Model Context Protocol (MCP) implementation for the clinical decision support system.

Key files include:

* `server.py` — defines the MCP server and available tools.
* `state_manager.py` — manages the current patient state and updates during a scenario.
* `case_repository.py` — loads scenario and patient case information.
* `neo4j_client.py` — handles connections and queries to the Neo4j knowledge graph.
* `clinical_guidance_service.py` — generates knowledge-graph-supported clinical guidance and differential diagnoses.
* `requirements.txt` — Python dependencies required to run the project.
* `README.md` — installation, repository structure, and usage documentation.

### `personas/`

Contains patient persona files used in simulated clinical scenarios.

* `patient_001.json`

### `scenarios/`

Contains scenario-specific files.

Current example:

```text
scenarios/
└── case_001/
    ├── public.json
    ├── simulation.json
    └── evaluation.json
```

* `public.json` — information available to the user/system at the beginning of the scenario.
* `simulation.json` — scenario progression and hidden simulation information.
* `evaluation.json` — expected outcomes or information used for system evaluation.

### `state/`

Contains the active patient state used by the MCP server.

* `current_patient.json`

### `prompts/`

Contains prompt templates used by the system including an agent.md file and a few baselines for the initial assessments and clinical workflow.

### `chainlit_ui/`

Contains the current Chainlit user interface.

* `app.py`

The application can be launched from the project root using:

```bash
chainlit run chainlit_ui/app.py -w
```

### `.chainlit/`

Contains Chainlit configuration files associated with the interface.

### `Charlotte_model_scripts/`

Contains a subset of the Python scripts that helped establish the foundation for the current project.

These scripts include several of the original clinical decision-support functions but do not contain an MCP server.

The original application was built using **Streamlit** and analyzes **pneumothorax as a predefined ("canned") scenario**.

The scenario-specific pneumothorax files used by that application are **not included in this repository**.

---

## Neo4j Knowledge Graph Databases

Several Neo4j databases were used during development and integration.

### ExMC

Original Exploration Medical Capability knowledge graph used as the primary foundation for the CDSS.

### PrimeKG Database

PrimeKG-derived database used to enrich ExMC with additional biomedical relationships and ontology mappings. This file is the version from January 2026.

### Exmc_Integrated Knowledge Graph

If you are new to the project, please use this knowledge graph as the main one you're playing around with on neo4j!

The integrated database combines ExMC with selected information (one example are drug-disease enhancements including the addition of contraindication, indication, and off-label use relationships) from PrimeKG and additional ontology mappings.

Relevant integrated content includes:

* Disease mappings using DOID and MONDO (this is a CSV file on Git, but the integrated KG will contain this information already)
* Condition ontology mappings
* Symptom / phenotype mappings
* DrugBank identifiers
* Drug indication relationships
* Drug contraindication relationships
* Off-label drug relationships
* Additional disease and phenotype context

Neo4j database dumps are stored separately because some files exceed GitHub's file-size limits.

---

## External Backups

### SharePoint

Large files that cannot be stored in GitHub are uploaded on SharePoint.

This includes:

* Neo4j `.dump` files
* Large knowledge graph database backups
* Other large project artifacts, where applicable

Recommended dump files to retain include:

* Original ExMC database dump
* PrimeKG database dump
* Exmc_integrated knowledge graph dump
* Most recent working database dump

> Add the exact SharePoint folder path or link here if appropriate.

---

## Files Not Included in GitHub

The following files are intentionally stored outside of the repository:

* Neo4j database dump files exceeding GitHub's size limits
* Original / external knowledge graph datasets where redistribution may not be appropriate
* Pneumothorax scenario files associated with the original Streamlit implementation
* Any restricted, internal, or externally managed NASA files

---

## Primary Project Outputs

The major outputs of this project include:

1. MCP-based clinical decision support server
2. Chainlit clinical interface
3. Integrated ExMC / PrimeKG biomedical knowledge graph (available on sharepoint)
4. Ontology mappings between ExMC and external biomedical knowledge sources (a CSV file on GitHub, no longer necessary if you're just looking at the integrated knowledge graph dump)
5. Drug and disease relationship enrichment
6. Condition and phenotype enrichment
7. Simulated clinical scenario framework
8. Poster and demonstration materials (available on Sharepoint)

---

## Recommended Handoff / Recovery Order

If the project needs to be restored on a new machine:

1. Clone the GitHub repository.
2. Install the dependencies listed in `requirements.txt`.
3. Install or open Neo4j Desktop.
4. Retrieve the appropriate Neo4j `.dump` file from SharePoint. You can just open Prime / Integrated for most up to date results.
5. Restore the database from the dump.
6. Update Neo4j credentials or connection settings if necessary.
7. Confirm the MCP server can connect to Neo4j.
8. Launch the Chainlit interface:

```bash
chainlit run chainlit_ui/app.py -w
```

9. Run a test clinical scenario to confirm the system is functioning.

---

## Storage Summary

| Resource                        | Location                  | Notes                              |
| ------------------------------- | ------------------------- | ---------------------------------- |
| Source code                     | GitHub                    | Main project repository            |
| README / documentation          | GitHub                    | Repository documentation           |
| Patient / scenario JSON files   | GitHub                    | Used by MCP server                 |
| Chainlit interface              | GitHub                    | Current UI                         |
| Charlotte foundational scripts  | GitHub                    | Earlier Streamlit implementation   |
| Neo4j database dumps            | SharePoint                | Stored externally due to file size |
| Integrated knowledge graph      | Neo4j + SharePoint backup | Primary enriched database          |
| Poster / presentation materials | [Add location]            | Add final storage location         |
| External datasets / mappings    | [Add location]            | Add location if separate           |

## Notes

This inventory should be updated whenever major files, databases, or backup locations change.

