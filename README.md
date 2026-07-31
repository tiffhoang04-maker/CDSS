# Clinical Decision Support System MCP Server

A Model Context Protocol (MCP) server that supports structured clinical reasoning for simulated medical emergencies in remote and resource-limited environments.

This project connects a large language model to patient-state data, scenario files, and a biomedical knowledge graph so the model can collect clinical information, identify missing assessments, generate differential diagnoses, retrieve relevant medical context, and recommend stage-appropriate next steps.

> **Project status:** Poster and demonstration prototype
> **Intended use:** Research, education, and simulated clinical scenarios only
> **Not intended for real-world medical diagnosis or treatment**

---

## Overview

During deep-space missions, crew members may need to manage medical emergencies with delayed communication, limited diagnostic capabilities, and a constrained medical kit.

This project explores whether an MCP server can help a language model provide more structured, traceable, and resource-aware clinical decision support.

The server acts as an interface between the language model and several sources of clinical context:

* Current patient state
* Simulated case data
* Clinical assessment requirements
* Biomedical knowledge graph relationships
* Available medical-kit resources
* Stage-specific clinical actions

The MCP architecture allows users to interact with these resources through natural language rather than manually writing database queries or navigating multiple data files.

---

## Current Capabilities

The current prototype can:

* Start and manage a simulated patient case
* Store the patient’s current clinical state
* Record symptoms, vital signs, examination findings, and completed assessments
* Identify missing information needed for the current stage of care
* Generate and refine a differential diagnosis
* Retrieve disease, symptom, action, treatment, and medical-kit relationships from a Neo4j knowledge graph
* Support selection of a working or final diagnosis
* Recommend stage-appropriate next steps
* Identify potential gaps between recommended care and available resources

The exact behavior depends on the scenario data, knowledge graph coverage, and language model connected to the server.

---

## Example Workflow

1. A patient presents with symptoms.
2. The user describes the patient in natural language.
3. The language model calls MCP tools to retrieve the patient state and determine which clinical information is missing.
4. New findings are added to the patient record.
5. The server queries the knowledge graph for relevant diseases, symptoms, actions, treatments, and medical-kit resources.
6. A differential diagnosis is generated and refined as additional information becomes available.
7. The language model recommends the next appropriate assessment or care step.
8. The process continues until a final diagnosis or care-stage output is reached.

Example interaction:

```text
User:
Start case_001.

Assistant:
The case has been started. I need an initial assessment before generating
a differential diagnosis. Please provide the patient's vital signs and
primary symptoms.

User:
The patient has a headache, shortness of breath, poor coordination,
and an oxygen saturation of 86%.

Assistant:
The findings suggest possible hypoxemia and neurologic impairment.
I will retrieve relevant differential diagnoses and determine which
additional assessments are needed.
```

---

## Architecture

The prototype separates patient information, scenario data, application logic, and knowledge-graph retrieval.

```text
.chainlit/
|** will update later but it has the app.py and interface application;
|pasting in your terminal should launch the application in your web browser: chainlit run chainlit_ui/app.py -w
cdss-mcp-server/
├── server.py
├── state_manager.py
├── case_repository.py
├── neo4j_client.py
├── clinical_guidance_service.py
├── requirements.txt
├── README.md
│
├── personas/
│   └── patient_001.json
│
├── scenarios/
│   └── case_001/
│       ├── public.json
│       ├── simulation.json
│       └── evaluation.json
│
├── state/
│   └── current_patient.json
│
├── config/
│   └── observation_mappings.json
│
└── prompts/
    └── [prompt files]
```
chainlit_ui/
** will update later :D

Charlotte_model_scripts/
** a fraction of the python scripts that first set the foundation for this project; it includes the different functions (but no mcp server)
** her application is ran on Streamlit!
** Charlotte's project analyzes Pneumothorax as a "canned scenario"; those scenario scripts are not available here.

### Main Components

#### `server.py`

Defines the MCP server and exposes the tools that can be called by the connected language model.

#### `state_manager.py`

Reads and updates the current patient state, including:

* Current clinical stage
* Recorded observations
* Completed assessments
* Working differential
* Working diagnosis
* Case status

#### `case_repository.py`

Loads public, simulation, and evaluation data for a selected scenario (scenarios were hardcoded for demo purposes during this internship period).

#### `clinical_guidance_service.py`

Transforms patient findings into knowledge-graph search terms and coordinates differential-diagnosis retrieval.

#### `neo4j_client.py`

Handles Neo4j database connections and knowledge-graph queries.

---

## Scenario Structure

Each simulated case is stored in its own directory.

```text
scenarios/
└── case_001/
    ├── public.json
    ├── simulation.json
    └── evaluation.json
```

### `public.json`

Contains information that may be shown to the user or language model when the case begins.

Example:

```json
{
  "scenario_id": "case_001",
  "title": "Altitude-Related Illness",
  "initial_stage": "initial_assessment",
  "persona_id": "patient_001",
  "opening_context": "The patient reports headache and shortness of breath."
}
```

### `simulation.json`

Contains hidden scenario behavior, expected findings, and information revealed after specific assessments.

This file should not be exposed directly to the language model during normal case execution.

### `evaluation.json`

Contains expected diagnoses, actions, and scoring criteria used to evaluate system performance.

---

## Patient State

The active patient record is stored in:

```text
state/current_patient.json
```

Example:

```json
{
  "patient_id": "current_patient",
  "scenario_id": "case_001",
  "persona_id": "patient_001",
  "status": "active",
  "current_stage": "initial_assessment",
  "clinical_data": {},
  "completed_triggers": [],
  "working_differential": [],
  "working_diagnosis": null
}
```

The patient state is updated as the language model collects findings and completes clinical actions.

---

## MCP Tools

The exact tool names may change as the prototype is refined. A typical implementation includes tools for the following functions.

### Start or Reset a Case

Loads a scenario and initializes the patient state.

```text
start_case(scenario_id="case_001")
```

### Get Current Patient Status

Returns the current stage, recorded findings, completed assessments, differential diagnoses, and working diagnosis.

```text
get_patient_status()
```

### Record Clinical Information

Adds symptoms, vital signs, physical examination findings, or other observations to the patient record.

```text
record_clinical_data(
    observations={
        "spo2": 86,
        "headache": true,
        "coordination": "impaired"
    }
)
```

### Assess Information Gaps

Determines which assessments or observations are still needed before progressing.

```text
assess_information_gaps()
```

### Retrieve Clinical Guidance

Generates differential diagnoses or retrieves diagnosis-specific clinical context.

```text
get_clinical_guidance(
    task="differential"
)
```

Diagnosis-specific example:

```text
get_clinical_guidance(
    task="diagnosis_context",
    diagnosis_id="DOID:0050156"
)
```

### Submit a Clinical Choice

Records a selected action, stage transition, working diagnosis, or next step.

```text
submit_choice(
    choice_type="working_diagnosis",
    choice_id="altitude_sickness"
)
```

---

## Prerequisites

Before running the project, install:

* Python 3.11 or later
* Neo4j Desktop, Neo4j Community Edition, or access to a Neo4j instance
* An MCP-compatible client
* A language model or chat application capable of connecting to MCP servers

Examples of MCP-compatible clients may include:

* Claude Desktop
* Codex
* An MCP Inspector
* A locally developed Streamlit or web interface
* Another application that supports standard MCP server configuration

---

## Installation

### 1. Clone the Repository

```bash
git clone https://github.com/[YOUR-USERNAME]/[YOUR-REPOSITORY].git
cd [YOUR-REPOSITORY]
```

### 2. Create a Virtual Environment

macOS or Linux:

```bash
python3 -m venv .venv
source .venv/bin/activate
```

Windows:

```powershell
python -m venv .venv
.venv\Scripts\activate
```

### 3. Install Dependencies

```bash
pip install -r requirements.txt
```

A minimal `requirements.txt` may include:

```text
mcp
neo4j
python-dotenv
pydantic
```

Add any additional packages used by the repository.

---

## Neo4j Configuration

Create a `.env` file in the repository root.

```env
NEO4J_URI=neo4j://localhost:7687
NEO4J_USERNAME=neo4j
NEO4J_PASSWORD=your-password
NEO4J_DATABASE=integrated
```

Do not commit the `.env` file to GitHub.

Add it to `.gitignore`:

```text
.env
.venv/
__pycache__/
*.pyc
state/current_patient.json
```

Whether `current_patient.json` should be ignored depends on whether the repository includes a blank demonstration state file. Another option is to commit a template:

```text
state/current_patient.example.json
```

---

## Knowledge Graph Requirements

The server is designed to retrieve biomedical relationships from a Neo4j knowledge graph.

The current project is based on the Exploration Medical Capability knowledge graph and may include mapped or imported information from external biomedical knowledge graphs.

Example node types include:

* `Disease`
* `Symptom`
* `Condition`
* `Action`
* `MedKit`
* `GapReport`

Example relationships include:

```text
(Disease)-[:PRESENTS_DpS]->(Symptom)
(Action)-[:DIAGNOSES_AdC]->(Condition)
(Action)-[:ASSISTSTREATMENT_AaC]->(Condition)
(MedKit)-[:TREATS_MKtC]->(Condition)
(Condition)-[:MAPSTO_CmD]->(Disease)
(Disease)-[:RESEMBLES_DrD]->(Disease)
```

The exact labels and relationship names must match those used in your Neo4j database.

---

## Verify the Neo4j Connection

Before running the MCP server, confirm that Neo4j is active and the configured database is available.

Example Python test:

```python
from neo4j import GraphDatabase
import os

driver = GraphDatabase.driver(
    os.environ["NEO4J_URI"],
    auth=(
        os.environ["NEO4J_USERNAME"],
        os.environ["NEO4J_PASSWORD"]
    )
)

with driver.session(
    database=os.getenv("NEO4J_DATABASE", "neo4j")
) as session:
    result = session.run("RETURN 1 AS value")
    print(result.single()["value"])

driver.close()
```

Expected output:

```text
1
```

---

## Running the MCP Server

Run the server from the repository root.

```bash
python server.py
```

Depending on the MCP library and transport used by the project, the command may instead resemble:

```bash
mcp run server.py
```

or:

```bash
fastmcp run server.py
```

Use the command supported by the version of the MCP SDK installed in the project.

---

## Connecting an MCP Client

Configure the client to launch the server using the repository’s virtual environment.

Example configuration:

```json
{
  "mcpServers": {
    "cdss-mcp-server": {
      "command": "/absolute/path/to/.venv/bin/python",
      "args": [
        "/absolute/path/to/cdss-mcp-server/server.py"
      ],
      "env": {
        "NEO4J_URI": "neo4j://localhost:7687",
        "NEO4J_USERNAME": "neo4j",
        "NEO4J_PASSWORD": "your-password",
        "NEO4J_DATABASE": "integrated"
      }
    }
  }
}
```

On Windows, the Python path may look like:

```text
C:\path\to\repository\.venv\Scripts\python.exe
```

Use absolute paths in the client configuration.

---

## Suggested Demo Procedure

### 1. Start Neo4j

Confirm that the target database is running.

### 2. Start the MCP Client

Open the MCP Inspector, Codex, Claude Desktop, or another configured client.

### 3. Confirm Tool Availability

Verify that the CDSS tools appear in the client.

### 4. Start a Scenario

```text
Start case_001.
```

### 5. Enter Patient Findings

```text
The patient reports headache, dizziness, shortness of breath,
and difficulty walking. Their oxygen saturation is 86%.
```

### 6. Request Clinical Reasoning

```text
What additional information is needed, and what is the current
differential diagnosis?
```

### 7. Continue the Case

Provide requested findings until the server can refine the differential and recommend a next step.

---

## Example Knowledge-Graph Query

The following Cypher query retrieves diseases associated with a set of symptoms.

```cypher
MATCH (d:Disease)-[:PRESENTS_DpS]-(s:Symptom)
WHERE toLower(s.name) IN $symptom_terms
WITH
    d,
    collect(DISTINCT s.name) AS matched_symptoms,
    count(DISTINCT s) AS matched_count
RETURN
    coalesce(d.identifier, elementId(d)) AS diagnosis_id,
    d.name AS diagnosis_name,
    matched_symptoms,
    matched_count
ORDER BY
    matched_count DESC,
    diagnosis_name
```

Example parameters:

```json
{
  "symptom_terms": [
    "headache",
    "ataxia",
    "hypoxemia",
    "dyspnea"
  ]
}
```

The current implementation may return all matching candidates rather than limiting the differential to a fixed number. The language model can then refine the list using additional patient findings.

---

## Observation Mapping

Patient-state fields do not always use the same terminology as the knowledge graph.

For example:

```text
coordination = impaired
```

may need to be translated into:

```text
ataxia
```

Similarly:

```text
spo2 = 86
```

may be represented in the graph as:

```text
hypoxemia
```

These mappings should be stored in a reusable configuration file rather than embedded directly into a single scenario.

Example:

```json
{
  "headache": ["headache"],
  "coordination": ["ataxia"],
  "spo2": ["hypoxemia"],
  "shortness_of_breath": ["dyspnea"],
  "lung_auscultation": [
    "pulmonary crackles",
    "crackles"
  ]
}
```

The mapping file can be expanded as new scenarios and observation types are added.

---

## Evaluation

The prototype is intended to be evaluated using physician-documented clinical cases and simulated emergency scenarios.

Potential evaluation metrics include:

* Final diagnosis ranked in the top 1, top 3, or top 5
* Differential-diagnosis recall
* Treatment recommendation alignment
* Stage-appropriate action selection
* Identification of missing clinical information
* Recognition of unavailable diagnostic or treatment resources
* Knowledge-graph evidence traceability
* Number of clarification steps
* Time or tool calls required to reach a diagnosis

A potential comparison design is:

```text
General LLM alone
        versus
LLM connected to the CDSS MCP server and knowledge graph
```

---

## Limitations

This project is an early research prototype.

Current limitations may include:

* Incomplete knowledge-graph coverage
* Missing links between diseases, treatments, actions, and medical-kit resources
* Dependence on manually curated observation mappings
* Variation in language-model tool-selection behavior
* Limited scenario coverage
* No validation for real-world clinical use
* Possible retrieval of broad or weakly matched differential diagnoses
* Dependence on the accuracy of source knowledge graphs and scenario files
* Limited handling of uncertainty, contraindications, dosing, and patient-specific treatment risk

A recommendation should not be considered clinically valid solely because it was generated by the server or retrieved from the knowledge graph.

---

## Safety Disclaimer

This software is for research, demonstration, and educational purposes only.

It is not a medical device and has not been validated for clinical care, emergency response, diagnosis, treatment selection, medication administration, or medical-kit planning.

Do not use this software to make decisions about an actual patient.

All outputs should be reviewed by appropriately qualified medical professionals and evaluated against authoritative clinical guidance.

---

## Future Work

Planned development may include:

* Expanding the ExMC knowledge graph with additional symptom, disease, treatment, and phenotype relationships
* Adding retrieval-augmented generation for guidelines, journal articles, medication references, device manuals, and mission-specific medical resources
* Improving terminology normalization and ontology mapping
* Developing specialized clinical-reasoning agents
* Adding evidence citations and explanation paths
* Improving resource-gap detection
* Supporting additional simulated medical emergencies
* Developing a user-friendly web interface
* Comparing multiple language models and knowledge-graph configurations
* Incorporating feedback from aerospace medicine and clinical experts
* Evaluating the system using standardized case-study benchmarks

---

## Research Context

This project investigates the use of knowledge graphs and Model Context Protocol servers for clinical decision support during deep-space missions.

The broader goal is to improve:

* Medical autonomy
* Emergency preparedness
* Clinical reasoning consistency
* Explainability
* Resource awareness
* Medical-kit planning
* Decision support in remote environments

Although the motivating use case is astronaut healthcare, the architecture may also be relevant to wilderness medicine, military medicine, disaster response, rural care, and other settings with limited access to specialists or medical resources.

---

## Contributing

This repository is currently maintained as a research and demonstration project.

For proposed changes:

1. Create a new branch.
2. Make and test the changes.
3. Document any new tools, scenarios, mappings, or database requirements.
4. Submit a pull request with a description of the change.

Please avoid committing:

* Patient-identifiable information
* Private credentials
* Neo4j passwords
* Restricted datasets
* Hidden scenario answers
* Proprietary medical content without permission

---

## Acknowledgments

This project was developed through a UC Berkeley CITRIS internship in collaboration with NASA.

Special thanks to Dr. Walter Alvarado and Dr. Amanda Saravia-Butler for their mentorship, and to Dr. Charlotte Nelson, whose knowledge-graph data and Python resources provided an important foundation for this work.

---

## License

Add the appropriate license for the repository.

For example:

```text
MIT License
```

or:

```text
Research use only. All rights reserved.
```

Confirm that the selected license is compatible with the licenses and usage restrictions of all included datasets, knowledge graphs, and external code.

---

## Contact

For questions about this research project, contact:

**Tiffany Hoang**
tiffhoang04@gmail.com
