
import streamlit as st
import pandas as pd
import numpy as np
import pydeck as pdk
from datetime import datetime

# ============================================================
# FIELDOPS | OPERATIONAL INTELLIGENCE PLATFORM
# Prototype v0.3 — Resource Intelligence Engine
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

html, body, [class*="css"] {
    font-family: 'Inter', sans-serif;
}
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
            "people_affected": int(rng.integers(1, 30)),
            "status": "OPEN"
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

if "assignments" not in st.session_state:
    st.session_state.assignments = []

if "deployed_resources" not in st.session_state:
    st.session_state.deployed_resources = set()

if "assigned_incidents" not in st.session_state:
    st.session_state.assigned_incidents = {}


# -------------------- DECISION ENGINE -----------------------

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


def calculate_distance(lat1, lon1, lat2, lon2):
    """Return Haversine straight-line distance in kilometers."""
    earth_radius = 6371

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

    return float(2 * earth_radius * np.arcsin(np.sqrt(a)))


def rank_resources(incident, limit=3):
    """
    Return the top eligible resources ranked by a transparent score.

    Scoring:
      - 60 points: proximity
      - 25 points: resource-type compatibility
      - 15 points: capacity

    Eligibility is a hard gate: only compatible, available,
    non-deployed resources are considered.

    Scores support coordinator judgment; they do not represent
    validated real-world response performance.
    """
    eligible_types = COMPATIBILITY.get(
        incident["incident_type"], []
    )

    candidates = resources_df[
        (resources_df["resource_type"].isin(eligible_types))
        & (resources_df["status"] == "Available")
        & (~resources_df["resource_id"].isin(
            st.session_state.deployed_resources
        ))
    ].copy()

    if candidates.empty:
        return candidates.assign(
            distance_km=pd.Series(dtype=float),
            proximity_score=pd.Series(dtype=float),
            compatibility_score=pd.Series(dtype=float),
            capacity_score=pd.Series(dtype=float),
            total_score=pd.Series(dtype=float),
            rationale=pd.Series(dtype=str)
        )

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
        float(candidates["distance_km"].max()), 0.01
    )
    max_capacity = max(
        float(candidates["capacity"].max()), 1.0
    )

    candidates["proximity_score"] = (
        60 * (1 - candidates["distance_km"] / max_distance)
    ).clip(lower=0, upper=60)

    candidates["compatibility_score"] = 25.0

    candidates["capacity_score"] = (
        15 * candidates["capacity"] / max_capacity
    )

    candidates["total_score"] = (
        candidates["proximity_score"]
        + candidates["compatibility_score"]
        + candidates["capacity_score"]
    ).round(1)

    candidates["rationale"] = candidates.apply(
        lambda row: (
            f"{row['resource_type']} is compatible; "
            f"{row['distance_km']:.2f} km straight-line distance; "
            f"capacity {int(row['capacity'])}."
        ),
        axis=1
    )

    return candidates.sort_values(
        ["total_score", "distance_km"],
        ascending=[False, True]
    ).head(limit).reset_index(drop=True)


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
        "<div class='field-label'>SYSTEM STATUS</div>",
        unsafe_allow_html=True
    )
    st.success("CORE SYSTEMS ONLINE")
    st.caption("FIELDOPS / PROTOTYPE 0.3")
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


# -------------------- FILTERED DATA -------------------------

assigned_ids = set(st.session_state.assigned_incidents.keys())

map_incidents = incidents_df.copy()

if not show_assigned:
    map_incidents = map_incidents[
        ~map_incidents["incident_id"].isin(assigned_ids)
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
    "Critical": 248, "High": 249, "Medium": 250, "Low": 100
})
map_incidents["g"] = map_incidents["severity"].map({
    "Critical": 113, "High": 160, "Medium": 204, "Low": 116
})
map_incidents["b"] = map_incidents["severity"].map({
    "Critical": 113, "High": 60, "Medium": 21, "Low": 139
})

map_resources = resources_df.copy()

if resource_filter == "Available only":
    map_resources = map_resources[
        map_resources["status"] == "Available"
    ]
elif resource_filter == "Busy only":
    map_resources = map_resources[
        map_resources["status"] == "Busy"
    ]

map_resources = map_resources[
    ~map_resources["resource_id"].isin(
        st.session_state.deployed_resources
    )
]


# -------------------- DERIVED METRICS -----------------------

open_count = len(incidents_df) - len(assigned_ids)

critical_count = len(
    incidents_df[
        (incidents_df["severity"] == "Critical")
        & (~incidents_df["incident_id"].isin(assigned_ids))
    ]
)

available_count = len(resources_df[
    (resources_df["status"] == "Available")
    & (~resources_df["resource_id"].isin(
        st.session_state.deployed_resources
    ))
])

assigned_count = len(st.session_state.assignments)


# -------------------- COMMAND CENTER ------------------------

if page == "Command Center":
    c1, c2, c3, c4 = st.columns(4)
    c1.metric("OPEN INCIDENTS", open_count)
    c2.metric("CRITICAL INCIDENTS", critical_count)
    c3.metric("AVAILABLE UNITS", available_count)
    c4.metric("RECORDED ASSIGNMENTS", assigned_count)

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
                    "Resource: {resource_id}"
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
            f"{len(map_incidents) if show_incidents else 0}  |  "
            f"VISIBLE RESOURCES: "
            f"{len(map_resources) if show_resources else 0}  |  "
            "MAP DATA: SYNTHETIC"
        )

    with intelligence_col:
        st.markdown(
            "<div class='field-label'>02 / INCIDENT PRIORITY QUEUE</div>",
            unsafe_allow_html=True
        )

        queue = incidents_df[
            ~incidents_df["incident_id"].isin(assigned_ids)
        ].copy()

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

        for _, incident in queue.head(6).iterrows():
            color = {
                "Critical": "#F87171",
                "High": "#FB923C",
                "Medium": "#FACC15",
                "Low": "#94A3B8"
            }[incident["severity"]]

            st.markdown(
                f"""
                <div class="panel">
                    <div style="display:flex;justify-content:space-between;">
                        <b>{incident['incident_id']}</b>
                        <span style="color:{color};font-size:11px;">
                            ● {incident['severity'].upper()}
                        </span>
                    </div>
                    <div style="color:#CBD5E1;margin-top:8px;">
                        {incident['incident_type']}
                    </div>
                    <div class="muted">
                        {incident['people_affected']} people affected
                    </div>
                </div>
                """,
                unsafe_allow_html=True
            )

    st.divider()
    st.markdown(
        "<div class='field-label'>03 / RESOURCE ALLOCATION WORKBENCH</div>",
        unsafe_allow_html=True
    )

    available_incidents = incidents_df[
        ~incidents_df["incident_id"].isin(assigned_ids)
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
            incident_options
        )

        incident = incidents_df[
            incidents_df["incident_id"] == selected_id
        ].iloc[0]

        ranked_resources = rank_resources(incident, limit=3)

        st.markdown("**INCIDENT PROFILE**")
        profile_cols = st.columns(4)
        profile_cols[0].metric("INCIDENT", incident["incident_id"])
        profile_cols[1].metric("SEVERITY", incident["severity"])
        profile_cols[2].metric(
            "PEOPLE AFFECTED", int(incident["people_affected"])
        )
        profile_cols[3].metric(
            "ELIGIBLE UNITS", len(ranked_resources)
        )

        st.caption(
            "Eligibility is checked before ranking. Candidates must match "
            "the incident type, be marked available, and not already be deployed."
        )

        if not ranked_resources.empty:
            st.markdown("**TOP RESOURCE CANDIDATES**")

            comparison = ranked_resources[
                [
                    "resource_id", "resource_type", "distance_km",
                    "capacity", "proximity_score",
                    "compatibility_score", "capacity_score", "total_score"
                ]
            ].copy()

            comparison.columns = [
                "Resource", "Type", "Distance (km)", "Capacity",
                "Proximity", "Compatibility", "Capacity score", "Total score"
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

            selected_candidate_label = st.radio(
                "Choose a candidate to inspect",
                candidate_labels,
                index=0,
                horizontal=True
            )

            selected_candidate_index = candidate_labels.index(
                selected_candidate_label
            )

            selected_resource = ranked_resources.iloc[
                selected_candidate_index
            ]

            detail_left, detail_right = st.columns([1.2, 1])

            with detail_left:
                st.markdown("**WHY THIS RESOURCE?**")

                st.success(
                    f"{selected_resource['resource_id']} is ranked "
                    f"#{selected_candidate_index + 1} of the eligible candidates."
                )

                st.write(
                    f"- **Compatibility:** {selected_resource['resource_type']} "
                    f"is eligible for {incident['incident_type']}."
                )

                st.write(
                    f"- **Proximity:** {selected_resource['distance_km']:.2f} km "
                    "straight-line distance."
                )

                st.write(
                    f"- **Capacity:** {int(selected_resource['capacity'])} "
                    "synthetic capacity units."
                )

                st.caption(
                    "The score is a prototype decision-support heuristic, "
                    "not a validated emergency-response model."
                )

            with detail_right:
                st.markdown("**SCORE BREAKDOWN**")

                st.progress(
                    min(float(selected_resource["total_score"]) / 100, 1.0),
                    text=(
                        f"Total score: "
                        f"{selected_resource['total_score']:.1f}/100"
                    )
                )

                st.write(
                    f"Proximity: {selected_resource['proximity_score']:.1f}/60"
                )

                st.write(
                    f"Compatibility: "
                    f"{selected_resource['compatibility_score']:.1f}/25"
                )

                st.write(
                    f"Capacity: {selected_resource['capacity_score']:.1f}/15"
                )

            if st.button(
                "APPROVE & RECORD SELECTED ASSIGNMENT",
                use_container_width=True
            ):
                assignment = {
                    "timestamp": datetime.now().strftime(
                        "%Y-%m-%d %H:%M:%S"
                    ),
                    "incident_id": selected_id,
                    "resource_id": selected_resource["resource_id"],
                    "resource_type": selected_resource["resource_type"],
                    "distance_km": round(
                        float(selected_resource["distance_km"]), 2
                    ),
                    "decision_score": float(
                        selected_resource["total_score"]
                    ),
                    "rank_at_approval": selected_candidate_index + 1,
                    "decision": "APPROVED"
                }

                st.session_state.assignments.append(assignment)

                st.session_state.deployed_resources.add(
                    selected_resource["resource_id"]
                )

                st.session_state.assigned_incidents[selected_id] = (
                    selected_resource["resource_id"]
                )

                st.success("Assignment recorded.")
                st.rerun()

        else:
            st.warning(
                "No eligible available resource found. "
                "Coordinator intervention required."
            )

    else:
        st.info("No unassigned incidents match the selected filters.")


# -------------------- INCIDENT REGISTRY ---------------------

elif page == "Incident Registry":
    st.subheader("Incident Registry")
    st.caption("REGISTERED EMERGENCY REQUESTS")

    display = incidents_df.copy()

    display["status"] = display["incident_id"].apply(
        lambda x: (
            "ASSIGNED"
            if x in st.session_state.assigned_incidents
            else "OPEN"
        )
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
        display = display[
            display["status"] != "ASSIGNED"
        ]

    st.dataframe(
        display,
        use_container_width=True,
        hide_index=True
    )


# -------------------- RESOURCE REGISTRY ---------------------

elif page == "Resource Registry":
    st.subheader("Resource Registry")
    st.caption("RESPONSE RESOURCE STATUS")

    display = resources_df.copy()

    display["status"] = display.apply(
        lambda row: (
            "DEPLOYED"
            if row["resource_id"] in st.session_state.deployed_resources
            else row["status"]
        ),
        axis=1
    )

    if resource_filter == "Available only":
        display = display[
            display["status"] == "Available"
        ]

    elif resource_filter == "Busy only":
        display = display[
            display["status"] == "Busy"
        ]

    st.dataframe(
        display,
        use_container_width=True,
        hide_index=True
    )


# -------------------- DECISION LOG --------------------------

elif page == "Decision Log":
    st.subheader("Decision Audit Log")
    st.caption("RECORDED RESOURCE ALLOCATION DECISIONS")

    if st.session_state.assignments:
        log = pd.DataFrame(
            st.session_state.assignments
        )

        st.dataframe(
            log,
            use_container_width=True,
            hide_index=True
        )

        st.metric(
            "TOTAL RECORDED DECISIONS",
            len(log)
        )

    else:
        st.info(
            "No decisions recorded. "
            "Evaluate an incident in the Command Center."
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
            PROTOTYPE 0.3 / SYNTHETIC DATA / HEURISTIC SCORING
        </span>
    </div>
    """,
    unsafe_allow_html=True
)
