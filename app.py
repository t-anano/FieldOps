
import streamlit as st
import pandas as pd
import numpy as np
import pydeck as pdk
from datetime import datetime

# ============================================================
# FIELDOPS | OPERATIONAL INTELLIGENCE PLATFORM
# Prototype v0.5 — Operational Lifecycle & Conflict Management
# SYNTHETIC DATA ONLY — NOT FOR LIVE EMERGENCY DISPATCH
# ============================================================

st.set_page_config(
    page_title="FIELDOPS | Command",
    page_icon="◈",
    layout="wide",
    initial_sidebar_state="expanded"
)

# -------------------- DESIGN SYSTEM -------------------------

st.markdown("""
<style>
@import url('https://fonts.googleapis.com/css2?family=DM+Mono:wght@400;500&family=Inter:wght@400;500;600;700;800&display=swap');
html, body, [class*="css"] { font-family: 'Inter', sans-serif; }
.stApp { background: #080D17; }
section[data-testid="stSidebar"] {
    background: #0D1421;
    border-right: 1px solid #243044;
}
div[data-testid="stMetric"] {
    background: #111B2B;
    border: 1px solid #26364B;
    padding: 17px;
    border-radius: 8px;
}
div[data-testid="stMetricLabel"] {
    color: #91A3BA;
    font-family: 'DM Mono', monospace;
    font-size: 11px;
    letter-spacing: 1px;
}
div[data-testid="stMetricValue"] { color: #F1F5F9; }
h1, h2, h3 { letter-spacing: -0.7px; }
p, label { color: #C5D0DF; }
div[data-testid="stDataFrame"] {
    border: 1px solid #26364B;
    border-radius: 8px;
}
div.stButton > button {
    background: #0891B2;
    color: white;
    border: none;
    border-radius: 5px;
    font-weight: 700;
    min-height: 42px;
}
div.stButton > button:hover {
    background: #06B6D4;
    color: white;
}
.field-label {
    color: #22D3EE;
    font-family: 'DM Mono', monospace;
    font-size: 11px;
    letter-spacing: 1.5px;
    margin-bottom: 8px;
}
.panel {
    background: #111B2B;
    border: 1px solid #26364B;
    border-radius: 8px;
    padding: 17px;
    margin-bottom: 10px;
}
.muted { color: #91A3BA; font-size: 12px; }
</style>
""", unsafe_allow_html=True)


# -------------------- SYNTHETIC DATA ------------------------

@st.cache_data
def generate_data():
    rng = np.random.default_rng(42)

    center_lat = 35.2271
    center_lon = -80.8431

    incident_types = [
        "Medical Emergency", "Structure Fire", "Flooding",
        "Traffic Accident", "Search and Rescue",
        "Medical Emergency", "Structure Fire", "Flooding",
        "Medical Emergency", "Traffic Accident",
        "Search and Rescue", "Medical Emergency"
    ]

    severities = [
        "Critical", "High", "Medium", "Low",
        "Critical", "High", "Medium", "High",
        "Critical", "Medium", "Low", "High"
    ]

    incidents = []

    for i, (kind, severity) in enumerate(
        zip(incident_types, severities), 1
    ):
        incidents.append({
            "incident_id": f"INC-{i:03}",
            "incident_type": kind,
            "severity": severity,
            "latitude": center_lat + rng.uniform(-0.065, 0.065),
            "longitude": center_lon + rng.uniform(-0.065, 0.065),
            "people_affected": int(rng.integers(1, 30))
        })

    resource_types = [
        "Ambulance", "Ambulance", "Ambulance",
        "Fire Engine", "Fire Engine",
        "Rescue Vehicle", "Rescue Vehicle",
        "Supply Truck", "Supply Truck",
        "Ambulance", "Fire Engine", "Rescue Vehicle"
    ]

    statuses = [
        "Available", "Available", "Busy",
        "Available", "Busy", "Available",
        "Available", "Available", "Busy",
        "Available", "Available", "Busy"
    ]

    resources = []

    for i, (kind, status) in enumerate(
        zip(resource_types, statuses), 1
    ):
        resources.append({
            "resource_id": f"RES-{i:03}",
            "resource_type": kind,
            "latitude": center_lat + rng.uniform(-0.065, 0.065),
            "longitude": center_lon + rng.uniform(-0.065, 0.065),
            "status": status,
            "capacity": int(rng.integers(2, 12))
        })

    return pd.DataFrame(incidents), pd.DataFrame(resources)


incidents_df, resources_df = generate_data()


# -------------------- SESSION STATE -------------------------

defaults = {
    "assignments": [],
    "events": [],
    "deployed_resources": set(),
    "assigned_incidents": {},
    "incident_status": {},
    "weight_proximity": 60,
    "weight_compatibility": 25,
    "weight_capacity": 15
}

for key, value in defaults.items():
    if key not in st.session_state:
        st.session_state[key] = (
            value.copy()
            if isinstance(value, (list, dict, set))
            else value
        )

# Initialize each incident exactly once.
for incident_id in incidents_df["incident_id"]:
    if incident_id not in st.session_state.incident_status:
        st.session_state.incident_status[incident_id] = "OPEN"


# -------------------- CONSTANTS -----------------------------

COMPATIBILITY = {
    "Medical Emergency": ["Ambulance"],
    "Structure Fire": ["Fire Engine"],
    "Flooding": ["Rescue Vehicle", "Supply Truck"],
    "Traffic Accident": ["Ambulance", "Rescue Vehicle"],
    "Search and Rescue": ["Rescue Vehicle"]
}

SEVERITY_RANK = {
    "Critical": 4,
    "High": 3,
    "Medium": 2,
    "Low": 1
}

VALID_STATUSES = [
    "OPEN", "ASSIGNED", "IN PROGRESS", "RESOLVED"
]


# -------------------- EVENT / AUDIT ENGINE -----------------

def timestamp_now():
    return datetime.now().strftime("%Y-%m-%d %H:%M:%S")


def record_event(
    event_type,
    incident_id,
    resource_id=None,
    details=""
):
    """Append an immutable-style operational event record."""

    st.session_state.events.append({
        "timestamp": timestamp_now(),
        "event_type": event_type,
        "incident_id": incident_id,
        "resource_id": resource_id or "N/A",
        "details": details
    })


def get_incident(incident_id):
    rows = incidents_df[
        incidents_df["incident_id"] == incident_id
    ]

    if rows.empty:
        return None

    return rows.iloc[0]


def get_resource(resource_id):
    rows = resources_df[
        resources_df["resource_id"] == resource_id
    ]

    if rows.empty:
        return None

    return rows.iloc[0]


def resource_is_available(resource_id):
    """A resource must be originally available and not deployed."""

    resource = get_resource(resource_id)

    return (
        resource is not None
        and resource["status"] == "Available"
        and resource_id not in st.session_state.deployed_resources
    )


def incident_has_active_assignment(incident_id):
    return incident_id in st.session_state.assigned_incidents


def release_resource(resource_id):
    """Release a deployed resource back to its original available pool."""

    st.session_state.deployed_resources.discard(resource_id)


def set_incident_status(incident_id, new_status):
    """Validate and record an incident status transition."""

    current = st.session_state.incident_status[incident_id]

    allowed_transitions = {
        "OPEN": ["ASSIGNED"],
        "ASSIGNED": ["IN PROGRESS"],
        "IN PROGRESS": ["RESOLVED"],
        "RESOLVED": []
    }

    if new_status not in allowed_transitions[current]:
        return False

    st.session_state.incident_status[incident_id] = new_status

    record_event(
        event_type="STATUS CHANGE",
        incident_id=incident_id,
        resource_id=st.session_state.assigned_incidents.get(
            incident_id
        ),
        details=f"{current} → {new_status}"
    )

    return True


# -------------------- DECISION ENGINE -----------------------

def calculate_distance(lat1, lon1, lat2, lon2):
    """Return Haversine straight-line distance in kilometers."""

    earth_radius = 6371.0

    lat1, lon1, lat2, lon2 = np.radians(
        [lat1, lon1, lat2, lon2]
    )

    dlat = lat2 - lat1
    dlon = lon2 - lon1

    a = (
        np.sin(dlat / 2) ** 2
        + np.cos(lat1) * np.cos(lat2)
        * np.sin(dlon / 2) ** 2
    )

    return float(
        2 * earth_radius * np.arcsin(np.sqrt(a))
    )


def validate_weights(proximity, compatibility, capacity):
    values = [proximity, compatibility, capacity]

    return (
        all(value >= 0 for value in values)
        and sum(values) == 100
    )


def rank_resources(incident, weights, limit=3):
    """
    Eligibility gates:
    - Compatible resource type
    - Original resource status is Available
    - Resource is not currently deployed

    Eligible resources are ranked using weighted components.
    """

    w_prox, w_compat, w_capacity = weights

    eligible_types = COMPATIBILITY.get(
        incident["incident_type"], []
    )

    candidates = resources_df[
        resources_df["resource_type"].isin(eligible_types)
        & (resources_df["status"] == "Available")
        & (
            ~resources_df["resource_id"].isin(
                st.session_state.deployed_resources
            )
        )
    ].copy()

    if candidates.empty:
        for col in [
            "distance_km",
            "proximity_component",
            "compatibility_component",
            "capacity_component",
            "proximity_score",
            "compatibility_score",
            "capacity_score",
            "total_score",
            "rationale"
        ]:
            candidates[col] = pd.Series(
                dtype=str if col == "rationale" else float
            )

        return candidates

    candidates["distance_km"] = candidates.apply(
        lambda row: calculate_distance(
            incident["latitude"],
            incident["longitude"],
            row["latitude"],
            row["longitude"]
        ),
        axis=1
    )

    max_distance = max(
        float(candidates["distance_km"].max()),
        0.01
    )

    max_capacity = max(
        float(candidates["capacity"].max()),
        1.0
    )

    candidates["proximity_component"] = (
        100 * (
            1 - candidates["distance_km"] / max_distance
        )
    ).clip(0, 100)

    candidates["compatibility_component"] = 100.0

    candidates["capacity_component"] = (
        100 * candidates["capacity"] / max_capacity
    ).clip(0, 100)

    candidates["proximity_score"] = (
        candidates["proximity_component"] * w_prox / 100
    )

    candidates["compatibility_score"] = (
        candidates["compatibility_component"] * w_compat / 100
    )

    candidates["capacity_score"] = (
        candidates["capacity_component"] * w_capacity / 100
    )

    candidates["total_score"] = (
        candidates["proximity_score"]
        + candidates["compatibility_score"]
        + candidates["capacity_score"]
    ).round(1)

    candidates["rationale"] = candidates.apply(
        lambda row: (
            f"{row['resource_type']} passes eligibility; "
            f"{row['distance_km']:.2f} km straight-line distance; "
            f"capacity {int(row['capacity'])}; "
            f"score {row['total_score']:.1f}/100."
        ),
        axis=1
    )

    return candidates.sort_values(
        ["total_score", "distance_km"],
        ascending=[False, True]
    ).head(limit).reset_index(drop=True)


# -------------------- ASSIGNMENT ENGINE ---------------------

def approve_assignment(incident_id, resource_id, weights):
    """Validate and commit a new incident-resource assignment."""

    incident = get_incident(incident_id)

    if incident is None:
        return False, "Incident not found."

    if st.session_state.incident_status[incident_id] != "OPEN":
        return False, "Incident is not open for a new assignment."

    if incident_has_active_assignment(incident_id):
        return False, "Incident already has an active assignment."

    if not resource_is_available(resource_id):
        return False, "Resource is unavailable or already deployed."

    current_ranked = rank_resources(
        incident, weights, limit=3
    )

    if resource_id not in current_ranked["resource_id"].tolist():
        return False, "Resource failed the current eligibility or ranking check."

    candidate = current_ranked[
        current_ranked["resource_id"] == resource_id
    ].iloc[0]

    rank = int(
        current_ranked.index[
            current_ranked["resource_id"] == resource_id
        ][0] + 1
    )

    assignment = {
        "timestamp": timestamp_now(),
        "incident_id": incident_id,
        "incident_type": incident["incident_type"],
        "severity": incident["severity"],
        "resource_id": resource_id,
        "resource_type": candidate["resource_type"],
        "distance_km": round(float(candidate["distance_km"]), 2),
        "decision_score": float(candidate["total_score"]),
        "rank_at_approval": rank,
        "weight_proximity": weights[0],
        "weight_compatibility": weights[1],
        "weight_capacity": weights[2],
        "proximity_contribution": round(
            float(candidate["proximity_score"]), 1
        ),
        "compatibility_contribution": round(
            float(candidate["compatibility_score"]), 1
        ),
        "capacity_contribution": round(
            float(candidate["capacity_score"]), 1
        ),
        "decision": "APPROVED"
    }

    st.session_state.assignments.append(assignment)
    st.session_state.deployed_resources.add(resource_id)
    st.session_state.assigned_incidents[incident_id] = resource_id

    set_incident_status(incident_id, "ASSIGNED")

    record_event(
        "RESOURCE ASSIGNED",
        incident_id,
        resource_id,
        f"Initial assignment approved. Score: {candidate['total_score']:.1f}/100."
    )

    return True, "Assignment approved and recorded."


def reassign_resource(incident_id, new_resource_id, weights):
    """Transfer an active incident to a different eligible resource."""

    if incident_id not in st.session_state.assigned_incidents:
        return False, "Incident has no active assignment."

    current_status = st.session_state.incident_status[incident_id]

    if current_status not in ["ASSIGNED", "IN PROGRESS"]:
        return False, "Only active incidents can be reassigned."

    old_resource_id = st.session_state.assigned_incidents[incident_id]

    if old_resource_id == new_resource_id:
        return False, "Choose a different resource."

    if not resource_is_available(new_resource_id):
        return False, "Replacement resource is unavailable or deployed."

    incident = get_incident(incident_id)

    current_ranked = rank_resources(
        incident, weights, limit=3
    )

    if new_resource_id not in current_ranked["resource_id"].tolist():
        return False, "Replacement resource failed the eligibility check."

    candidate = current_ranked[
        current_ranked["resource_id"] == new_resource_id
    ].iloc[0]

    # Commit only after all validation succeeds.
    release_resource(old_resource_id)

    st.session_state.deployed_resources.add(new_resource_id)

    st.session_state.assigned_incidents[
        incident_id
    ] = new_resource_id

    st.session_state.assignments.append({
        "timestamp": timestamp_now(),
        "incident_id": incident_id,
        "incident_type": incident["incident_type"],
        "severity": incident["severity"],
        "resource_id": new_resource_id,
        "resource_type": candidate["resource_type"],
        "distance_km": round(float(candidate["distance_km"]), 2),
        "decision_score": float(candidate["total_score"]),
        "rank_at_approval": int(
            current_ranked.index[
                current_ranked["resource_id"] == new_resource_id
            ][0] + 1
        ),
        "weight_proximity": weights[0],
        "weight_compatibility": weights[1],
        "weight_capacity": weights[2],
        "proximity_contribution": round(
            float(candidate["proximity_score"]), 1
        ),
        "compatibility_contribution": round(
            float(candidate["compatibility_score"]), 1
        ),
        "capacity_contribution": round(
            float(candidate["capacity_score"]), 1
        ),
        "decision": "REASSIGNED"
    })

    record_event(
        "RESOURCE REASSIGNED",
        incident_id,
        new_resource_id,
        f"Previous resource {old_resource_id} released; "
        f"replacement resource {new_resource_id} assigned."
    )

    return True, (
        f"Resource transferred from {old_resource_id} "
        f"to {new_resource_id}."
    )


def resolve_incident(incident_id):
    """Resolve an incident and release its active resource."""

    if st.session_state.incident_status[incident_id] != "IN PROGRESS":
        return False, "Incident must be IN PROGRESS before resolution."

    if incident_id not in st.session_state.assigned_incidents:
        return False, "No active resource assignment exists."

    resource_id = st.session_state.assigned_incidents[incident_id]

    if not set_incident_status(incident_id, "RESOLVED"):
        return False, "Invalid incident status transition."

    del st.session_state.assigned_incidents[incident_id]

    release_resource(resource_id)

    record_event(
        "INCIDENT RESOLVED",
        incident_id,
        resource_id,
        "Incident resolved. Resource released back to available pool."
    )

    return True, f"{incident_id} resolved. {resource_id} released."


# -------------------- SIDEBAR / NAVIGATION ------------------

with st.sidebar:

    st.markdown(
        "<h2 style='color:#22D3EE; margin-bottom:0;'>◈ FIELDOPS</h2>",
        unsafe_allow_html=True
    )

    st.caption("OPERATIONAL INTELLIGENCE")
    st.divider()

    page = st.radio(
        "NAVIGATION",
        [
            "Command Center",
            "Operations",
            "Incident Registry",
            "Resource Registry",
            "Decision Log"
        ]
    )

    st.divider()

    st.markdown(
        "<div class='field-label'>OPERATIONAL REGION</div>",
        unsafe_allow_html=True
    )

    st.write("Charlotte, North Carolina")
    st.caption("SIMULATION ENVIRONMENT")

    st.divider()

    st.markdown(
        "<div class='field-label'>MAP DISPLAY CONTROLS</div>",
        unsafe_allow_html=True
    )

    show_incidents = st.checkbox(
        "Show incident locations", value=True
    )

    show_resources = st.checkbox(
        "Show available resources", value=True
    )

    show_assigned = st.checkbox(
        "Show assigned incidents", value=True
    )

    critical_only = st.checkbox(
        "Critical incidents only", value=False
    )

    all_severities = ["Critical", "High", "Medium", "Low"]

    selected_severities = st.multiselect(
        "Incident severity",
        all_severities,
        default=all_severities
    )

    all_types = sorted(incidents_df["incident_type"].unique())

    selected_types = st.multiselect(
        "Incident categories",
        all_types,
        default=all_types
    )

    resource_filter = st.selectbox(
        "Resource availability",
        ["All", "Available only", "Busy only"]
    )

    st.divider()

    st.markdown(
        "<div class='field-label'>DECISION MODEL / WEIGHTS</div>",
        unsafe_allow_html=True
    )

    st.caption(
        "Adjust priorities. All three weights must total 100."
    )

    weight_proximity = st.slider(
        "Proximity weight",
        0, 100, int(st.session_state.weight_proximity), 5
    )

    weight_compatibility = st.slider(
        "Compatibility weight",
        0, 100, int(st.session_state.weight_compatibility), 5
    )

    weight_capacity = st.slider(
        "Capacity weight",
        0, 100, int(st.session_state.weight_capacity), 5
    )

    weight_total = (
        weight_proximity
        + weight_compatibility
        + weight_capacity
    )

    weights_valid = validate_weights(
        weight_proximity,
        weight_compatibility,
        weight_capacity
    )

    if weights_valid:

        st.success(f"WEIGHTS VALID · {weight_total}/100")

        st.session_state.weight_proximity = weight_proximity
        st.session_state.weight_compatibility = weight_compatibility
        st.session_state.weight_capacity = weight_capacity

    else:

        st.warning(
            f"Weights total {weight_total}. "
            "Adjust them to exactly 100."
        )

    st.divider()

    st.markdown(
        "<div class='field-label'>SYSTEM STATUS</div>",
        unsafe_allow_html=True
    )

    st.success("CORE SYSTEMS ONLINE")
    st.caption("FIELDOPS / PROTOTYPE 0.5")
    st.caption("DATA CLASSIFICATION: SYNTHETIC")


# -------------------- HEADER --------------------------------

st.markdown(
    "<div class='field-label'>FIELDOPS / REGIONAL OPERATIONS / CHARLOTTE</div>",
    unsafe_allow_html=True
)

st.title(page)

st.markdown(
    "<p class='muted'>Emergency response coordination and resource intelligence.</p>",
    unsafe_allow_html=True
)

st.divider()


# -------------------- DERIVED METRICS -----------------------

status_values = st.session_state.incident_status

open_count = sum(
    status == "OPEN" for status in status_values.values()
)

critical_count = sum(
    1
    for _, row in incidents_df.iterrows()
    if row["severity"] == "Critical"
    and status_values[row["incident_id"]] != "RESOLVED"
)

available_count = sum(
    resource_is_available(resource_id)
    for resource_id in resources_df["resource_id"]
)

active_count = len(st.session_state.assigned_incidents)

resolved_count = sum(
    status == "RESOLVED" for status in status_values.values()
)

assigned_count = len(st.session_state.assignments)

weights = (
    weight_proximity,
    weight_compatibility,
    weight_capacity
)


# -------------------- FILTERED MAP DATA ---------------------

map_incidents = incidents_df.copy()

map_incidents["status"] = map_incidents["incident_id"].map(
    st.session_state.incident_status
)

if not show_assigned:
    map_incidents = map_incidents[
        map_incidents["status"] == "OPEN"
    ]

map_incidents = map_incidents[
    map_incidents["severity"].isin(selected_severities)
    & map_incidents["incident_type"].isin(selected_types)
]

if critical_only:
    map_incidents = map_incidents[
        map_incidents["severity"] == "Critical"
    ]

map_incidents["r"] = map_incidents["severity"].map({
    "Critical": 248,
    "High": 249,
    "Medium": 250,
    "Low": 100
})

map_incidents["g"] = map_incidents["severity"].map({
    "Critical": 113,
    "High": 160,
    "Medium": 204,
    "Low": 116
})

map_incidents["b"] = map_incidents["severity"].map({
    "Critical": 113,
    "High": 60,
    "Medium": 21,
    "Low": 139
})

map_resources = resources_df.copy()

map_resources["operational_status"] = map_resources[
    "resource_id"
].apply(
    lambda resource_id: (
        "DEPLOYED"
        if resource_id in st.session_state.deployed_resources
        else (
            "AVAILABLE"
            if resource_is_available(resource_id)
            else "BUSY"
        )
    )
)

if resource_filter == "Available only":
    map_resources = map_resources[
        map_resources["operational_status"] == "AVAILABLE"
    ]

elif resource_filter == "Busy only":
    map_resources = map_resources[
        map_resources["operational_status"] == "BUSY"
    ]

if not show_assigned:
    map_resources = map_resources[
        map_resources["operational_status"] != "DEPLOYED"
    ]


# -------------------- COMMAND CENTER ------------------------

if page == "Command Center":

    c1, c2, c3, c4, c5 = st.columns(5)

    c1.metric("OPEN INCIDENTS", open_count)
    c2.metric("CRITICAL UNRESOLVED", critical_count)
    c3.metric("AVAILABLE UNITS", available_count)
    c4.metric("ACTIVE ASSIGNMENTS", active_count)
    c5.metric("RESOLVED", resolved_count)

    st.markdown("<br>", unsafe_allow_html=True)

    map_col, intelligence_col = st.columns(
        [2.2, 1], gap="large"
    )

    with map_col:

        st.markdown(
            "<div class='field-label'>01 / REGIONAL SITUATION MAP</div>",
            unsafe_allow_html=True
        )

        layers = []

        if show_incidents and not map_incidents.empty:

            layers.append(
                pdk.Layer(
                    "ScatterplotLayer",
                    id="incident-layer",
                    data=map_incidents,
                    get_position="[longitude, latitude]",
                    get_fill_color="[r, g, b, 220]",
                    get_radius=180,
                    radius_min_pixels=6,
                    radius_max_pixels=15,
                    pickable=True
                )
            )

        if show_resources and not map_resources.empty:

            layers.append(
                pdk.Layer(
                    "ScatterplotLayer",
                    id="resource-layer",
                    data=map_resources,
                    get_position="[longitude, latitude]",
                    get_fill_color="[34, 211, 153, 220]",
                    get_radius=140,
                    radius_min_pixels=6,
                    radius_max_pixels=13,
                    pickable=True
                )
            )

        view = pdk.ViewState(
            latitude=35.2271,
            longitude=-80.8431,
            zoom=10.5,
            pitch=35
        )

        deck = pdk.Deck(
            layers=layers,
            initial_view_state=view,
            map_style=(
                "https://basemaps.cartocdn.com/"
                "gl/dark-matter-gl-style/style.json"
            ),
            tooltip={
                "html": (
                    "<b>{incident_id}</b><br/>"
                    "Type: {incident_type}<br/>"
                    "Severity: {severity}<br/>"
                    "Status: {status}"
                ),
                "style": {
                    "backgroundColor": "#111827",
                    "color": "#F1F5F9"
                }
            }
        )

        st.pydeck_chart(deck, height=440)

        st.caption(
            f"VISIBLE INCIDENTS: "
            f"{len(map_incidents) if show_incidents else 0} | "
            f"VISIBLE RESOURCES: "
            f"{len(map_resources) if show_resources else 0} | "
            "MAP DATA: SYNTHETIC"
        )

    with intelligence_col:

        st.markdown(
            "<div class='field-label'>02 / INCIDENT PRIORITY QUEUE</div>",
            unsafe_allow_html=True
        )

        queue = incidents_df.copy()

        queue["status"] = queue["incident_id"].map(
            st.session_state.incident_status
        )

        queue = queue[
            queue["status"] == "OPEN"
        ]

        queue = queue[
            queue["severity"].isin(selected_severities)
            & queue["incident_type"].isin(selected_types)
        ]

        if critical_only:
            queue = queue[
                queue["severity"] == "Critical"
            ]

        queue["rank"] = queue["severity"].map(SEVERITY_RANK)

        queue = queue.sort_values(
            ["rank", "people_affected"],
            ascending=[False, False]
        )

        if queue.empty:
            st.info("No open incidents match the selected filters.")

        for _, row in queue.head(6).iterrows():

            color = {
                "Critical": "#F87171",
                "High": "#FB923C",
                "Medium": "#FACC15",
                "Low": "#94A3B8"
            }[row["severity"]]

            st.markdown(
                f"""
                <div class="panel">
                    <div style="display:flex;justify-content:space-between;">
                        <b>{row['incident_id']}</b>
                        <span style="color:{color};font-size:11px;">
                            ● {row['severity'].upper()}
                        </span>
                    </div>
                    <div style="color:#CBD5E1;margin-top:8px;">
                        {row['incident_type']}
                    </div>
                    <div class="muted">
                        {row['people_affected']} people affected
                    </div>
                </div>
                """,
                unsafe_allow_html=True
            )

    # Allocation workbench

    st.divider()

    st.markdown(
        "<div class='field-label'>03 / RESOURCE ALLOCATION WORKBENCH</div>",
        unsafe_allow_html=True
    )

    available_incidents = incidents_df[
        incidents_df["incident_id"].apply(
            lambda incident_id:
            st.session_state.incident_status[incident_id] == "OPEN"
        )
    ].copy()

    available_incidents = available_incidents[
        available_incidents["severity"].isin(selected_severities)
        & available_incidents["incident_type"].isin(selected_types)
    ]

    if critical_only:
        available_incidents = available_incidents[
            available_incidents["severity"] == "Critical"
        ]

    if not available_incidents.empty:

        available_incidents["priority_rank"] = (
            available_incidents["severity"].map(SEVERITY_RANK)
        )

        available_incidents = available_incidents.sort_values(
            ["priority_rank", "people_affected"],
            ascending=[False, False]
        )

        incident_options = available_incidents["incident_id"].tolist()

        selected_id = st.selectbox(
            "Select an incident for resource evaluation",
            incident_options,
            key="allocation_incident"
        )

        incident = get_incident(selected_id)

        profile_cols = st.columns(4)

        profile_cols[0].metric("INCIDENT", incident["incident_id"])
        profile_cols[1].metric("SEVERITY", incident["severity"])
        profile_cols[2].metric(
            "PEOPLE AFFECTED",
            int(incident["people_affected"])
        )

        if not weights_valid:

            profile_cols[3].metric("WEIGHTS", f"{weight_total}/100")

            st.warning(
                "Candidate ranking is paused until weights total 100."
            )

        else:

            ranked_resources = rank_resources(
                incident, weights, limit=3
            )

            profile_cols[3].metric(
                "ELIGIBLE UNITS", len(ranked_resources)
            )

            st.caption(
                "Eligibility is a hard gate: compatible type, Available "
                "status, and not already deployed. Weights affect ranking "
                "after eligibility is established."
            )

            if not ranked_resources.empty:

                st.markdown("**TOP RESOURCE CANDIDATES**")

                comparison = ranked_resources[
                    [
                        "resource_id",
                        "resource_type",
                        "distance_km",
                        "capacity",
                        "proximity_score",
                        "compatibility_score",
                        "capacity_score",
                        "total_score"
                    ]
                ].copy()

                comparison.columns = [
                    "Resource",
                    "Type",
                    "Distance (km)",
                    "Capacity",
                    "Proximity contribution",
                    "Compatibility contribution",
                    "Capacity contribution",
                    "Total score"
                ]

                comparison["Distance (km)"] = (
                    comparison["Distance (km)"].round(2)
                )

                st.dataframe(
                    comparison,
                    use_container_width=True,
                    hide_index=True
                )

                candidate_labels = [
                    f"{row['resource_id']} — {row['resource_type']} "
                    f"({row['total_score']:.1f}/100)"
                    for _, row in ranked_resources.iterrows()
                ]

                selected_label = st.radio(
                    "Choose a candidate to inspect",
                    candidate_labels,
                    index=0,
                    horizontal=True,
                    key=f"candidate_{selected_id}"
                )

                selected_index = candidate_labels.index(selected_label)
                selected_resource = ranked_resources.iloc[selected_index]

                detail_left, detail_right = st.columns([1.2, 1])

                with detail_left:

                    st.markdown("**WHY THIS RESOURCE?**")

                    st.success(
                        f"{selected_resource['resource_id']} is ranked "
                        f"#{selected_index + 1} of the displayed candidates."
                    )

                    st.write(
                        f"- **Eligibility:** {selected_resource['resource_type']} "
                        "is compatible and available."
                    )

                    st.write(
                        f"- **Proximity:** "
                        f"{selected_resource['distance_km']:.2f} km "
                        "straight-line distance."
                    )

                    st.write(
                        f"- **Capacity:** "
                        f"{int(selected_resource['capacity'])} "
                        "synthetic capacity units."
                    )

                    st.write(
                        f"- **Weighted result:** "
                        f"{selected_resource['total_score']:.1f}/100."
                    )

                with detail_right:

                    st.markdown("**WEIGHTED SCORE BREAKDOWN**")

                    st.progress(
                        min(
                            float(selected_resource["total_score"]) / 100,
                            1.0
                        ),
                        text=(
                            f"Total score: "
                            f"{selected_resource['total_score']:.1f}/100"
                        )
                    )

                    st.write(
                        f"Proximity: **{selected_resource['proximity_score']:.1f}**"
                    )

                    st.write(
                        f"Compatibility: "
                        f"**{selected_resource['compatibility_score']:.1f}**"
                    )

                    st.write(
                        f"Capacity: **{selected_resource['capacity_score']:.1f}**"
                    )

                with st.expander("SENSITIVITY ANALYSIS"):

                    scenarios = [
                        ("Current settings", weights),
                        ("Proximity emphasis", (80, 10, 10)),
                        ("Capacity emphasis", (30, 20, 50))
                    ]

                    scenario_rows = []

                    for scenario_name, scenario_weights in scenarios:

                        scenario_ranked = rank_resources(
                            incident,
                            scenario_weights,
                            limit=3
                        )

                        for scenario_rank, (_, row) in enumerate(
                            scenario_ranked.iterrows(), 1
                        ):
                            scenario_rows.append({
                                "Scenario": scenario_name,
                                "Rank": scenario_rank,
                                "Resource": row["resource_id"],
                                "Score": row["total_score"]
                            })

                    if scenario_rows:
                        st.dataframe(
                            pd.DataFrame(scenario_rows),
                            use_container_width=True,
                            hide_index=True
                        )

                if st.button(
                    "APPROVE & RECORD ASSIGNMENT",
                    use_container_width=True
                ):

                    success, message = approve_assignment(
                        selected_id,
                        selected_resource["resource_id"],
                        weights
                    )

                    if success:
                        st.success(message)
                        st.rerun()
                    else:
                        st.error(message)

            else:
                st.warning(
                    "No eligible available resource found. "
                    "Coordinator intervention required."
                )

    else:
        st.info("No open incidents match the selected filters.")


# -------------------- OPERATIONS ----------------------------

elif page == "Operations":

    st.markdown(
        "<div class='field-label'>04 / OPERATIONAL LIFECYCLE MANAGEMENT</div>",
        unsafe_allow_html=True
    )

    st.subheader("Active Incident Operations")

    st.caption(
        "Manage active assignments, progress incidents, reassign resources, "
        "and resolve completed operations."
    )

    active_incidents = list(
        st.session_state.assigned_incidents.keys()
    )

    if not active_incidents:

        st.info(
            "No active assignments. Approve an assignment in the "
            "Command Center to begin an operation."
        )

    else:

        active_rows = []

        for incident_id in active_incidents:

            incident = get_incident(incident_id)
            resource_id = st.session_state.assigned_incidents[incident_id]
            resource = get_resource(resource_id)

            active_rows.append({
                "Incident": incident_id,
                "Type": incident["incident_type"],
                "Severity": incident["severity"],
                "Resource": resource_id,
                "Resource type": resource["resource_type"],
                "Status": st.session_state.incident_status[incident_id]
            })

        st.dataframe(
            pd.DataFrame(active_rows),
            use_container_width=True,
            hide_index=True
        )

        st.divider()

        selected_operation = st.selectbox(
            "Select an active operation",
            active_incidents,
            key="operation_selection"
        )

        operation_status = st.session_state.incident_status[
            selected_operation
        ]

        current_resource_id = st.session_state.assigned_incidents[
            selected_operation
        ]

        operation = get_incident(selected_operation)

        left, right = st.columns(2)

        with left:

            st.markdown("**CURRENT OPERATION**")

            st.metric("INCIDENT", selected_operation)
            st.metric("CURRENT STATUS", operation_status)
            st.metric("ASSIGNED RESOURCE", current_resource_id)

            st.write(f"Incident type: {operation['incident_type']}")
            st.write(f"Severity: {operation['severity']}")
            st.write(
                f"People affected: {int(operation['people_affected'])}"
            )

        with right:

            st.markdown("**LIFECYCLE CONTROLS**")

            if operation_status == "ASSIGNED":

                if st.button(
                    "MARK INCIDENT IN PROGRESS",
                    use_container_width=True
                ):

                    success = set_incident_status(
                        selected_operation,
                        "IN PROGRESS"
                    )

                    if success:
                        st.success("Incident moved to IN PROGRESS.")
                        st.rerun()
                    else:
                        st.error("Status transition rejected.")

            elif operation_status == "IN PROGRESS":

                st.info("This incident is actively being handled.")

                if st.button(
                    "RESOLVE INCIDENT & RELEASE RESOURCE",
                    use_container_width=True
                ):

                    success, message = resolve_incident(
                        selected_operation
                    )

                    if success:
                        st.success(message)
                        st.rerun()
                    else:
                        st.error(message)

            st.divider()

            st.markdown("**RESOURCE REASSIGNMENT**")

            st.caption(
                "The replacement must pass the compatibility, availability, "
                "and deployment eligibility checks."
            )

            replacement_candidates = rank_resources(
                operation,
                weights,
                limit=12
            ) if weights_valid else pd.DataFrame()

            if not weights_valid:

                st.warning(
                    "Valid decision weights are required for reassignment."
                )

            elif replacement_candidates.empty:

                st.warning(
                    "No eligible replacement resources are available."
                )

            else:

                replacement_options = (
                    replacement_candidates["resource_id"].tolist()
                )

                replacement_id = st.selectbox(
                    "Select replacement resource",
                    replacement_options,
                    key=f"replacement_{selected_operation}"
                )

                replacement = replacement_candidates[
                    replacement_candidates["resource_id"] == replacement_id
                ].iloc[0]

                st.caption(
                    f"{replacement['resource_type']} · "
                    f"{replacement['distance_km']:.2f} km · "
                    f"Score {replacement['total_score']:.1f}/100"
                )

                if st.button(
                    "CONFIRM RESOURCE REASSIGNMENT",
                    use_container_width=True
                ):

                    success, message = reassign_resource(
                        selected_operation,
                        replacement_id,
                        weights
                    )

                    if success:
                        st.success(message)
                        st.rerun()
                    else:
                        st.error(message)

    # Resolved operations

    st.divider()

    st.markdown("**RESOLVED INCIDENTS**")

    resolved_ids = [
        incident_id
        for incident_id, status in st.session_state.incident_status.items()
        if status == "RESOLVED"
    ]

    if resolved_ids:
        st.dataframe(
            incidents_df[
                incidents_df["incident_id"].isin(resolved_ids)
            ][
                [
                    "incident_id",
                    "incident_type",
                    "severity",
                    "people_affected"
                ]
            ],
            use_container_width=True,
            hide_index=True
        )
    else:
        st.caption("No incidents resolved in this session.")


# -------------------- INCIDENT REGISTRY ---------------------

elif page == "Incident Registry":

    st.subheader("Incident Registry")
    st.caption("REGISTERED EMERGENCY REQUESTS")

    display = incidents_df.copy()

    display["status"] = display["incident_id"].map(
        st.session_state.incident_status
    )

    display["assigned_resource"] = display["incident_id"].apply(
        lambda incident_id:
        st.session_state.assigned_incidents.get(incident_id, "—")
    )

    display = display[
        display["severity"].isin(selected_severities)
        & display["incident_type"].isin(selected_types)
    ]

    if critical_only:
        display = display[
            display["severity"] == "Critical"
        ]

    if not show_assigned:
        display = display[display["status"] == "OPEN"]

    st.dataframe(
        display,
        use_container_width=True,
        hide_index=True
    )

    status_counts = (
        pd.Series(st.session_state.incident_status)
        .value_counts()
        .reindex(VALID_STATUSES, fill_value=0)
    )

    st.markdown("**INCIDENT LIFECYCLE DISTRIBUTION**")

    st.bar_chart(status_counts)


# -------------------- RESOURCE REGISTRY ---------------------

elif page == "Resource Registry":

    st.subheader("Resource Registry")
    st.caption("RESPONSE RESOURCE STATUS")

    display = resources_df.copy()

    display["operational_status"] = display["resource_id"].apply(
        lambda resource_id: (
            "DEPLOYED"
            if resource_id in st.session_state.deployed_resources
            else (
                "AVAILABLE"
                if resource_is_available(resource_id)
                else "BUSY"
            )
        )
    )

    display["assigned_incident"] = display["resource_id"].apply(
        lambda resource_id: next(
            (
                incident_id
                for incident_id, assigned_resource
                in st.session_state.assigned_incidents.items()
                if assigned_resource == resource_id
            ),
            "—"
        )
    )

    if resource_filter == "Available only":
        display = display[
            display["operational_status"] == "AVAILABLE"
        ]

    elif resource_filter == "Busy only":
        display = display[
            display["operational_status"] == "BUSY"
        ]

    st.dataframe(
        display,
        use_container_width=True,
        hide_index=True
    )

    st.markdown("**RESOURCE AVAILABILITY SUMMARY**")

    resource_summary = (
        display["operational_status"]
        .value_counts()
        .reindex(["AVAILABLE", "DEPLOYED", "BUSY"], fill_value=0)
    )

    st.bar_chart(resource_summary)


# -------------------- DECISION LOG --------------------------

elif page == "Decision Log":

    st.subheader("Decision & Event Audit Log")

    st.caption(
        "Assignment decisions, resource transfers, lifecycle transitions, "
        "and resolution events."
    )

    tab1, tab2 = st.tabs([
        "Assignment Decisions",
        "Operational Event History"
    ])

    with tab1:

        if st.session_state.assignments:

            log = pd.DataFrame(st.session_state.assignments)

            st.dataframe(
                log,
                use_container_width=True,
                hide_index=True
            )

            st.metric(
                "TOTAL ASSIGNMENT DECISIONS",
                len(log)
            )

            st.markdown("**DECISION DETAIL**")

            selected_audit = st.selectbox(
                "Select a decision to inspect",
                log.index.tolist(),
                format_func=lambda i: (
                    f"{log.loc[i, 'incident_id']} → "
                    f"{log.loc[i, 'resource_id']} "
                    f"({log.loc[i, 'decision_score']:.1f}/100)"
                )
            )

            audit = log.loc[selected_audit]

            audit_cols = st.columns(4)

            audit_cols[0].metric(
                "RECORDED RANK",
                int(audit["rank_at_approval"])
            )

            audit_cols[1].metric(
                "PROXIMITY WEIGHT",
                int(audit["weight_proximity"])
            )

            audit_cols[2].metric(
                "COMPATIBILITY WEIGHT",
                int(audit["weight_compatibility"])
            )

            audit_cols[3].metric(
                "CAPACITY WEIGHT",
                int(audit["weight_capacity"])
            )

            st.caption(
                f"Decision: {audit['decision']} · "
                f"Proximity contribution: {audit['proximity_contribution']:.1f} · "
                f"Compatibility contribution: {audit['compatibility_contribution']:.1f} · "
                f"Capacity contribution: {audit['capacity_contribution']:.1f}"
            )

        else:

            st.info("No assignment decisions have been recorded.")

    with tab2:

        if st.session_state.events:

            events_df = pd.DataFrame(
                st.session_state.events
            )

            st.dataframe(
                events_df,
                use_container_width=True,
                hide_index=True
            )

            st.metric(
                "TOTAL OPERATIONAL EVENTS",
                len(events_df)
            )

            st.download_button(
                "EXPORT EVENT HISTORY AS CSV",
                data=events_df.to_csv(index=False).encode("utf-8"),
                file_name="fieldops_event_history.csv",
                mime="text/csv",
                use_container_width=True
            )

        else:

            st.info(
                "No operational events recorded. "
                "Assignments and lifecycle actions will appear here."
            )


# -------------------- FOOTER --------------------------------

st.divider()

st.markdown(
    """
    <div style="display:flex;justify-content:space-between;">
        <span style="color:#64748B;font-size:11px;">
            FIELDOPS / OPERATIONAL INTELLIGENCE
        </span>
        <span style="color:#64748B;font-size:11px;">
            PROTOTYPE 0.5 / SYNTHETIC DATA / LIFECYCLE MANAGEMENT
        </span>
    </div>
    """,
    unsafe_allow_html=True
)
