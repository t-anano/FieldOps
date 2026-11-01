# FIELDOPS
### Operational Intelligence & Emergency Resource Allocation

**FieldOps** is a synthetic-data operational coordination prototype built with Python and Streamlit. It demonstrates how an operator can evaluate incidents, rank eligible response resources, approve assignments, manage active operations, and audit decisions.

> **Disclaimer:** FieldOps is an educational prototype using synthetic data. It is not designed, validated, or authorized for live emergency dispatch.

## Problem

Emergency response coordination involves competing priorities, limited resources, geographic constraints, and changing operational conditions.

FieldOps explores a decision-support workflow that makes resource eligibility, ranking criteria, operator approvals, and subsequent operational changes visible.

## Core capabilities

- **Incident monitoring:** Regional incident map, priority queue, and incident registry.
- **Resource intelligence:** Eligibility filtering and ranked resource recommendations.
- **Configurable decision model:** Adjustable proximity, compatibility, and capacity weights.
- **Sensitivity analysis:** Compare rankings under alternative weighting scenarios.
- **Human-in-the-loop approval:** An operator reviews and approves recommended assignments.
- **Operational lifecycle:** Track incidents from OPEN through ASSIGNED and IN PROGRESS to RESOLVED.
- **Conflict management:** Prevent assignment of unavailable or already-deployed resources.
- **Resource reassignment:** Transfer an active incident to another eligible resource.
- **Audit history:** Record assignment decisions, status transitions, reassignment, and resolution.
- **CSV export:** Export operational event history.

## Technology

- Python
- Streamlit
- Pandas
- NumPy
- PyDeck

## Decision model

The prototype applies eligibility gates before ranking resources.

A resource must:
1. Have a compatible resource type.
2. Have an original status of Available.
3. Not already be deployed.

Eligible resources are scored using a configurable weighted model:

`Total Score = Proximity Contribution + Compatibility Contribution + Capacity Contribution`

The default weighting is:

| Criterion | Weight |
|---|---:|
| Proximity | 60% |
| Compatibility | 25% |
| Capacity | 15% |

The model uses Haversine straight-line distance. It does not calculate road travel time or validate real-world emergency response suitability.

## Run locally

Clone the repository and enter the project directory.

```bash
cd FieldOps
```

Create and activate a virtual environment:

```bash
python -m venv .venv
```

Windows PowerShell:

```powershell
.\.venv\Scripts\Activate.ps1
```

Install dependencies:

```bash
pip install streamlit pandas numpy pydeck
```

Launch:

```bash
streamlit run app.py
```

## Demonstration workflow

1. Select an open incident in Command Center.
2. Review eligible resource candidates and their scores.
3. Adjust decision weights and compare sensitivity scenarios.
4. Approve an assignment.
5. Open Operations and advance the incident to IN PROGRESS.
6. Reassign the resource and inspect the audit history.
7. Resolve the incident and verify that the resource returns to availability.
8. Export the operational event history.

## Architecture and limitations

This is a prototype, not a production dispatch system.

- Incident and resource records are synthetic.
- Application state is maintained in Streamlit session state and resets when the session is restarted.
- Audit events are not persisted to a database or protected against tampering.
- Resource scoring is a heuristic, not a validated optimization model.
- Geographic distance is straight-line, not road-network distance or ETA.
- No live emergency service integrations are present.

## Project direction

Future development could explore persistent storage, authenticated operator roles, geospatial routing, scenario simulation, automated testing, and more advanced resource optimization.

---

**FieldOps | Operational Intelligence Prototype | v1.0**