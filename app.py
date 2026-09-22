"""
GENESIS EIR Grant — India Startup Ecosystem Intelligence Platform
====================================================================================

A senior-management / programme-monitoring platform built from the "Call for
Applications" dataset for the GENESIS EIR Grant. Features a hero interactive
India map, incubator intelligence, a startup explorer, a generic ecosystem
comparison engine, cross-filtering, drill-down breadcrumbs and automated
insights / attention flags.

Run with:
    python -m streamlit run app.py

Data source:
    data.xlsx and india_states.geojson must sit alongside this file.

-----------------------------------------------------------------------------
ASSUMPTIONS MADE ABOUT THE DATA (documented, not fabricated):

1. STATE EXTRACTION — "State & City" arrives as free text "City, State, India"
   (occasionally "City, State"). State = second-to-last comma token (or the
   last token if the string does not end in "India"). Unmatched values become
   "Not Specified" and are excluded from state-level/geographic charts only.

2. APPLICATION STATUS — "Form Status" is "Submitted" for all 4,039 records
   (there is no Draft/Saved/Rejected/Shortlisted status in this dataset).
   "Round Status" (Active / Withdrawn) is therefore the operative status field
   used throughout for funnels, conversion and "submission-style" metrics, and
   is always labelled explicitly as "Round Status" / "Active" / "Withdrawn" so
   it is never confused with a review decision or a "Saved" application —
   no such status exists in the source file.

3. INCUBATOR FIELD — There is no single "Incubator" column. Incubator-level
   analysis uses "Preference 1" (an applicant's first-choice incubator,
   treated as "the incubator" for aggregate ranking/comparison purposes) and
   "Preference 2" where a second-preference view is explicitly needed. Each
   value has the shape "Incubator Name (City, State)"; name/city/state are
   parsed out with a verified regex (65/65 distinct values matched cleanly).

4. HIGHEST QUALIFICATION — Free text with 350+ distinct raw spellings. Grouped
   into 6 standard buckets (PhD, Postgraduate, Graduate, Undergraduate/Diploma,
   12th/Intermediate, 10th & Below, Other/Unspecified) via case-insensitive
   keyword matching for reporting only. Original text is never altered.

5. MULTI-SELECT FIELDS — "Startup Sector" and "Technology Used" allow multiple
   selections joined by commas. Because several individual labels themselves
   contain commas (e.g. "DeepTech – Advanced Computing & Intelligent Systems
   (AI, ML, Computer Vision, ...)"), values are split only on a comma NOT
   followed by a space — the delimiter the source system uses between
   distinct selections — which keeps such labels intact.

6. GEOGRAPHY — India state boundaries are a public reference GeoJSON (state
   outlines only — no application data was sourced from it), simplified for
   performance. State names are aligned to the dataset's spellings via a small
   lookup (e.g. "Andaman and Nicobar Islands" ↔ "Andaman and Nicobar"). State
   centroids used for incubator map markers are standard public reference
   coordinates for Indian state capitals/regions, not derived from the survey.

7. DATES — Form/Round timestamp fields are parsed using the exact source
   format "DD Mon YYYY hh:mm am/pm". Unparseable dates are treated as missing.

8. DUPLICATE / MISSING-DATA MONITORING has been intentionally removed from
   the user-facing dashboard per explicit direction — the underlying cleaning
   logic (whitespace trimming, null normalisation) is retained internally
   only insofar as it is required for accurate analysis elsewhere.

No values, statuses, states, incubators, sectors, technologies, coordinates or
dates were invented. All figures are computed directly from the uploaded file.
-----------------------------------------------------------------------------
"""

import re
import os
import json
import hashlib

import pandas as pd
import numpy as np
import streamlit as st
import plotly.express as px
import plotly.graph_objects as go

# =============================================================================
# PAGE CONFIG & THEME
# =============================================================================

st.set_page_config(
    page_title="GENESIS EIR | India Startup Ecosystem Intelligence Platform",
    page_icon="🏛️",
    layout="wide",
    initial_sidebar_state="expanded",
)

NAVY = "#0B2545"
NAVY_DARK = "#081B34"
NAVY_MID = "#13315C"
AMBER = "#C8963E"
AMBER_LIGHT = "#E0AC5C"
GREY_BG = "#F4F6F8"
CARD_BG = "#FFFFFF"
TEXT_DARK = "#1B2733"
TEXT_MUTED = "#5B6B7A"
BORDER = "#E3E7EC"
GREEN = "#2E7D5B"
RED = "#B3432B"
MAP_SCALE = [[0, "#EEF2F6"], [0.25, "#C9D9EA"], [0.5, "#7FA0C4"], [0.75, "#3E6B99"], [1, NAVY_DARK]]
# Used for ranked bar charts colored by volume — starts at a clearly visible
# medium blue (not near-white) so low-volume bars stay distinguishable against
# the page background, while still ramping up to navy for the highest values.
STATE_BAR_SCALE = [[0, "#9FBEDD"], [0.5, "#4C7AA8"], [1, NAVY_DARK]]

CHART_SEQUENCE = [NAVY, AMBER, "#3E6B99", "#8AA6C2", "#D8B26B", "#5B7EA8",
                  "#A9BFD4", "#EBC98A", "#274B75", "#C7D1DA"]

BASE_LAYOUT = dict(
    font=dict(family="Segoe UI, Arial, sans-serif", size=13, color=TEXT_DARK),
    paper_bgcolor="rgba(0,0,0,0)",
    plot_bgcolor="rgba(0,0,0,0)",
    margin=dict(l=10, r=20, t=40, b=10),
    colorway=CHART_SEQUENCE,
    legend=dict(orientation="h", yanchor="bottom", y=1.02, xanchor="right", x=1, font=dict(size=12)),
    xaxis=dict(gridcolor=BORDER, zeroline=False),
    yaxis=dict(gridcolor=BORDER, zeroline=False),
    hoverlabel=dict(bgcolor="white", font_size=12.5, font_family="Segoe UI, Arial, sans-serif",
                     bordercolor=NAVY),
)

st.markdown(f"""
<style>
    .stApp {{ background-color: {GREY_BG}; }}
    #MainMenu, footer {{visibility: hidden;}}
    .block-container {{ padding-top: 1.0rem; padding-bottom: 2rem; max-width: 1440px; }}

    .gov-header {{
        background: linear-gradient(90deg, {NAVY_DARK} 0%, {NAVY} 55%, {NAVY_MID} 100%);
        border-radius: 10px; padding: 20px 30px; margin-bottom: 14px;
        border-left: 6px solid {AMBER}; box-shadow: 0 2px 10px rgba(11,37,69,0.18);
        display: flex; justify-content: space-between; align-items: center; flex-wrap: wrap; gap: 10px;
    }}
    .gov-header h1 {{ color: #FFFFFF !important; font-size: 24px; font-weight: 700; margin: 0; letter-spacing: 0.2px; }}
    .gov-header p {{ color: #C9D6E5 !important; font-size: 13px; margin-top: 4px; margin-bottom: 0; }}
    .gov-badge {{
        display:inline-block; background:{AMBER}; color:{NAVY_DARK}; font-weight:700;
        font-size: 11px; padding: 3px 10px; border-radius: 20px; margin-left: 10px; vertical-align: middle;
    }}

    .breadcrumb {{
        background: {CARD_BG}; border: 1px solid {BORDER}; border-radius: 8px;
        padding: 9px 16px; margin-bottom: 12px; font-size: 13px; color: {TEXT_MUTED};
        font-weight: 600; border-left: 4px solid {NAVY};
    }}
    .breadcrumb b {{ color: {NAVY_DARK}; }}

    .explore-strip {{
        background: linear-gradient(90deg, {NAVY} 0%, {NAVY_MID} 100%); color: #EAF0F7;
        border-radius: 8px; padding: 10px 18px; margin-bottom: 14px; font-size: 13.5px;
        border-left: 4px solid {AMBER};
    }}
    .explore-strip b {{ color: {AMBER_LIGHT}; }}

    .kpi-card {{
        background: {CARD_BG}; border: 1px solid {BORDER}; border-radius: 10px;
        padding: 14px 16px 12px 16px; box-shadow: 0 1px 3px rgba(11,37,69,0.06);
        border-top: 3px solid {NAVY}; height: 100px;
    }}
    .kpi-label {{ font-size: 11px; color: {TEXT_MUTED}; font-weight: 600; text-transform: uppercase;
                  letter-spacing: 0.6px; margin-bottom: 5px; }}
    .kpi-value {{ font-size: 24px; font-weight: 700; color: {NAVY_DARK}; line-height: 1.15; }}
    .kpi-sub {{ font-size: 11.5px; color: {TEXT_MUTED}; margin-top: 3px; }}
    .kpi-sub.pos {{ color: {GREEN}; font-weight: 600; }}
    .kpi-sub.neg {{ color: {RED}; font-weight: 600; }}

    .section-title {{ font-size: 16px; font-weight: 700; color: {NAVY_DARK}; margin-top: 4px;
                       margin-bottom: 2px; padding-bottom: 6px; border-bottom: 2px solid {BORDER}; }}
    .section-sub {{ font-size: 12px; color: {TEXT_MUTED}; margin-bottom: 10px; }}

    .insight-card {{
        background: {CARD_BG}; border: 1px solid {BORDER}; border-left: 4px solid {AMBER};
        border-radius: 8px; padding: 11px 15px; margin-bottom: 9px; font-size: 13px;
        color: {TEXT_DARK}; line-height: 1.42;
    }}
    .insight-card b {{ color: {NAVY_DARK}; }}

    .attn-card {{
        background: #FDF6EE; border: 1px solid #EAD3AE; border-left: 4px solid {RED};
        border-radius: 8px; padding: 11px 15px; margin-bottom: 9px; font-size: 13px;
        color: {TEXT_DARK}; line-height: 1.42;
    }}
    .attn-card b {{ color: {RED}; }}
    .attn-title {{ font-size: 11px; font-weight: 700; text-transform: uppercase; letter-spacing: 0.5px;
                    color: {RED}; margin-bottom: 3px; }}

    .profile-card {{
        background: {CARD_BG}; border: 1px solid {BORDER}; border-radius: 10px; padding: 18px 20px;
        border-top: 4px solid {AMBER};
    }}
    .profile-card h4 {{ color: {NAVY_DARK}; margin: 0 0 4px 0; }}

    .meity-title {{ font-size: 22px; font-weight: 800; color: {NAVY_DARK}; letter-spacing: 0.5px; }}
    .meity-heading {{ font-size: 15px; font-weight: 700; color: {AMBER}; letter-spacing: 3px;
                       margin-top: 2px; margin-bottom: 10px; }}
    .meity-heading .meity-scope {{ color: {TEXT_MUTED}; font-weight: 600; letter-spacing: 0.5px; }}
    .meity-desc {{ font-size: 12.5px; color: {TEXT_MUTED}; line-height: 1.55; margin-bottom: 16px; max-width: 92%; }}
    .meity-tile {{ text-align: center; padding: 6px 2px 14px 2px; }}
    .meity-icon {{
        width: 42px; height: 42px; border-radius: 50%; background: {NAVY};
        color: white; font-size: 18px; display: flex; align-items: center; justify-content: center;
        margin: 0 auto 6px auto;
    }}
    .meity-label {{ font-size: 10.5px; font-weight: 700; color: {TEXT_DARK}; letter-spacing: 0.6px;
                     text-transform: uppercase; margin-bottom: 2px; }}
    .meity-lcd {{
        font-family: "Courier New", Courier, monospace; font-weight: 700; font-size: 26px;
        color: #17A94A; letter-spacing: 2px;
    }}
    .meity-hint {{
        display: inline-block; float: right; margin-top: -46px; margin-right: 10px;
        background: {CARD_BG}; border: 1px solid {BORDER}; border-radius: 6px;
        padding: 6px 12px; font-size: 11.5px; color: {TEXT_MUTED}; box-shadow: 0 1px 4px rgba(11,37,69,0.08);
    }}
    .profile-card .tag {{
        display:inline-block; background:{GREY_BG}; color:{NAVY_MID}; font-size:11px; font-weight:600;
        padding:3px 9px; border-radius: 12px; margin: 3px 4px 3px 0; border: 1px solid {BORDER};
    }}

    div[data-testid="stMetricValue"] {{ color: {NAVY_DARK}; }}
    section[data-testid="stSidebar"] {{ background-color: {NAVY_DARK}; }}
    section[data-testid="stSidebar"] * {{ color: #E6ECF3 !important; }}
    section[data-testid="stSidebar"] h1, section[data-testid="stSidebar"] h2,
    section[data-testid="stSidebar"] h3, section[data-testid="stSidebar"] h4,
    section[data-testid="stSidebar"] strong, section[data-testid="stSidebar"] b,
    section[data-testid="stSidebar"] p, section[data-testid="stSidebar"] span,
    section[data-testid="stSidebar"] a {{ color: #E6ECF3 !important; }}
    section[data-testid="stSidebar"] .stButton button {{
        background-color: {AMBER}; color: {NAVY_DARK}; border: none; font-weight: 700;
    }}
    section[data-testid="stSidebar"] .stButton button * {{ color: {NAVY_DARK} !important; }}
    .stTabs [data-baseweb="tab-list"] {{ gap: 4px; }}
    .stTabs [data-baseweb="tab"] {{
        background-color: #FFFFFF; border-radius: 8px 8px 0 0; padding: 8px 14px;
        border: 1px solid {BORDER}; border-bottom: none; font-weight: 600; color: {TEXT_MUTED};
    }}
    .stTabs [aria-selected="true"] {{ background-color: {NAVY}; color: #FFFFFF !important; }}
</style>
""", unsafe_allow_html=True)


# =============================================================================
# DATA LOADING
# =============================================================================

DATA_CANDIDATES = ["data.xlsx", "Final_eir_3_0.xlsx"]
GEOJSON_CANDIDATES = ["india_states.geojson"]
HERE = os.path.dirname(os.path.abspath(__file__))


@st.cache_data(show_spinner="Loading application data...")
def load_raw(file) -> pd.DataFrame:
    df = pd.read_excel(file, sheet_name=0)
    df.columns = [c.strip() for c in df.columns]
    return df


def get_source_file():
    for cand in DATA_CANDIDATES:
        p = os.path.join(HERE, cand)
        if os.path.exists(p):
            return p
    return None


@st.cache_data(show_spinner=False)
def load_geojson():
    for cand in GEOJSON_CANDIDATES:
        p = os.path.join(HERE, cand)
        if os.path.exists(p):
            with open(p, "r") as f:
                return json.load(f)
    return None


# Alignment between dataset state spellings and the reference GeoJSON spellings.
STATE_NAME_TO_GEO = {
    "Andaman and Nicobar Islands": "Andaman and Nicobar",
}
GEO_NAME_TO_STATE = {v: k for k, v in STATE_NAME_TO_GEO.items()}

# Public reference centroids (approx.) for Indian states/UTs — geography only,
# not derived from the survey — used solely to place incubator markers.
STATE_CENTROIDS = {
    "Andhra Pradesh": (15.9129, 79.7400), "Arunachal Pradesh": (28.2180, 94.7278),
    "Assam": (26.2006, 92.9376), "Bihar": (25.0961, 85.3131),
    "Chhattisgarh": (21.2787, 81.8661), "Delhi": (28.7041, 77.1025),
    "Goa": (15.2993, 74.1240), "Gujarat": (22.2587, 71.1924),
    "Haryana": (29.0588, 76.0856), "Himachal Pradesh": (31.1048, 77.1734),
    "Jammu and Kashmir": (33.7782, 76.5762), "Jharkhand": (23.6102, 85.2799),
    "Karnataka": (15.3173, 75.7139), "Kerala": (10.8505, 76.2711),
    "Madhya Pradesh": (22.9734, 78.6569), "Maharashtra": (19.7515, 75.7139),
    "Manipur": (24.6637, 93.9063), "Meghalaya": (25.4670, 91.3662),
    "Mizoram": (23.1645, 92.9376), "Nagaland": (26.1584, 94.5624),
    "Odisha": (20.9517, 85.0985), "Punjab": (31.1471, 75.3412),
    "Rajasthan": (27.0238, 74.2179), "Sikkim": (27.5330, 88.5122),
    "Tamil Nadu": (11.1271, 78.6569), "Telangana": (18.1124, 79.0193),
    "Tripura": (23.9408, 91.9882), "Uttar Pradesh": (26.8467, 80.9462),
    "Uttarakhand": (30.0668, 79.0193), "West Bengal": (22.9868, 87.8550),
    "Chandigarh": (30.7333, 76.7794), "Puducherry": (11.9416, 79.8083),
    "Andaman and Nicobar Islands": (11.7401, 92.6586),
    "Dadra and Nagar Haveli and Daman and Diu": (20.1809, 73.0169),
}

# Known abbreviations / older or alternate names that don't normalize purely
# by punctuation/case cleanup (below) — mapped to the canonical spelling used
# by STATE_CENTROIDS / the GeoJSON.
STATE_NAME_ALIASES = {
    "j and k": "Jammu and Kashmir", "jk": "Jammu and Kashmir",
    "jammu kashmir": "Jammu and Kashmir",
    "orissa": "Odisha", "pondicherry": "Puducherry", "uttaranchal": "Uttarakhand",
    "chattisgarh": "Chhattisgarh", "chattishgarh": "Chhattisgarh",
    "nct of delhi": "Delhi", "delhi nct": "Delhi", "new delhi": "Delhi",
    "national capital territory of delhi": "Delhi",
    "andaman and nicobar": "Andaman and Nicobar Islands",
    "dadra and nagar haveli": "Dadra and Nagar Haveli and Daman and Diu",
    "daman and diu": "Dadra and Nagar Haveli and Daman and Diu",
}


def _state_norm_key(s):
    s = str(s).strip().lower()
    s = s.replace("&", " and ")
    s = re.sub(r"[().]", " ", s)
    s = re.sub(r"\s+", " ", s).strip()
    return s


_CANONICAL_STATE_LOOKUP = {_state_norm_key(c): c for c in STATE_CENTROIDS}


def normalize_state_name(raw):
    """Map common spelling / punctuation variants of a state or UT name (e.g.
    'J&K', 'Jammu & Kashmir', 'Orissa') to the canonical spelling used by the
    reference GeoJSON and centroids, so a minor formatting difference in the
    source data doesn't cause that state to silently vanish from the maps.
    Anything not recognised is returned unchanged (never invents a state)."""
    if raw is None or (isinstance(raw, float) and pd.isna(raw)):
        return raw
    raw = str(raw).strip()
    if not raw or raw == "Not Specified":
        return raw
    if raw in STATE_CENTROIDS:
        return raw
    key = _state_norm_key(raw)
    if key in _CANONICAL_STATE_LOOKUP:
        return _CANONICAL_STATE_LOOKUP[key]
    if key in STATE_NAME_ALIASES:
        return STATE_NAME_ALIASES[key]
    return raw


# =============================================================================
# CLEANING & FEATURE ENGINEERING
# =============================================================================

QUALIFICATION_RULES = [
    ("PhD", [r"\bph\.?d\b", r"\bdoctor(ate)?\b"]),
    ("Postgraduate", [r"post\s*grad", r"\bpg\b", r"\bm\.?tech\b", r"\bm\.?sc\b",
                       r"\bm\.?a\b", r"\bm\.?com\b", r"\bmba\b", r"\bmca\b",
                       r"\bmasters?\b", r"\bm\.?e\b(?!\w)"]),
    ("Graduate", [r"\bgraduat(e|ion)\b(?!.*(post|under))", r"\bb\.?tech\b",
                  r"\bb\.?e\b(?!\w)", r"\bb\.?sc\b", r"\bb\.?a\b(?!\w)", r"\bb\.?com\b",
                  r"\bbba\b", r"\bbca\b", r"\bllb\b", r"\bengineering\b"]),
    ("Undergraduate / Diploma", [r"under\s*grad", r"\bug\b", r"\bdiploma\b",
                                  r"pursuing", r"ongoing"]),
    ("12th / Intermediate", [r"12th", r"\b12\b", r"\bhsc\b", r"intermediate",
                              r"higher secondary", r"10\+2", r"\bsenior secondary\b"]),
    ("10th & Below", [r"10th", r"\b10\b(?!\+)", r"matriculation", r"ssc\b"]),
]

INCUBATOR_PATTERN = re.compile(r"^(.*)\s\(([^,]+),\s*([^)]+)\)$")


def bucket_qualification(raw):
    if pd.isna(raw):
        return "Not Specified"
    text = str(raw).strip().lower()
    if text == "" or text in ("nan", "na", "n/a", "-"):
        return "Not Specified"
    for bucket, patterns in QUALIFICATION_RULES:
        for pat in patterns:
            if re.search(pat, text):
                return bucket
    return "Other / Unspecified"


def extract_state(raw):
    if pd.isna(raw):
        return "Not Specified"
    parts = [p.strip() for p in str(raw).split(",") if p.strip() != ""]
    if len(parts) <= 1:
        return "Not Specified"
    if parts[-1].lower() == "india" and len(parts) >= 2:
        state = parts[-2]
    else:
        state = parts[-1]
    return normalize_state_name(state)


def split_multi(raw):
    """Split on a comma NOT followed by a space — preserves labels that
    themselves contain ', ' internally (e.g. inside parentheses)."""
    if pd.isna(raw) or str(raw).strip() == "":
        return []
    return [x.strip() for x in re.split(r",(?!\s)", str(raw)) if x.strip() != ""]


def parse_incubator(raw):
    """Parse 'Incubator Name (City, State)' -> (name, city, state)."""
    if pd.isna(raw) or str(raw).strip() == "":
        return (np.nan, np.nan, np.nan)
    m = INCUBATOR_PATTERN.match(str(raw).strip())
    if m:
        return (m.group(1).strip(), m.group(2).strip(), normalize_state_name(m.group(3).strip()))
    return (str(raw).strip(), np.nan, np.nan)


def parse_dt(series):
    return pd.to_datetime(series, format="%d %b %Y %I:%M %p", errors="coerce")


@st.cache_data(show_spinner="Preparing dashboard...")
def clean_data(df_raw: pd.DataFrame) -> pd.DataFrame:
    df = df_raw.copy()

    str_cols = df.select_dtypes(include="object").columns
    for c in str_cols:
        df[c] = df[c].apply(lambda x: x.strip() if isinstance(x, str) else x)
        df[c] = df[c].replace({"": np.nan, "nan": np.nan, "NaN": np.nan,
                                "N/A": np.nan, "NA": np.nan})

    df["State"] = df["State & City"].apply(extract_state)
    df["City"] = df["State & City"].apply(
        lambda x: str(x).split(",")[0].strip() if pd.notna(x) else "Not Specified")

    df["Qualification Group"] = df["Highest Qualification"].apply(bucket_qualification)

    df["Sector List"] = df["Startup Sector"].apply(split_multi)
    df["Technology List"] = df["Technology Used"].apply(split_multi)

    for c in ["Form Initiation Time", "Form Submission Time",
              "Round Initiation Time", "Round Last Activity"]:
        if c in df.columns:
            df[c + " (parsed)"] = parse_dt(df[c])

    if "Form Initiation Time (parsed)" in df.columns and "Form Submission Time (parsed)" in df.columns:
        df["Completion Minutes"] = (
            df["Form Submission Time (parsed)"] - df["Form Initiation Time (parsed)"]
        ).dt.total_seconds() / 60.0
        df.loc[df["Completion Minutes"] < 0, "Completion Minutes"] = np.nan

    df["Gender"] = df["Gender"].fillna("Not Specified")
    df["Round Status"] = df["Round Status"].fillna("Not Specified")
    df["Startup Sector"] = df["Startup Sector"].fillna("Not Specified")
    df["Technology Used"] = df["Technology Used"].fillna("Not Specified")
    df["Preference 1"] = df["Preference 1"].fillna("Not Specified")
    df["Preference 2"] = df["Preference 2"].fillna("Not Specified")
    df["Startup Name"] = df["Startup Name"].fillna("Unnamed Startup")

    for c in ["Innovation Type", "Technology Readiness Level (TRL)",
              "Current Startup Stage", "Preferred Incubation Mode",
              "Is your startup incorporated?", "Is your startup DPIIT Registered?",
              "Time allocation by founder on startup", "Current Occupation"]:
        if c in df.columns:
            df[c] = df[c].fillna("Not Specified")

    # Parsed incubator identity for Preference 1 / Preference 2
    p1 = df["Preference 1"].apply(parse_incubator)
    df["Incubator 1 Name"] = [x[0] for x in p1]
    df["Incubator 1 City"] = [x[1] for x in p1]
    df["Incubator 1 State"] = [x[2] for x in p1]
    df["Incubator 1 Name"] = df["Incubator 1 Name"].fillna("Not Specified")

    p2 = df["Preference 2"].apply(parse_incubator)
    df["Incubator 2 Name"] = [x[0] for x in p2]
    df["Incubator 2 City"] = [x[1] for x in p2]
    df["Incubator 2 State"] = [x[2] for x in p2]
    df["Incubator 2 Name"] = df["Incubator 2 Name"].fillna("Not Specified")

    df["Same Incubator Both Preferences"] = (
        (df["Preference 1"] != "Not Specified") & (df["Preference 1"] == df["Preference 2"])
    )

    df["_row_id"] = np.arange(len(df))
    return df


@st.cache_data(show_spinner=False)
def build_incubator_directory(df: pd.DataFrame) -> pd.DataFrame:
    """One row per unique incubator (by Preference-1 identity), with location
    and aggregate metrics computed from applications that chose it as
    Preference 1."""
    valid = df[df["Incubator 1 Name"] != "Not Specified"].copy()
    rows = []
    for name, grp in valid.groupby("Incubator 1 Name"):
        city = grp["Incubator 1 City"].iloc[0]
        state = grp["Incubator 1 State"].iloc[0]
        total = len(grp)
        active = int((grp["Round Status"] == "Active").sum())
        withdrawn = int((grp["Round Status"] == "Withdrawn").sum())
        sectors = set(s for lst in grp["Sector List"] for s in lst)
        techs = set(t for lst in grp["Technology List"] for t in lst)
        states = grp["State"].nunique()
        rows.append({
            "Incubator": name, "City": city, "State": state,
            "Applications": total, "Active": active, "Withdrawn": withdrawn,
            "Active Rate": (active / total * 100) if total else 0,
            "Applicant States": states, "Sectors": len(sectors), "Technologies": len(techs),
        })
    out = pd.DataFrame(rows).sort_values("Applications", ascending=False).reset_index(drop=True)
    return out


# =============================================================================
# FORMATTING & UI HELPERS
# =============================================================================

def fmt_num(n):
    try:
        return f"{int(n):,}"
    except (ValueError, TypeError):
        return "0"


def fmt_pct(n, d):
    if not d:
        return "0.0%"
    return f"{(n / d * 100):.1f}%"


# Friendly display names for the handful of very long compound sector labels
# (raw values preserved everywhere else — this is a presentation-only alias,
# the full original text is always shown in hover tooltips / insight text).
SECTOR_SHORT_MAP = {
    "DeepTech – Advanced Computing & Intelligent Systems (AI, ML, Generative AI, Computer Vision, NLP, Quantum Computing, Advanced Analytics)":
        "DeepTech — Computing & AI",
    "DeepTech – Advanced Electronics, Semiconductors & Connectivity (Semiconductors, Chip Design, ESDM, Embedded Systems, IoT, 5G/6G, Edge Computing, Photonics)":
        "DeepTech — Electronics & Connectivity",
    "DeepTech – Advanced Manufacturing, Robotics & Materials (Industry 4.0, Robotics, Automation, Nanotechnology, Advanced Materials, Digital Twins, Additive Manufacturing)":
        "DeepTech — Manufacturing & Robotics",
    "DeepTech – Biotechnology, Climate & Frontier Technologies (Biotechnology, MedTech, CleanTech, ClimateTech, Space Technologies, Drones, Geospatial, Quantum Communication)":
        "DeepTech — Biotech & Climate",
}


def short_label(text, max_len=30):
    """Shorten a long sector/technology/dimension label for display on chart
    axes while keeping the full original text available for hover tooltips."""
    if text in SECTOR_SHORT_MAP:
        return SECTOR_SHORT_MAP[text]
    base = re.split(r"\s*\(", str(text))[0].strip()
    base = base.rstrip(",")
    if len(base) <= max_len:
        return base
    return base[:max_len - 1].rstrip() + "…"


def kpi_card(label, value, sub=None, sub_class=""):
    sub_html = f'<div class="kpi-sub {sub_class}">{sub}</div>' if sub else ""
    st.markdown(f"""
    <div class="kpi-card">
        <div class="kpi-label">{label}</div>
        <div class="kpi-value">{value}</div>
        {sub_html}
    </div>
    """, unsafe_allow_html=True)


def section_title(title, sub=None):
    st.markdown(f'<div class="section-title">{title}</div>', unsafe_allow_html=True)
    if sub:
        st.markdown(f'<div class="section-sub">{sub}</div>', unsafe_allow_html=True)


def insight(text):
    st.markdown(f'<div class="insight-card">{text}</div>', unsafe_allow_html=True)


def attention(title, text):
    st.markdown(f'<div class="attn-card"><div class="attn-title">{title}</div>{text}</div>',
                unsafe_allow_html=True)


def apply_theme(fig, height=380):
    fig.update_layout(**BASE_LAYOUT)
    fig.update_layout(height=height)
    return fig


def empty_state(msg="No records found for the selected combination."):
    st.info(f"ℹ️ {msg}")


def top_n_counts(series_or_lists, n=10, explode=False, exclude=("Not Specified",)):
    if explode:
        exploded = pd.Series([item for sub in series_or_lists for item in sub])
    else:
        exploded = series_or_lists
    vc = exploded.value_counts()
    vc = vc[~vc.index.isin(exclude)]
    return vc.head(n)


def rank_control(key, label="View"):
    """Reusable Top/Bottom/All toggle used across major ranked charts."""
    return st.selectbox(label, ["Top 10", "Top 5", "Top 15", "All", "Bottom 5", "Bottom 10"],
                         key=key, label_visibility="collapsed")


def apply_rank(counts: pd.Series, mode: str) -> pd.Series:
    if mode == "All":
        return counts.sort_values(ascending=False)
    if mode.startswith("Top"):
        n = int(mode.split()[1])
        return counts.sort_values(ascending=False).head(n)
    if mode.startswith("Bottom"):
        n = int(mode.split()[1])
        return counts.sort_values(ascending=True).head(n)
    return counts


def ranked_bar_chart(counts: pd.Series, color, x_title="Applications", max_label_len=34):
    """Horizontal ranked bar with shortened, non-overlapping axis labels —
    the full original category name is always shown on hover."""
    if not len(counts):
        return None
    d = pd.DataFrame({"full": counts.index.astype(str), "count": counts.values})
    d["short"] = d["full"].apply(lambda t: short_label(t, max_label_len))
    # de-duplicate short labels that collide after truncation
    seen = {}
    labels = []
    for s in d["short"]:
        n = seen.get(s, 0)
        seen[s] = n + 1
        labels.append(s if n == 0 else f"{s} ({n+1})")
    d["short"] = labels
    fig = px.bar(d, x="count", y="short", orientation="h", color_discrete_sequence=[color],
                 custom_data=["full"])
    fig.update_traces(hovertemplate="%{customdata[0]}<br>" + x_title + ": %{x:,}<extra></extra>")
    fig.update_layout(yaxis=dict(autorange="reversed", title=None), xaxis_title=x_title)
    return fig


# =============================================================================
# DIMENSION ENGINE (used by Comparison Studio & Sector–Technology Landscape)
# =============================================================================

DIMENSIONS = {
    "State": {"col": "State", "multi": False},
    "Incubator (Preference 1)": {"col": "Incubator 1 Name", "multi": False},
    "Sector": {"col": "Sector List", "multi": True},
    "Technology": {"col": "Technology List", "multi": True},
    "Startup Stage": {"col": "Current Startup Stage", "multi": False},
    "Gender": {"col": "Gender", "multi": False},
    "Qualification": {"col": "Qualification Group", "multi": False},
    "Innovation Type": {"col": "Innovation Type", "multi": False},
    "TRL": {"col": "Technology Readiness Level (TRL)", "multi": False},
    "Incubation Mode": {"col": "Preferred Incubation Mode", "multi": False},
}

MEASURES = ["Application Count", "Active Count", "Withdrawn Count", "Active Rate (%)", "Share of Total (%)"]


def dimension_long(df: pd.DataFrame, dim_name: str) -> pd.DataFrame:
    """Return a long DataFrame [_row_id, _val, Round Status] for a dimension,
    exploding multi-select dimensions (Sector/Technology)."""
    spec = DIMENSIONS[dim_name]
    col = spec["col"]
    base = df[["_row_id", "Round Status", col]].copy()
    if spec["multi"]:
        base = base.explode(col)
    base = base.rename(columns={col: "_val"})
    base = base[base["_val"].notna() & (base["_val"] != "Not Specified")]
    return base


def build_comparison(df: pd.DataFrame, dim_a: str, dim_b: str, measure: str,
                      top_a=12, top_b=10):
    """Generic reusable comparison engine: cross-tabulates dim_a x dim_b on
    the requested measure and returns (pivot_df, chart_kind)."""
    a_long = dimension_long(df, dim_a).rename(columns={"_val": "A"})
    b_long = dimension_long(df, dim_b).rename(columns={"_val": "B"})
    merged = a_long.merge(b_long[["_row_id", "B"]], on="_row_id", how="inner")
    if merged.empty:
        return None, None

    # restrict to top categories on each side for legibility
    top_a_vals = merged["A"].value_counts().head(top_a).index.tolist()
    top_b_vals = merged["B"].value_counts().head(top_b).index.tolist()
    merged = merged[merged["A"].isin(top_a_vals) & merged["B"].isin(top_b_vals)]
    if merged.empty:
        return None, None

    grp = merged.groupby(["A", "B"])
    counts = grp.size().rename("Application Count")
    active = merged[merged["Round Status"] == "Active"].groupby(["A", "B"]).size().rename("Active Count")
    withdrawn = merged[merged["Round Status"] == "Withdrawn"].groupby(["A", "B"]).size().rename("Withdrawn Count")

    result = pd.concat([counts, active, withdrawn], axis=1).fillna(0).reset_index()
    result["Active Rate (%)"] = np.where(result["Application Count"] > 0,
                                          result["Active Count"] / result["Application Count"] * 100, 0)
    result["Share of Total (%)"] = result["Application Count"] / result["Application Count"].sum() * 100

    pivot = result.pivot(index="A", columns="B", values=measure).fillna(0)

    n_a, n_b = pivot.shape
    if n_a <= 1 or n_b <= 1:
        chart_kind = "bar"
    elif min(n_a, n_b) <= 5:
        chart_kind = "stacked_bar"
    else:
        chart_kind = "heatmap"
    return pivot, chart_kind


def render_clean_heatmap(pivot: pd.DataFrame, y_setter=None, x_setter=None, value_label="Applications",
                          x_max_len=22, y_max_len=30, key="heatmap", height=None):
    """Shared heatmap renderer: short, non-overlapping axis labels with the
    full category name always shown on hover, and (optionally) click-to-filter
    that correctly maps the short label back to the original value."""
    if pivot is None or pivot.empty:
        empty_state("Not enough overlapping data to render this view.")
        return

    short_rows = [short_label(r, y_max_len) for r in pivot.index]
    short_cols = [short_label(c, x_max_len) for c in pivot.columns]
    row_map = dict(zip(short_rows, pivot.index))
    col_map = dict(zip(short_cols, pivot.columns))

    z = pivot.values
    customdata = np.empty(z.shape + (2,), dtype=object)
    for i, r in enumerate(pivot.index):
        for j, c in enumerate(pivot.columns):
            customdata[i, j, 0] = r
            customdata[i, j, 1] = c

    fig = go.Figure(go.Heatmap(
        z=z, x=short_cols, y=short_rows, customdata=customdata,
        colorscale=[[0, GREY_BG], [0.45, AMBER_LIGHT], [1, NAVY]],
        colorbar=dict(title=value_label, thickness=13, len=0.65, tickfont=dict(size=11)),
        hovertemplate=f"%{{customdata[0]}}<br>%{{customdata[1]}}<br>{value_label}: %{{z:,.1f}}<extra></extra>",
        xgap=2, ygap=2,
    ))
    fig.update_layout(
        xaxis=dict(tickangle=-20, automargin=True, tickfont=dict(size=11.5)),
        yaxis=dict(autorange="reversed", automargin=True, tickfont=dict(size=11.5)),
    )
    apply_theme(fig, height or max(360, 34 * len(pivot)))
    fig.update_layout(margin=dict(l=10, r=10, t=10, b=110))

    event = st.plotly_chart(fig, use_container_width=True, key=key, on_select="rerun",
                             config={"displayModeBar": False})
    if event and (x_setter or y_setter):
        try:
            points = event["selection"]["points"]
        except (KeyError, TypeError):
            points = []
        if points:
            p = points[0]
            yv, xv = p.get("y"), p.get("x")
            changed = False
            if y_setter and yv in row_map:
                y_setter(row_map[yv])
                changed = True
            if x_setter and xv in col_map:
                x_setter(col_map[xv])
                changed = True
            if changed:
                st.rerun()


def render_comparison(pivot, chart_kind, dim_a, dim_b, measure):
    if pivot is None or pivot.empty:
        empty_state("No overlapping records for this dimension combination.")
        return
    if chart_kind == "heatmap":
        render_clean_heatmap(pivot, value_label=measure, key="comparison_hm",
                              x_max_len=20, y_max_len=26)
    elif chart_kind == "stacked_bar":
        pivot_disp = pivot.copy()
        pivot_disp.index = [short_label(i, 24) for i in pivot_disp.index]
        pivot_disp.columns = [short_label(c, 24) for c in pivot_disp.columns]
        pivot_disp.index.name = "A"
        pivot_disp.columns.name = "B"
        # fewer-category dimension becomes the stacking colour
        if pivot_disp.shape[0] <= pivot_disp.shape[1]:
            long_df = pivot_disp.reset_index().melt(id_vars="A", var_name="B", value_name=measure)
            fig = px.bar(long_df, x="B", y=measure, color="A", barmode="stack",
                         color_discrete_sequence=CHART_SEQUENCE,
                         labels={"B": dim_b, "A": dim_a})
        else:
            long_df = pivot_disp.reset_index().melt(id_vars="A", var_name="B", value_name=measure)
            fig = px.bar(long_df, x="A", y=measure, color="B", barmode="stack",
                         color_discrete_sequence=CHART_SEQUENCE,
                         labels={"A": dim_a, "B": dim_b})
        fig.update_layout(xaxis_tickangle=-20, yaxis_title=measure, xaxis_title=None,
                           legend=dict(orientation="h", yanchor="bottom", y=1.02, xanchor="left", x=0,
                                       font=dict(size=11)))
        apply_theme(fig, 420)
        fig.update_layout(margin=dict(l=10, r=10, t=50, b=90))
        st.plotly_chart(fig, use_container_width=True, config={"displayModeBar": False})
    else:
        series = pivot.iloc[:, 0].sort_values(ascending=False)
        fig = ranked_bar_chart(series, NAVY, x_title=measure, max_label_len=34)
        apply_theme(fig, max(360, 30 * len(series)))
        st.plotly_chart(fig, use_container_width=True, config={"displayModeBar": False})


# =============================================================================
# INDIA MAP — HERO COMPONENT
# =============================================================================

MAP_MODES = ["Application Density", "Active Applications", "Incubator Distribution",
             "Sector Diversity", "Technology Diversity"]


@st.cache_data(show_spinner=False)
def _incubator_directory_cached(_df):
    return build_incubator_directory(_df)


def compute_state_metrics(df: pd.DataFrame, all_states=None) -> pd.DataFrame:
    """One row per state present in the (filtered) data with all metrics the
    map / hover / drill-down needs. If 'all_states' (the full list of
    state/UT names covered by the GeoJSON) is provided, any state with zero
    matching applications is still included as a zero-value row — this keeps
    the full India outline rendering on the map instead of leaving states
    with no matching data as blank gaps."""
    cols = ["State", "Applications", "Active", "Withdrawn", "Active Rate",
            "Sectors", "Technologies", "Incubators", "Top Sector", "Top Incubator"]
    valid = df[df["State"] != "Not Specified"]
    rows = []
    if not valid.empty:
        for state, grp in valid.groupby("State"):
            total = len(grp)
            active = int((grp["Round Status"] == "Active").sum())
            withdrawn = int((grp["Round Status"] == "Withdrawn").sum())
            sectors = pd.Series([s for lst in grp["Sector List"] for s in lst])
            techs = pd.Series([t for lst in grp["Technology List"] for t in lst])
            incubators = grp.loc[grp["Incubator 1 Name"] != "Not Specified", "Incubator 1 Name"]
            top_sector = sectors.value_counts().index[0] if len(sectors) else "N/A"
            top_incubator = incubators.value_counts().index[0] if len(incubators) else "N/A"
            rows.append({
                "State": state, "Applications": total, "Active": active, "Withdrawn": withdrawn,
                "Active Rate": (active / total * 100) if total else 0,
                "Sectors": sectors.nunique(), "Technologies": techs.nunique(),
                "Incubators": incubators.nunique(), "Top Sector": top_sector, "Top Incubator": top_incubator,
            })
    result = pd.DataFrame(rows, columns=cols)
    if all_states:
        present = set(result["State"]) if not result.empty else set()
        missing = [s for s in all_states if s not in present]
        if missing:
            fill = pd.DataFrame([{
                "State": s, "Applications": 0, "Active": 0, "Withdrawn": 0, "Active Rate": 0,
                "Sectors": 0, "Technologies": 0, "Incubators": 0, "Top Sector": "N/A", "Top Incubator": "N/A",
            } for s in missing], columns=cols)
            result = pd.concat([result, fill], ignore_index=True)
    return result


def render_india_map(state_metrics: pd.DataFrame, geojson, mode: str, incubator_dir: pd.DataFrame,
                      key="india_map"):
    if geojson is None:
        st.warning("India boundary reference file not found — showing ranked bar chart instead.")
        return None

    metric_col = {
        "Application Density": "Applications",
        "Active Applications": "Active",
        "Incubator Distribution": "Incubators",
        "Sector Diversity": "Sectors",
        "Technology Diversity": "Technologies",
    }[mode]

    plot_df = state_metrics.copy()
    plot_df["geo_name"] = plot_df["State"].apply(lambda s: STATE_NAME_TO_GEO.get(s, s))

    fig = go.Figure(go.Choropleth(
        geojson=geojson,
        featureidkey="properties.STATE",
        locations=plot_df["geo_name"],
        z=plot_df[metric_col],
        colorscale=MAP_SCALE,
        marker_line_color="white",
        marker_line_width=0.6,
        colorbar=dict(title=metric_col, thickness=14, len=0.7),
        customdata=plot_df[["State", "Applications", "Active", "Withdrawn", "Active Rate",
                             "Sectors", "Technologies", "Incubators", "Top Sector", "Top Incubator"]],
        hovertemplate=(
            "<b>%{customdata[0]}</b><br>"
            "Applications: %{customdata[1]:,}<br>"
            "Active: %{customdata[2]:,} | Withdrawn: %{customdata[3]:,}<br>"
            "Active Rate: %{customdata[4]:.1f}%<br>"
            "Sectors: %{customdata[5]} | Technologies: %{customdata[6]}<br>"
            "Incubators: %{customdata[7]}<br>"
            "Top Sector: %{customdata[8]}<br>"
            "Top Incubator: %{customdata[9]}"
            "<extra></extra>"
        ),
    ))
    fig.update_geos(
        visible=False, projection_type="mercator",
        lonaxis_range=[67, 98], lataxis_range=[6, 38],
        bgcolor="rgba(0,0,0,0)",
    )
    fig.update_layout(**BASE_LAYOUT)
    fig.update_layout(height=560, margin=dict(l=0, r=0, t=10, b=0),
                       dragmode="pan", coloraxis_showscale=True)

    event = st.plotly_chart(fig, use_container_width=True, key=key, on_select="rerun",
                             config={"scrollZoom": True, "displayModeBar": True,
                                     "modeBarButtonsToRemove": ["lasso2d", "select2d"]})
    return event


# =============================================================================
# MEITY-STYLE FLAT MAP (Executive Overview hero — matches reference screenshot)
# =============================================================================

FLAT_STATE_LINE = "#2C3E50"
FLAT_SELECTED_COLOR = AMBER

# Multi-shade blue palette (light -> dark) used to give each state its own
# tone, purely for visual distinction between neighbouring states — colours
# carry no data meaning here (data-driven views use MAP_SCALE elsewhere).
STATE_SHADE_PALETTE = [
    "#EAF0F8", "#D3E0F0", "#BBD0E8", "#A3C0E0", "#8CB0D8", "#79A0CC",
    "#6690C0", "#5580B4", "#4570A6", "#376198", "#2B5288", "#204378",
]


def _state_shade(name: str) -> str:
    """Deterministic pseudo-random shade per state name, stable across runs."""
    h = int(hashlib.md5(str(name).encode()).hexdigest(), 16)
    return STATE_SHADE_PALETTE[h % len(STATE_SHADE_PALETTE)]


def _discrete_choropleth_colorscale(colors: list):
    """Build a step-function colorscale so each location gets its own flat
    colour with no blending into its neighbours in the array."""
    n = len(colors)
    if n <= 1:
        c = colors[0] if colors else "#D6DCE3"
        return [[0, c], [1, c]]
    scale = []
    step = 1.0 / n
    for i, c in enumerate(colors):
        lo = i * step
        hi = (i + 1) * step - 1e-6
        scale.append([lo, c])
        scale.append([hi, c])
    scale[0][0] = 0.0
    scale[-1][0] = 1.0
    return scale


def render_flat_state_map(all_state_metrics: pd.DataFrame, selected_state, geojson, key="flat_map"):
    """India map with each state shown in its own shade of blue and crisp dark
    borders (matching the reference style), with the selected state picked
    out in amber. Click a state to select it (hover-only reactivity isn't
    feasible with a server-rendered Streamlit/Plotly chart, so click is used
    instead)."""
    if all_state_metrics.empty:
        return None

    plot_df = all_state_metrics.copy()
    locations = plot_df["State"].tolist()
    colors = [FLAT_SELECTED_COLOR if (selected_state and s == selected_state) else _state_shade(s)
              for s in locations]
    z = list(range(len(locations)))
    colorscale = _discrete_choropleth_colorscale(colors)

    fig = go.Figure(go.Choropleth(
        geojson=geojson,
        featureidkey="properties.STATE",
        locations=locations,
        z=z,
        zmin=0, zmax=max(len(locations), 1),
        colorscale=colorscale,
        showscale=False,
        marker_line_color=FLAT_STATE_LINE,
        marker_line_width=0.9,
        customdata=plot_df[["State", "Applications", "Active", "Active Rate"]],
        hovertemplate=(
            "<b>%{customdata[0]}</b><br>"
            "Applications: %{customdata[1]:,}<br>"
            "Active: %{customdata[2]:,} (%{customdata[3]:.1f}%)"
            "<extra></extra>"
        ),
    ))
    fig.update_geos(visible=False, projection_type="mercator",
                     lonaxis_range=[67, 98], lataxis_range=[5.5, 38], bgcolor="rgba(0,0,0,0)",
                     fitbounds=False)
    fig.update_layout(**BASE_LAYOUT)
    fig.update_layout(height=560, margin=dict(l=0, r=0, t=0, b=0), dragmode="pan")

    event = st.plotly_chart(fig, use_container_width=True, key=key, on_select="rerun",
                             config={"scrollZoom": True, "displayModeBar": True,
                                     "modeBarButtonsToRemove": ["lasso2d", "select2d"]})
    return event




def _lcd_tile(icon, label, value):
    st.markdown(f"""
    <div class="meity-tile">
        <div class="meity-icon">{icon}</div>
        <div class="meity-label">{label}</div>
        <div class="meity-lcd">{value}</div>
    </div>
    """, unsafe_allow_html=True)


def render_meity_style_hero(fdf, df, geojson, inc_dir_full):
    """Executive Overview hero — statistics panel + flat India map, styled
    after the MeitY Startup Hub reference. Numbers reflect the current filter
    scope (fdf); clicking a state on the map narrows that scope further."""
    left, right = st.columns([1, 1.35])

    with left:
        k = compute_core_kpis(fdf)
        scope_label = f_state[0] if len(f_state) == 1 else "All India"
        st.markdown(f"""
        <div class="meity-title">STARTUP ECOSYSTEM</div>
        <div class="meity-heading">STATISTICS <span class="meity-scope">— {scope_label}</span></div>
        <div class="meity-desc">
            This dashboard provides a consolidated view of GENESIS EIR Cohort-3 Applications — applicant state,
            sector, technology, incubator preference and founder profile — into a single
            programme-monitoring snapshot. Click any state on the map to drill into its numbers.
        </div>
        """, unsafe_allow_html=True)

        r1c1, r1c2, r1c3 = st.columns(3)
        with r1c1:
            _lcd_tile("🚀", "APPLICATIONS", fmt_num(k["total"]))
        with r1c2:
            _lcd_tile("🏢", "INCUBATORS", fmt_num(k["n_incubators"]))
        with r1c3:
            _lcd_tile("🧭", "SECTORS", fmt_num(k["n_sectors"]))
        r2c1, r2c2, r2c3 = st.columns(3)
        with r2c1:
            _lcd_tile("📍", "STATES/UTS", fmt_num(k["n_states"]))
        with r2c2:
            _lcd_tile("💡", "TECHNOLOGIES", fmt_num(k["n_tech"]))
        with r2c3:
            _lcd_tile("✅", "ACTIVE RATE", f"{fmt_pct(k['active'], k['total'])}")

        if f_state:
            if st.button("↺ Back to All India", key="meity_reset"):
                select_state(None)
                st.rerun()

    with right:
        all_state_metrics = compute_state_metrics(df, ALL_GEO_STATE_NAMES)
        selected = f_state[0] if len(f_state) == 1 else None
        if all_state_metrics.empty:
            empty_state("No geo-tagged records available to plot.")
        else:
            event = render_flat_state_map(all_state_metrics, selected, geojson, key="meity_flat_map")
            _handle_map_click(event, all_state_metrics)
        st.markdown('<div class="meity-hint">Click a state to explore its numbers</div>', unsafe_allow_html=True)



# =============================================================================

source_path = get_source_file()
if source_path:
    raw_df = load_raw(source_path)
else:
    st.markdown("""
    <div class="gov-header"><h1>GENESIS EIR — India Startup Ecosystem Intelligence Platform</h1>
    <p>Upload the application dataset (.xlsx) to begin.</p></div>
    """, unsafe_allow_html=True)
    uploaded = st.file_uploader("Upload dataset (.xlsx)", type=["xlsx"])
    if uploaded is None:
        st.stop()
    raw_df = load_raw(uploaded)

df = clean_data(raw_df)
india_geojson = load_geojson()

# Every state/UT name the GeoJSON covers (mapped to the dataset's spelling
# where an alignment exists) — used so the map always renders the complete
# India outline, even for states with zero matching applications.
if india_geojson:
    ALL_GEO_STATE_NAMES = sorted(set(
        GEO_NAME_TO_STATE.get(feat["properties"].get("STATE"), feat["properties"].get("STATE"))
        for feat in india_geojson.get("features", [])
        if feat.get("properties", {}).get("STATE")
    ))
else:
    ALL_GEO_STATE_NAMES = []
incubator_directory_full = _incubator_directory_cached(df)

# =============================================================================
# SESSION STATE DEFAULTS
# =============================================================================

for _k, _v in {
    "f_state": [], "f_round_status": [], "f_sector": [], "f_tech": [], "f_stage": [],
    "f_gender": [], "f_qual": [], "f_incubator": [], "f_innov": [], "f_mode": [], "f_trl": [],
}.items():
    if _k not in st.session_state:
        st.session_state[_k] = _v

# Apply any pending click-driven filter changes (from map/incubator/heatmap clicks
# in the tabs below) BEFORE the sidebar widgets are instantiated this run — a
# widget-bound session_state key cannot be reassigned after its widget has
# already rendered in the same script pass, so click handlers stage their
# intent here via "_pending_*" keys instead of writing the widget key directly.
for _pk, _sk in [("_pending_f_state", "f_state"), ("_pending_f_incubator", "f_incubator"),
                 ("_pending_f_sector", "f_sector"), ("_pending_f_tech", "f_tech")]:
    if _pk in st.session_state:
        st.session_state[_sk] = st.session_state.pop(_pk)


def reset_all_filters():
    for k in ["f_state", "f_round_status", "f_sector", "f_tech", "f_stage",
              "f_gender", "f_qual", "f_incubator", "f_innov", "f_mode", "f_trl"]:
        st.session_state[k] = []


def select_state(state_name):
    st.session_state["_pending_f_state"] = [state_name] if state_name else []


def select_incubator(inc_name):
    st.session_state["_pending_f_incubator"] = [inc_name] if inc_name else []


def select_sector(sector_name):
    st.session_state["_pending_f_sector"] = [sector_name] if sector_name else []


def select_technology(tech_name):
    st.session_state["_pending_f_tech"] = [tech_name] if tech_name else []


# =============================================================================
# SIDEBAR — FILTERS
# =============================================================================

with st.sidebar:
    st.markdown("### 🏛️ GENESIS EIR 3.0")
    st.markdown("---")

    if st.button("🔄 Clear All Filters", use_container_width=True):
        reset_all_filters()
        st.rerun()

    def multiselect_filter(label, options, key):
        options = sorted([o for o in options if o not in (None, "Not Specified") and str(o) != "nan"])
        if key not in st.session_state:
            st.session_state[key] = []
        return st.multiselect(label, options, key=key)

    f_state = multiselect_filter("State", df["State"].unique(), "f_state")

    all_incubators = sorted(set(df["Incubator 1 Name"].unique()) - {"Not Specified"})
    f_incubator = multiselect_filter("Incubator (Preference 1)", all_incubators, "f_incubator")

    f_gender = multiselect_filter("Gender", df["Gender"].unique(), "f_gender")
    f_trl = multiselect_filter("TRL", df["Technology Readiness Level (TRL)"].unique(), "f_trl")
    f_innov = multiselect_filter("Innovation Type", df["Innovation Type"].unique(), "f_innov")
    f_mode = multiselect_filter("Preferred Incubation Mode", df["Preferred Incubation Mode"].unique(), "f_mode")
    f_qual = multiselect_filter("Qualification", df["Qualification Group"].unique(), "f_qual")

    all_tech = sorted(set(t for lst in df["Technology List"] for t in lst))
    f_tech = multiselect_filter("Technology Used", all_tech, "f_tech")

    all_sectors = sorted(set(s for lst in df["Sector List"] for s in lst))
    f_sector = multiselect_filter("Startup Sector", all_sectors, "f_sector")

    # Round Status and Startup Stage filters are hidden from the sidebar per
    # request; kept as inactive empty selections so filtering logic elsewhere
    # continues to work unchanged (they simply never narrow the data).
    f_round_status = st.session_state.get("f_round_status", [])
    f_stage = st.session_state.get("f_stage", [])

    min_dt = df["Form Submission Time (parsed)"].min()
    max_dt = df["Form Submission Time (parsed)"].max()
    st.markdown("**Submission Date Range**")
    if pd.notna(min_dt) and pd.notna(max_dt):
        date_range = st.date_input(
            "Date range", value=(min_dt.date(), max_dt.date()),
            min_value=min_dt.date(), max_value=max_dt.date(),
            key="f_daterange", label_visibility="collapsed")
    else:
        date_range = None

    st.markdown("---")
    st.caption(f"Dataset: {fmt_num(len(df))} total application records")


def apply_filters(data):
    d = data.copy()
    if f_state:
        d = d[d["State"].isin(f_state)]
    if f_round_status:
        d = d[d["Round Status"].isin(f_round_status)]
    if f_sector:
        d = d[d["Sector List"].apply(lambda lst: any(s in lst for s in f_sector))]
    if f_tech:
        d = d[d["Technology List"].apply(lambda lst: any(t in lst for t in f_tech))]
    if f_stage:
        d = d[d["Current Startup Stage"].isin(f_stage)]
    if f_gender:
        d = d[d["Gender"].isin(f_gender)]
    if f_qual:
        d = d[d["Qualification Group"].isin(f_qual)]
    if f_incubator:
        d = d[d["Incubator 1 Name"].isin(f_incubator)]
    if f_innov:
        d = d[d["Innovation Type"].isin(f_innov)]
    if f_mode:
        d = d[d["Preferred Incubation Mode"].isin(f_mode)]
    if f_trl:
        d = d[d["Technology Readiness Level (TRL)"].isin(f_trl)]
    if date_range and isinstance(date_range, tuple) and len(date_range) == 2:
        start, end = date_range
        mask = (d["Form Submission Time (parsed)"].dt.date >= start) & \
               (d["Form Submission Time (parsed)"].dt.date <= end)
        d = d[mask | d["Form Submission Time (parsed)"].isna()]
    return d


fdf = apply_filters(df)
active_filter_count = sum([bool(x) for x in [
    f_state, f_round_status, f_sector, f_tech, f_stage, f_gender, f_qual,
    f_incubator, f_innov, f_mode, f_trl]])


# =============================================================================
# HEADER, BREADCRUMB, EXPLORE-SELECTION STRIP
# =============================================================================

st.markdown(f"""
<div class="gov-header">
    <div>
        <h1>Genesis EIR Cohort-3 Applications Dashboard</h1>
    </div>
</div>
""", unsafe_allow_html=True)

# Safety check: if the current filter combination returns no records, stop
# here rather than letting later charts/KPIs error out on an empty frame.
if len(fdf) == 0:
    st.warning("⚠️ No records match the current filter combination. "
               "Try removing a filter or use **Clear All Filters** in the sidebar.")
    st.stop()




# =============================================================================
# SHARED ANALYTICS: KPIs / INSIGHTS / ATTENTION
# =============================================================================

def compute_core_kpis(d: pd.DataFrame) -> dict:
    total = len(d)
    active = int((d["Round Status"] == "Active").sum())
    withdrawn = int((d["Round Status"] == "Withdrawn").sum())
    n_states = d.loc[d["State"] != "Not Specified", "State"].nunique()
    n_sectors = len(set(s for lst in d["Sector List"] for s in lst))
    n_incubators = d.loc[d["Incubator 1 Name"] != "Not Specified", "Incubator 1 Name"].nunique()
    n_tech = len(set(t for lst in d["Technology List"] for t in lst))
    return dict(total=total, active=active, withdrawn=withdrawn, n_states=n_states,
                n_sectors=n_sectors, n_incubators=n_incubators, n_tech=n_tech)


def generate_insights(d: pd.DataFrame) -> list:
    out = []
    total = len(d)
    valid_state = d[d["State"] != "Not Specified"]
    state_counts = valid_state["State"].value_counts()
    if len(state_counts):
        out.append(f"<b>{state_counts.index[0]}</b> leads state-wise participation with "
                    f"<b>{fmt_num(state_counts.iloc[0])}</b> applications "
                    f"({fmt_pct(state_counts.iloc[0], len(valid_state))} of geo-tagged applications).")
        top5_share = state_counts.head(5).sum()
        out.append(f"The <b>top 5 states</b> together contribute <b>{fmt_pct(top5_share, len(valid_state))}</b> "
                    f"of all applications — a "
                    f"{'concentrated' if top5_share/len(valid_state) > 0.55 else 'fairly distributed'} geographic footprint.")
    sector_counts = top_n_counts(d["Sector List"], n=1, explode=True)
    if len(sector_counts):
        out.append(f"<b>{sector_counts.index[0]}</b> is the most represented startup sector "
                    f"with <b>{fmt_num(sector_counts.iloc[0])}</b> tagged applications.")
    inc_counts = d.loc[d["Incubator 1 Name"] != "Not Specified", "Incubator 1 Name"].value_counts()
    if len(inc_counts):
        out.append(f"<b>{inc_counts.index[0]}</b> is the most preferred incubator (Preference 1) "
                    f"with <b>{fmt_num(inc_counts.iloc[0])}</b> applicants.")
    stage_counts = d["Current Startup Stage"].value_counts()
    stage_counts = stage_counts[stage_counts.index != "Not Specified"]
    if len(stage_counts):
        dom_stage = stage_counts.idxmax()
        out.append(f"Most applicants are at the <b>{dom_stage}</b> stage "
                    f"({fmt_pct(stage_counts.max(), total)} of applications).")
    gender_counts = d["Gender"].value_counts()
    out.append(f"Founder gender split stands at <b>{fmt_pct(gender_counts.get('Male', 0), total)} male</b> vs "
                f"<b>{fmt_pct(gender_counts.get('Female', 0), total)} female</b> applicants.")
    active = int((d["Round Status"] == "Active").sum())
    out.append(f"<b>{fmt_pct(active, total)}</b> of applications are currently <b>Active</b>; "
                f"<b>{fmt_pct(total - active, total)}</b> have been <b>Withdrawn</b>.")
    return out


def generate_attention(d: pd.DataFrame, inc_dir: pd.DataFrame) -> list:
    """Automated ecosystem attention flags with transparent, stated thresholds."""
    flags = []
    total = len(d)
    overall_withdrawn_rate = (d["Round Status"] == "Withdrawn").mean() * 100

    # Low-participation states (bottom quartile among states with >=1 application)
    valid_state = d[d["State"] != "Not Specified"]
    state_counts = valid_state["State"].value_counts()
    if len(state_counts) >= 4:
        q25 = state_counts.quantile(0.25)
        low_states = state_counts[state_counts <= q25]
        if len(low_states):
            names = ", ".join(low_states.index[:8])
            flags.append(("Low-Participation States",
                           f"<b>{len(low_states)}</b> states/UTs fall at or below the 25th percentile of "
                           f"application volume (≤ <b>{int(q25)}</b> applications each): {names}"
                           f"{' …' if len(low_states) > 8 else ''}."))

    # Low-application incubators (bottom quartile among incubators with >=1 application)
    if len(inc_dir) >= 4:
        q25_i = inc_dir["Applications"].quantile(0.25)
        low_inc = inc_dir[inc_dir["Applications"] <= q25_i]
        if len(low_inc):
            names = ", ".join(low_inc["Incubator"].head(8))
            flags.append(("Low-Application Incubators",
                           f"<b>{len(low_inc)}</b> incubators fall at or below the 25th percentile of "
                           f"Preference-1 applications (≤ <b>{int(q25_i)}</b> each): {names}"
                           f"{' …' if len(low_inc) > 8 else ''}."))

    # High-withdrawal incubators (>= 10 applications and withdrawn rate > 1.5x overall average)
    eligible_inc = inc_dir[inc_dir["Applications"] >= 10].copy()
    eligible_inc["Withdrawn Rate"] = 100 - eligible_inc["Active Rate"]
    threshold = max(overall_withdrawn_rate * 1.5, overall_withdrawn_rate + 5)
    high_wd = eligible_inc[eligible_inc["Withdrawn Rate"] > threshold]
    if len(high_wd):
        names = ", ".join(high_wd.sort_values("Withdrawn Rate", ascending=False)["Incubator"].head(6))
        flags.append(("High-Withdrawal Incubators",
                       f"<b>{len(high_wd)}</b> incubators (≥10 applications) show a withdrawal rate above "
                       f"<b>{threshold:.1f}%</b> (vs. the overall average of {overall_withdrawn_rate:.1f}%): {names}."))

    # Low-participation sectors (bottom quartile among sectors with >=1 application)
    sector_counts = pd.Series([s for lst in d["Sector List"] for s in lst]).value_counts()
    if len(sector_counts) >= 4:
        q25_s = sector_counts.quantile(0.25)
        low_sec = sector_counts[sector_counts <= q25_s]
        if len(low_sec):
            names = ", ".join(low_sec.index[:6])
            flags.append(("Low-Participation Sectors",
                           f"<b>{len(low_sec)}</b> sectors fall at or below the 25th percentile of tagged "
                           f"applications (≤ <b>{int(q25_s)}</b> each): {names}"
                           f"{' …' if len(low_sec) > 6 else ''}."))

    if not flags:
        flags.append(("All Clear", "No participation or conversion anomalies detected against current thresholds."))
    return flags


# =============================================================================
# EXECUTIVE VIEW — condensed, highly visual, single page
# =============================================================================

def _handle_map_click(event, state_metrics):
    """Shared click handler: reads a Plotly on_select event from the India
    choropleth and drills the sidebar state filter down to the clicked state."""
    if not event:
        return
    try:
        points = event["selection"]["points"]
    except (KeyError, TypeError):
        points = []
    if points:
        loc = points[0].get("location")
        if loc:
            state_name = GEO_NAME_TO_STATE.get(loc, loc)
            if state_name in state_metrics["State"].values and st.session_state.get("f_state") != [state_name]:
                select_state(state_name)
                st.rerun()


# =============================================================================
# INCUBATOR MAP (bubble markers at state-level reference centroids)
# =============================================================================

def render_incubator_map(inc_dir: pd.DataFrame, geojson, state_metrics: pd.DataFrame, key="incubator_map"):
    """State-level incubator footprint map: one bubble per state (no overlap,
    however many incubators sit underneath it), sized by number of incubators
    and coloured by total applications received. Click a bubble to drill
    into that state — the incubator-by-incubator detail lives in the ranking
    chart / table below this map."""
    fig = go.Figure()
    plot_states = state_metrics.copy()
    if not plot_states.empty:
        plot_states["geo_name"] = plot_states["State"].apply(lambda s: STATE_NAME_TO_GEO.get(s, s))
        fig.add_trace(go.Choropleth(
            geojson=geojson, featureidkey="properties.STATE", locations=plot_states["geo_name"],
            z=[1] * len(plot_states), showscale=False,
            colorscale=[[0, "#E7ECF1"], [1, "#E7ECF1"]],
            marker_line_color="#2C3E50", marker_line_width=0.9, hoverinfo="skip",
        ))

    def _incubator_breakdown(grp):
        sorted_grp = grp.sort_values("Applications", ascending=False)
        lines = [f"{row['Incubator']} – {int(row['Applications'])} Applications"
                 for _, row in sorted_grp.iterrows()]
        max_lines = 30
        if len(lines) > max_lines:
            lines = lines[:max_lines] + [f"+ {len(lines) - max_lines} more"]
        return "<br>".join(lines)

    state_agg = inc_dir.groupby("State").agg(
        Incubators=("Incubator", "nunique"),
        Applications=("Applications", "sum"),
        Active=("Active", "sum"),
        City=("City", lambda s: s.value_counts().index[0] if len(s) else "N/A"),
    ).reset_index()
    state_agg["Active Rate"] = np.where(state_agg["Applications"] > 0,
                                         state_agg["Active"] / state_agg["Applications"] * 100, 0)
    breakdown = inc_dir.groupby("State").apply(_incubator_breakdown).rename("Breakdown").reset_index()
    state_agg = state_agg.merge(breakdown, on="State", how="left")
    state_agg["lat"] = state_agg["State"].map(lambda s: STATE_CENTROIDS.get(s, (None, None))[0])
    state_agg["lon"] = state_agg["State"].map(lambda s: STATE_CENTROIDS.get(s, (None, None))[1])
    state_agg = state_agg.dropna(subset=["lat", "lon"])

    if not state_agg.empty:
        max_inc = max(state_agg["Incubators"].max(), 1)
        fig.add_trace(go.Scattergeo(
            lat=state_agg["lat"], lon=state_agg["lon"], mode="markers",
            customdata=state_agg[["State", "Incubators", "Applications", "Active Rate", "Breakdown"]],
            marker=dict(
                size=np.clip(state_agg["Incubators"] / max_inc * 46, 16, 46),
                color=state_agg["Applications"], colorscale=STATE_BAR_SCALE,
                cmin=0, cmax=max(state_agg["Applications"].max(), 1),
                opacity=0.88, line=dict(width=1.3, color="white"),
                colorbar=dict(title=dict(text="Applications", font=dict(size=11.5)),
                               thickness=13, len=0.55, tickfont=dict(size=10.5), y=0.4),
            ),
            hovertemplate=("<b>%{customdata[0]}</b><br>Incubators: %{customdata[1]:,}<br>"
                            "Applications: %{customdata[2]:,}<br>Active Rate: %{customdata[3]:.1f}%"
                            "<br><br>%{customdata[4]}"
                            "<extra></extra>"),
        ))
    fig.update_geos(visible=False, projection_type="mercator", lonaxis_range=[67, 98], lataxis_range=[6, 38],
                     bgcolor="rgba(0,0,0,0)")
    fig.update_layout(**BASE_LAYOUT)
    fig.update_layout(height=560, margin=dict(l=0, r=0, t=10, b=0), showlegend=False)
    event = st.plotly_chart(fig, use_container_width=True, key=key, on_select="rerun",
                             config={"scrollZoom": True, "displayModeBar": True,
                                     "modeBarButtonsToRemove": ["lasso2d", "select2d"]})
    return event


def _handle_point_click(event, setter_fn, name_field_index=0):
    if not event:
        return
    try:
        points = event["selection"]["points"]
    except (KeyError, TypeError):
        points = []
    if points:
        cd = points[0].get("customdata")
        if cd:
            setter_fn(cd[name_field_index])
            st.rerun()


def _handle_heatmap_click(event, row_setter, col_setter):
    if not event:
        return
    try:
        points = event["selection"]["points"]
    except (KeyError, TypeError):
        points = []
    if points:
        p = points[0]
        y_val, x_val = p.get("y"), p.get("x")
        if y_val is not None:
            row_setter(y_val)
        if x_val is not None:
            col_setter(x_val)
        if y_val is not None or x_val is not None:
            st.rerun()


# =============================================================================
# ANALYST VIEW — full tab set
# =============================================================================



def render_dashboard(fdf, df, geojson, inc_dir_full):
    tabs = st.tabs([
        "📊 Executive Overview", "📈 Application Analytics", "🚀 Startup Ecosystem",
        "🗺️ Geographic Intelligence", "👥 Founder & Demographics",
        "🏢 Incubator Intelligence", "⚖️ Ecosystem Comparison",
    ])

    # ---- TAB: Executive Overview -------------------------------------------
    with tabs[0]:
        render_meity_style_hero(fdf, df, geojson, inc_dir_full)

        colA, colB, colC = st.columns(3)
        with colA:
            section_title("Top Startup Sectors")
            sector_top = top_n_counts(fdf["Sector List"], n=8, explode=True)
            if len(sector_top):
                fig = px.bar(x=sector_top.values, y=sector_top.index, orientation="h", color_discrete_sequence=[NAVY])
                fig.update_traces(hovertemplate="%{y}<br>Applications: %{x:,}<extra></extra>")
                fig.update_layout(yaxis=dict(autorange="reversed", title=None), xaxis_title="Applications")
                apply_theme(fig, 320)
                st.plotly_chart(fig, use_container_width=True, config={"displayModeBar": False})
            else:
                empty_state()
        with colB:
            section_title("Top Participating States")
            state_top = top_n_counts(fdf["State"], n=8)
            if len(state_top):
                fig = px.bar(x=state_top.values, y=state_top.index, orientation="h", color_discrete_sequence=[AMBER])
                fig.update_traces(hovertemplate="%{y}<br>Applications: %{x:,}<extra></extra>")
                fig.update_layout(yaxis=dict(autorange="reversed", title=None), xaxis_title="Applications")
                apply_theme(fig, 320)
                st.plotly_chart(fig, use_container_width=True, config={"displayModeBar": False})
            else:
                empty_state()
        with colC:
            section_title("Top Incubators (Pref. 1)")
            inc_top = top_n_counts(fdf.loc[fdf["Incubator 1 Name"] != "Not Specified", "Incubator 1 Name"], n=8)
            if len(inc_top):
                fig = px.bar(x=inc_top.values, y=inc_top.index, orientation="h", color_discrete_sequence=[AMBER_LIGHT])
                fig.update_traces(hovertemplate="%{y}<br>Applications: %{x:,}<extra></extra>")
                fig.update_layout(yaxis=dict(autorange="reversed", title=None), xaxis_title="Applications")
                apply_theme(fig, 320)
                st.plotly_chart(fig, use_container_width=True, config={"displayModeBar": False})
            else:
                empty_state()

        colD, colE = st.columns(2)
        with colD:
            section_title("Startup Stage Distribution")
            stage_counts = fdf["Current Startup Stage"].value_counts()
            stage_counts = stage_counts[stage_counts.index != "Not Specified"]
            if len(stage_counts):
                fig = px.bar(x=stage_counts.index, y=stage_counts.values, color_discrete_sequence=[NAVY_MID])
                fig.update_traces(hovertemplate="%{x}<br>Applications: %{y:,}<extra></extra>")
                fig.update_layout(xaxis_title=None, yaxis_title="Applications")
                apply_theme(fig, 300)
                st.plotly_chart(fig, use_container_width=True, config={"displayModeBar": False})
            else:
                empty_state()
        with colE:
            section_title("Founder Gender Distribution")
            gender_counts = fdf["Gender"].value_counts()
            fig = px.pie(values=gender_counts.values, names=gender_counts.index, hole=0.55,
                         color_discrete_sequence=CHART_SEQUENCE)
            fig.update_traces(textinfo="percent+label", hovertemplate="%{label}<br>%{value:,} (%{percent})<extra></extra>")
            apply_theme(fig, 300)
            fig.update_layout(showlegend=False)
            st.plotly_chart(fig, use_container_width=True, config={"displayModeBar": False})

        st.markdown("<br>", unsafe_allow_html=True)
        section_title("Key Ecosystem Insights")
        insight_texts = generate_insights(fdf)
        ic1, ic2 = st.columns(2)
        for i, text in enumerate(insight_texts):
            with (ic1 if i % 2 == 0 else ic2):
                insight(text)

    # ---- TAB: Application Analytics -----------------------------------------
    with tabs[1]:
        k = compute_core_kpis(fdf)
        c1, c2, c3, c4 = st.columns(4)
        with c1:
            kpi_card("Total Applications", fmt_num(k["total"]))
        with c2:
            kpi_card("Form Status: Submitted",
                      fmt_num((fdf["Form Status"] == "Submitted").sum()) if "Form Status" in fdf.columns else "N/A",
                      "All records reached submission")
        with c3:
            kpi_card("Round Status: Active", fmt_num(k["active"]))
        with c4:
            kpi_card("Round Status: Withdrawn", fmt_num(k["withdrawn"]))

        st.caption("Note: 'Form Status' reflects whether the online form itself was completed (100% Submitted in "
                   "this dataset — there is no Saved/Draft status to report). 'Round Status' — Active or Withdrawn "
                   "— is the operative status field used as the funnel below.")

        section_title("Application Funnel by Round Status")
        sc = fdf["Round Status"].value_counts()
        fig = go.Figure(go.Funnel(
            y=sc.index.tolist(), x=sc.values.tolist(), textinfo="value+percent initial",
            marker=dict(color=[NAVY, RED, "#8AA6C2"][:len(sc)]),
            hovertemplate="%{y}<br>Applications: %{value:,}<extra></extra>",
        ))
        apply_theme(fig, 320)
        st.plotly_chart(fig, use_container_width=True, config={"displayModeBar": False})

        section_title("Application Trends Over Time", "Based on Form Submission Time")
        ts = fdf.dropna(subset=["Form Submission Time (parsed)"]).copy()
        if len(ts) > 0:
            granularity = st.radio("Granularity", ["Daily", "Weekly"], horizontal=True, key="trend_gran")
            ts["period"] = ts["Form Submission Time (parsed)"].dt.date if granularity == "Daily" else \
                ts["Form Submission Time (parsed)"].dt.to_period("W").apply(lambda p: p.start_time.date())
            trend = ts.groupby("period").size().reset_index(name="Applications")
            fig = px.area(trend, x="period", y="Applications", color_discrete_sequence=[NAVY])
            fig.update_traces(line=dict(color=NAVY, width=2), fillcolor="rgba(11,37,69,0.15)",
                               hovertemplate="%{x}<br>Applications: %{y:,}<extra></extra>")
            fig.update_layout(xaxis_title=None, yaxis_title="Applications Submitted")
            apply_theme(fig, 340)
            st.plotly_chart(fig, use_container_width=True, config={"displayModeBar": False})
            peak_day = trend.loc[trend["Applications"].idxmax()]
            insight(f"Peak submission activity occurred on <b>{peak_day['period']}</b> with "
                    f"<b>{fmt_num(peak_day['Applications'])}</b> applications submitted. Data spans "
                    f"<b>{ts['Form Submission Time (parsed)'].min().date()}</b> to "
                    f"<b>{ts['Form Submission Time (parsed)'].max().date()}</b>.")
        else:
            empty_state("No valid submission timestamps available in the current filtered scope.")

        colE, colF = st.columns(2)
        with colE:
            section_title("Relocation Willingness")
            col_reloc = "Are you willing to relocate if Physical/Hybrid Incubation is required?"
            if col_reloc in fdf.columns:
                rc = fdf[col_reloc].fillna("Not Specified").value_counts()
                fig = px.pie(values=rc.values, names=rc.index, hole=0.5, color_discrete_sequence=CHART_SEQUENCE)
                fig.update_traces(textinfo="percent+label", hovertemplate="%{label}<br>%{value:,} (%{percent})<extra></extra>")
                apply_theme(fig, 320)
                fig.update_layout(showlegend=False)
                st.plotly_chart(fig, use_container_width=True, config={"displayModeBar": False})
        with colF:
            section_title("Preferred Incubation Mode")
            mc = fdf["Preferred Incubation Mode"].value_counts()
            mc = mc[mc.index != "Not Specified"]
            if len(mc):
                fig = px.bar(x=mc.index, y=mc.values, color_discrete_sequence=[NAVY, AMBER])
                fig.update_traces(hovertemplate="%{x}<br>Applications: %{y:,}<extra></extra>")
                fig.update_layout(xaxis_title=None, yaxis_title="Applications")
                apply_theme(fig, 320)
                st.plotly_chart(fig, use_container_width=True, config={"displayModeBar": False})

        insight(f"Conversion Insight: <b>{fmt_pct(k['active'], k['total'])}</b> of applications are currently "
                f"<b>Active</b> under Round Status.")


    # ---- TAB: Startup Ecosystem ---------------------------------------------
    with tabs[2]:
        rcol1, rcol2 = st.columns([3, 1])
        with rcol1:
            section_title("Startup Sector Composition", "Multi-select field — an application may map to more than one sector")
        with rcol2:
            sec_rank_mode = rank_control("sector_rank_mode")
        sector_all = apply_rank(pd.Series([s for lst in fdf["Sector List"] for s in lst]).value_counts(), sec_rank_mode)
        if len(sector_all):
            fig = ranked_bar_chart(sector_all, NAVY, max_label_len=38)
            apply_theme(fig, max(360, 30 * len(sector_all)))
            st.plotly_chart(fig, use_container_width=True, config={"displayModeBar": False})
            top_sec, bot_sec = sector_all.idxmax(), sector_all.idxmin()
            st.caption(f"Highest representation: **{short_label(top_sec, 60)}** "
                       f"({fmt_num(sector_all.max())}) · Lowest shown: "
                       f"**{short_label(bot_sec, 60)}** ({fmt_num(sector_all.min())})")
        else:
            empty_state()

        colA, colB = st.columns(2)
        with colA:
            rcol1b, rcol2b = st.columns([3, 1])
            with rcol1b:
                section_title("Technology Areas in Use")
            with rcol2b:
                tech_rank_mode = rank_control("tech_rank_mode")
            tech_all = apply_rank(pd.Series([t for lst in fdf["Technology List"] for t in lst]).value_counts(), tech_rank_mode)
            if len(tech_all):
                fig = ranked_bar_chart(tech_all, AMBER, max_label_len=28)
                apply_theme(fig, max(400, 28 * len(tech_all)))
                st.plotly_chart(fig, use_container_width=True, config={"displayModeBar": False})
            else:
                empty_state()
        with colB:
            section_title("Innovation Type")
            ic = fdf["Innovation Type"].value_counts()
            ic = ic[ic.index != "Not Specified"]
            if len(ic):
                fig = px.pie(values=ic.values, names=ic.index, hole=0.5, color_discrete_sequence=CHART_SEQUENCE)
                fig.update_traces(textinfo="percent+label", hovertemplate="%{label}<br>%{value:,} (%{percent})<extra></extra>")
                apply_theme(fig, 300)
                fig.update_layout(showlegend=False)
                st.plotly_chart(fig, use_container_width=True, config={"displayModeBar": False})

            section_title("Technology Readiness Level (TRL)")
            trl = fdf["Technology Readiness Level (TRL)"].value_counts()
            trl = trl[trl.index != "Not Specified"]
            if len(trl):
                trl_order = sorted(trl.index, key=lambda x: int(re.search(r"TRL (\d+)", x).group(1))
                                    if re.search(r"TRL (\d+)", x) else 99)
                fig = px.bar(x=[t.split(" (")[0] for t in trl_order], y=[trl[t] for t in trl_order],
                             color_discrete_sequence=[NAVY_MID])
                fig.update_traces(hovertemplate="%{x}<br>Applications: %{y:,}<extra></extra>")
                fig.update_layout(xaxis_title=None, yaxis_title="Applications")
                apply_theme(fig, 300)
                st.plotly_chart(fig, use_container_width=True, config={"displayModeBar": False})

        colC, colD = st.columns(2)
        with colC:
            section_title("Startup Stage Distribution")
            stg = fdf["Current Startup Stage"].value_counts()
            stg = stg[stg.index != "Not Specified"]
            if len(stg):
                fig = px.bar(x=stg.index, y=stg.values, color_discrete_sequence=[NAVY])
                fig.update_traces(hovertemplate="%{x}<br>Applications: %{y:,}<extra></extra>")
                fig.update_layout(xaxis_title=None, yaxis_title="Applications")
                apply_theme(fig, 340)
                st.plotly_chart(fig, use_container_width=True, config={"displayModeBar": False})
        with colD:
            section_title("Incorporation & DPIIT Status")
            inc_status = fdf["Is your startup incorporated?"].value_counts()
            dpiit = fdf["Is your startup DPIIT Registered?"].value_counts()
            combined = pd.DataFrame({
                "Status": list(inc_status.index) + list(dpiit.index),
                "Count": list(inc_status.values) + list(dpiit.values),
                "Field": ["Incorporated"] * len(inc_status) + ["DPIIT Registered"] * len(dpiit),
            })
            fig = px.bar(combined, x="Status", y="Count", color="Field", barmode="group",
                         color_discrete_sequence=[NAVY, AMBER])
            fig.update_traces(hovertemplate="%{x}<br>%{data.name}: %{y:,}<extra></extra>")
            fig.update_layout(xaxis_title=None, yaxis_title="Applications")
            apply_theme(fig, 340)
            st.plotly_chart(fig, use_container_width=True, config={"displayModeBar": False})

        section_title("Sector – Technology Landscape",
                       "Darker cells = more startups. Click a cell to filter by that sector and technology together.")
        pivot_st, kind_st = build_comparison(fdf, "Sector", "Technology", "Application Count", top_a=10, top_b=10)
        render_clean_heatmap(pivot_st, y_setter=select_sector, x_setter=select_technology,
                              value_label="Startups", x_max_len=20, y_max_len=32, key="sector_tech_hm")

        if pivot_st is not None and not pivot_st.empty:
            max_pos = np.unravel_index(np.argmax(pivot_st.values), pivot_st.values.shape)
            dom_sector = pivot_st.index[max_pos[0]]
            dom_tech = pivot_st.columns[max_pos[1]]
            dom_val = int(pivot_st.values[max_pos])
            insight(f"Strongest combination: <b>{short_label(dom_sector, 55)}</b> startups building with "
                    f"<b>{short_label(dom_tech, 40)}</b> — <b>{fmt_num(dom_val)}</b> startups, the highest "
                    f"concentration in this matrix.")
        sector_top1 = top_n_counts(fdf["Sector List"], n=1, explode=True)
        if len(sector_top1):
            insight(f"Sector Insight: <b>{short_label(sector_top1.index[0], 55)}</b> is the largest represented "
                    f"sector with <b>{fmt_num(sector_top1.iloc[0])}</b> tagged applications.")

        st.markdown("<br>", unsafe_allow_html=True)
        section_title("Startup Explorer", "Explore the startup portfolio by sector, state, stage and technology")

        r1c1, r1c2, r1c3, r1c4 = st.columns(4)
        with r1c1:
            exp_sector = st.selectbox(
                "Sector", ["All"] + sorted(set(s for lst in fdf["Sector List"] for s in lst) - {"Not Specified"}),
                key="exp_sector")
        with r1c2:
            exp_state = st.selectbox(
                "State", ["All"] + sorted([s for s in fdf["State"].unique() if s != "Not Specified"]),
                key="exp_state")
        with r1c3:
            exp_stage = st.selectbox(
                "Stage", ["All"] + sorted([s for s in fdf["Current Startup Stage"].unique() if s != "Not Specified"]),
                key="exp_stage")
        with r1c4:
            exp_tech = st.selectbox(
                "Technology", ["All"] + sorted(set(t for lst in fdf["Technology List"] for t in lst) - {"Not Specified"}),
                key="exp_tech")

        with st.expander("More filters — Incubation Mode, Innovation Type, TRL, Gender, Qualification"):
            r2c1, r2c2, r2c3, r2c4, r2c5 = st.columns(5)
            with r2c1:
                exp_mode = st.selectbox(
                    "Incubation Mode", ["All"] + sorted([m for m in fdf["Preferred Incubation Mode"].unique() if m != "Not Specified"]),
                    key="exp_mode")
            with r2c2:
                exp_innov = st.selectbox(
                    "Innovation Type", ["All"] + sorted([m for m in fdf["Innovation Type"].unique() if m != "Not Specified"]),
                    key="exp_innov")
            with r2c3:
                exp_trl = st.selectbox(
                    "TRL", ["All"] + sorted([m for m in fdf["Technology Readiness Level (TRL)"].unique() if m != "Not Specified"]),
                    key="exp_trl")
            with r2c4:
                exp_gender = st.selectbox(
                    "Gender", ["All"] + sorted([m for m in fdf["Gender"].unique() if m != "Not Specified"]),
                    key="exp_gender")
            with r2c5:
                exp_qual = st.selectbox(
                    "Qualification", ["All"] + sorted([m for m in fdf["Qualification Group"].unique() if m != "Not Specified"]),
                    key="exp_qual")

        explorer_df = fdf.copy()
        if exp_sector != "All":
            explorer_df = explorer_df[explorer_df["Sector List"].apply(lambda lst: exp_sector in lst)]
        if exp_state != "All":
            explorer_df = explorer_df[explorer_df["State"] == exp_state]
        if exp_stage != "All":
            explorer_df = explorer_df[explorer_df["Current Startup Stage"] == exp_stage]
        if exp_tech != "All":
            explorer_df = explorer_df[explorer_df["Technology List"].apply(lambda lst: exp_tech in lst)]
        if exp_mode != "All":
            explorer_df = explorer_df[explorer_df["Preferred Incubation Mode"] == exp_mode]
        if exp_innov != "All":
            explorer_df = explorer_df[explorer_df["Innovation Type"] == exp_innov]
        if exp_trl != "All":
            explorer_df = explorer_df[explorer_df["Technology Readiness Level (TRL)"] == exp_trl]
        if exp_gender != "All":
            explorer_df = explorer_df[explorer_df["Gender"] == exp_gender]
        if exp_qual != "All":
            explorer_df = explorer_df[explorer_df["Qualification Group"] == exp_qual]

        st.caption(f"{fmt_num(len(explorer_df))} startups match the current exploration filters")

        if len(explorer_df) == 0:
            empty_state()
        else:
            display_cols = ["ApplicationId", "Startup Name", "State", "Startup Sector", "Current Startup Stage",
                             "Round Status", "Incubator 1 Name"]
            table_view = explorer_df[display_cols].head(500).rename(columns={"Incubator 1 Name": "Preferred Incubator"})
            sel = st.dataframe(table_view, use_container_width=True, hide_index=True,
                                on_select="rerun", selection_mode="single-row", key="startup_table")
            selected_rows = sel.get("selection", {}).get("rows", []) if isinstance(sel, dict) else \
                sel.selection.rows if hasattr(sel, "selection") else []
            if selected_rows:
                app_id = table_view.iloc[selected_rows[0]]["ApplicationId"]
                srow = explorer_df[explorer_df["ApplicationId"] == app_id].iloc[0]
                section_title(f"Startup Profile — {srow['Startup Name']}")
                pc1, pc2 = st.columns([1, 1])
                with pc1:
                    st.markdown(f"""
                    <div class="profile-card">
                        <h4>{srow['Startup Name']}</h4>
                        <p style="color:{TEXT_MUTED}; font-size:13px;">{srow['State']}, {srow.get('City','')}</p>
                        <span class="tag">Stage: {srow['Current Startup Stage']}</span>
                        <span class="tag">Round Status: {srow['Round Status']}</span>
                        <span class="tag">Innovation: {srow['Innovation Type']}</span>
                        <span class="tag">TRL: {srow['Technology Readiness Level (TRL)']}</span>
                        <span class="tag">Incorporated: {srow.get('Is your startup incorporated?', 'N/A')}</span>
                        <span class="tag">DPIIT: {srow.get('Is your startup DPIIT Registered?', 'N/A')}</span>
                    </div>
                    """, unsafe_allow_html=True)
                with pc2:
                    st.markdown(f"""
                    <div class="profile-card">
                        <h4>Founder</h4>
                        <span class="tag">Gender: {srow['Gender']}</span>
                        <span class="tag">Qualification: {srow['Qualification Group']}</span>
                        <span class="tag">Occupation: {srow['Current Occupation']}</span>
                        <span class="tag">Time Allocation: {srow['Time allocation by founder on startup']}</span>
                        <p style="margin-top:10px; color:{TEXT_MUTED}; font-size:12.5px;">
                        Preference 1: <b>{srow['Preference 1']}</b><br>
                        Preference 2: <b>{srow['Preference 2']}</b></p>
                    </div>
                    """, unsafe_allow_html=True)
                if pd.notna(srow.get("Problem Statement")) or pd.notna(srow.get("Proposed Solution")):
                    section_title("Innovation Overview")
                    if pd.notna(srow.get("Problem Statement")):
                        st.markdown(f"**Problem Statement:** {srow['Problem Statement']}")
                    if pd.notna(srow.get("Proposed Solution")):
                        st.markdown(f"**Proposed Solution:** {srow['Proposed Solution']}")


    # ---- TAB: Geographic Intelligence ---------------------------------------
    with tabs[3]:
        k = compute_core_kpis(fdf)
        valid_state_df = fdf[fdf["State"] != "Not Specified"]
        state_counts_full = valid_state_df["State"].value_counts()
        top5 = state_counts_full.head(5).sum() if len(valid_state_df) else 0
        section_title("State-wise Application Volume",
                      f"{fmt_num(k['n_states'])} states/UTs represented — ranked by application volume")
        rc1, rc2 = st.columns([3, 1])
        with rc2:
            rmode = rank_control("state_rank", "Rank")
        with rc1:
            st.caption(f"Showing: {rmode}")
        plot_states = apply_rank(state_counts_full, rmode)
        if len(plot_states):
            fig = px.bar(x=plot_states.values, y=plot_states.index, orientation="h",
                         color=plot_states.values, color_continuous_scale=STATE_BAR_SCALE)
            fig.update_traces(hovertemplate="%{y}<br>Applications: %{x:,}<extra></extra>")
            fig.update_layout(yaxis=dict(autorange="reversed", title=None), xaxis_title="Applications",
                               coloraxis_showscale=False)
            apply_theme(fig, max(360, 24 * len(plot_states)))
            st.plotly_chart(fig, use_container_width=True, config={"displayModeBar": False})
        else:
            empty_state()

        section_title("State-wise Round Status Mix", "Top 12 states by volume")
        top12_states = state_counts_full.head(12).index.tolist()
        ss = fdf[fdf["State"].isin(top12_states)]
        if len(ss):
            pivot = ss.groupby(["State", "Round Status"]).size().reset_index(name="Count")
            fig = px.bar(pivot, x="State", y="Count", color="Round Status", barmode="stack",
                         category_orders={"State": top12_states},
                         color_discrete_map={"Active": NAVY, "Withdrawn": RED})
            fig.update_traces(hovertemplate="%{x}<br>%{data.name}: %{y:,}<extra></extra>")
            fig.update_layout(xaxis_tickangle=-30, xaxis_title=None, yaxis_title="Applications")
            apply_theme(fig, 380)
            st.plotly_chart(fig, use_container_width=True, config={"displayModeBar": False})
        else:
            empty_state()

        section_title("State × Top Sector Heatmap", "Top 10 states vs Top 8 sectors — click a cell to filter")
        pivot_hm, kind_hm = build_comparison(fdf, "State", "Sector", "Application Count", top_a=10, top_b=8)
        render_clean_heatmap(pivot_hm, y_setter=select_state, x_setter=select_sector,
                              value_label="Applications", x_max_len=20, y_max_len=18, key="state_sector_hm")

        section_title("Geographic Insight")
        if len(valid_state_df):
            insight(f"The top participating state is <b>{state_counts_full.index[0]}</b> with "
                    f"<b>{fmt_num(state_counts_full.iloc[0])}</b> applications "
                    f"({fmt_pct(state_counts_full.iloc[0], len(valid_state_df))} of geo-tagged applications), "
                    f"while the top 5 states together contribute <b>{fmt_pct(top5, len(valid_state_df))}</b> of all applications.")


    # ---- TAB: Founder & Demographics -----------------------------------------
    with tabs[4]:
        c1, c2, c3, c4 = st.columns(4)
        with c1:
            kpi_card("Male Founders", fmt_num((fdf["Gender"] == "Male").sum()),
                      fmt_pct((fdf["Gender"] == "Male").sum(), len(fdf)))
        with c2:
            kpi_card("Female Founders", fmt_num((fdf["Gender"] == "Female").sum()),
                      fmt_pct((fdf["Gender"] == "Female").sum(), len(fdf)))
        with c3:
            kpi_card("Other Genders", fmt_num((~fdf["Gender"].isin(["Male", "Female"])).sum()))
        with c4:
            kpi_card("Qualification Categories",
                      fmt_num(fdf.loc[fdf["Qualification Group"] != "Not Specified", "Qualification Group"].nunique()))

        colA, colB = st.columns(2)
        with colA:
            section_title("Founder Gender Distribution")
            gc = fdf["Gender"].value_counts()
            fig = px.bar(x=gc.index, y=gc.values, color_discrete_sequence=[NAVY, AMBER, "#8AA6C2"])
            fig.update_traces(hovertemplate="%{x}<br>Founders: %{y:,}<extra></extra>")
            fig.update_layout(xaxis_title=None, yaxis_title="Founders")
            apply_theme(fig, 340)
            st.plotly_chart(fig, use_container_width=True, config={"displayModeBar": False})
        with colB:
            section_title("Founder Qualification (Grouped)", "Free-text responses grouped into standard categories")
            qc = fdf["Qualification Group"].value_counts()
            qc = qc[qc.index != "Not Specified"]
            order = ["PhD", "Postgraduate", "Graduate", "Undergraduate / Diploma", "12th / Intermediate",
                     "10th & Below", "Other / Unspecified"]
            qc = qc.reindex([o for o in order if o in qc.index]).dropna()
            if len(qc):
                fig = px.bar(x=qc.values, y=qc.index, orientation="h", color_discrete_sequence=[NAVY])
                fig.update_traces(hovertemplate="%{y}<br>Founders: %{x:,}<extra></extra>")
                fig.update_layout(yaxis=dict(autorange="reversed", title=None), xaxis_title="Founders")
                apply_theme(fig, 340)
                st.plotly_chart(fig, use_container_width=True, config={"displayModeBar": False})

        colC, colD = st.columns(2)
        with colC:
            section_title("Current Occupation")
            occ = fdf["Current Occupation"].value_counts()
            occ = occ[occ.index != "Not Specified"]
            if len(occ):
                fig = px.pie(values=occ.values, names=occ.index, hole=0.5, color_discrete_sequence=CHART_SEQUENCE)
                fig.update_traces(textinfo="percent+label", hovertemplate="%{label}<br>%{value:,} (%{percent})<extra></extra>")
                apply_theme(fig, 340)
                fig.update_layout(showlegend=False)
                st.plotly_chart(fig, use_container_width=True, config={"displayModeBar": False})
        with colD:
            section_title("Founder Time Allocation on Startup")
            ta = fdf["Time allocation by founder on startup"].value_counts()
            ta = ta[ta.index != "Not Specified"]
            if len(ta):
                fig = px.bar(x=ta.index, y=ta.values, color_discrete_sequence=[AMBER, NAVY])
                fig.update_traces(hovertemplate="%{x}<br>Founders: %{y:,}<extra></extra>")
                fig.update_layout(xaxis_title=None, yaxis_title="Founders")
                apply_theme(fig, 340)
                st.plotly_chart(fig, use_container_width=True, config={"displayModeBar": False})

        section_title("Gender × Occupation")
        cross = fdf[fdf["Current Occupation"] != "Not Specified"].groupby(["Current Occupation", "Gender"]).size().reset_index(name="Count")
        if len(cross):
            fig = px.bar(cross, x="Current Occupation", y="Count", color="Gender", barmode="group",
                         color_discrete_map={"Male": NAVY, "Female": AMBER, "Others": "#8AA6C2"})
            fig.update_traces(hovertemplate="%{x}<br>%{data.name}: %{y:,}<extra></extra>")
            fig.update_layout(xaxis_title=None, yaxis_title="Founders")
            apply_theme(fig, 360)
            st.plotly_chart(fig, use_container_width=True, config={"displayModeBar": False})

        female_pct = fmt_pct((fdf["Gender"] == "Female").sum(), len(fdf))
        insight(f"Female founder representation stands at <b>{female_pct}</b> of the current scope. "
                f"The most common qualification group is <b>{qc.index[0] if len(qc) else 'N/A'}</b>, and the "
                f"dominant occupation is <b>{occ.index[0] if len(occ) else 'N/A'}</b> "
                f"({fmt_pct(occ.iloc[0], len(fdf)) if len(occ) else '0%'} of applicants).")


    # ---- TAB: Incubator Intelligence ------------------------------------------
    with tabs[5]:
        pref1_valid = fdf[fdf["Incubator 1 Name"] != "Not Specified"]
        inc_dir_scope = build_incubator_directory(fdf)

        c1, c2, c3, c4 = st.columns(4)
        with c1:
            kpi_card("Incubators Engaged", fmt_num(inc_dir_scope["Incubator"].nunique()), "Via Preference 1")
        with c2:
            kpi_card("Same Incubator Both Prefs.", fmt_num(fdf["Same Incubator Both Preferences"].sum()),
                      fmt_pct(fdf["Same Incubator Both Preferences"].sum(), len(fdf)))
        with c3:
            if len(inc_dir_scope):
                top_row = inc_dir_scope.iloc[0]
                kpi_card("Top Incubator (Pref. 1)", top_row["Incubator"], f"{fmt_num(top_row['Applications'])} applications")
            else:
                kpi_card("Top Incubator (Pref. 1)", "N/A")
        with c4:
            top10_share = inc_dir_scope["Applications"].head(10).sum() if len(inc_dir_scope) else 0
            kpi_card("Top-10 Incubator Concentration",
                      fmt_pct(top10_share, len(pref1_valid)) if len(pref1_valid) else "0%",
                      "Share of Pref. 1 applications")

        section_title("Incubator Map", "Bubble size = number of incubators · colour = applications received. Click a state to drill down.")
        state_metrics_inc = compute_state_metrics(fdf, ALL_GEO_STATE_NAMES)
        inc_event = render_incubator_map(inc_dir_scope, geojson, state_metrics_inc, key="incubator_map_chart")
        _handle_point_click(inc_event, select_state, name_field_index=0)

        section_title("Incubator Ranking")
        rcol1, rcol2 = st.columns([1, 1])
        with rcol1:
            rank_measure = st.selectbox("Rank by", ["Applications", "Active", "Active Rate"], key="inc_rank_measure")
        with rcol2:
            rank_mode = st.selectbox("Show", ["Top 10", "Top 5", "Bottom 10", "Bottom 5", "All"], key="inc_rank_mode")
        if len(inc_dir_scope):
            ranked = inc_dir_scope.sort_values(rank_measure, ascending=rank_mode.startswith("Bottom"))
            if rank_mode != "All":
                n = int(rank_mode.split()[1])
                ranked = ranked.head(n)
            fig = px.bar(ranked.sort_values(rank_measure), x=rank_measure, y="Incubator", orientation="h",
                         color_discrete_sequence=[NAVY])
            fig.update_traces(hovertemplate="%{y}<br>" + rank_measure + ": %{x:,.1f}<extra></extra>")
            fig.update_layout(yaxis=dict(title=None), xaxis_title=rank_measure)
            apply_theme(fig, max(340, 24 * len(ranked)))
            st.plotly_chart(fig, use_container_width=True, config={"displayModeBar": False})
        else:
            empty_state()

        if f_incubator and len(f_incubator) == 1 and f_incubator[0] in inc_dir_full["Incubator"].values:
            section_title(f"Incubator Profile — {f_incubator[0]}")
            prof = inc_dir_full[inc_dir_full["Incubator"] == f_incubator[0]].iloc[0]
            pc1, pc2, pc3, pc4, pc5 = st.columns(5)
            with pc1:
                kpi_card("Applications", fmt_num(prof["Applications"]))
            with pc2:
                kpi_card("Active", fmt_num(prof["Active"]))
            with pc3:
                kpi_card("Withdrawn", fmt_num(prof["Withdrawn"]))
            with pc4:
                kpi_card("Active Rate", f"{prof['Active Rate']:.1f}%")
            with pc5:
                kpi_card("Applicant States", fmt_num(prof["Applicant States"]))

            prof_scope = df[df["Incubator 1 Name"] == f_incubator[0]]
            pcol1, pcol2 = st.columns(2)
            with pcol1:
                st.markdown(f'<div class="profile-card"><h4>📍 {prof["City"]}, {prof["State"]}</h4>', unsafe_allow_html=True)
                sector_tags = top_n_counts(prof_scope["Sector List"], n=8, explode=True)
                st.markdown("**Top Sectors:** " + "".join(f'<span class="tag">{s} ({n})</span>' for s, n in sector_tags.items()) +
                             '</div>', unsafe_allow_html=True)
            with pcol2:
                st.markdown('<div class="profile-card"><h4>Startup Stage Mix</h4>', unsafe_allow_html=True)
                stage_tags = prof_scope["Current Startup Stage"].value_counts()
                stage_tags = stage_tags[stage_tags.index != "Not Specified"]
                st.markdown("".join(f'<span class="tag">{s} ({n})</span>' for s, n in stage_tags.items()) + '</div>',
                             unsafe_allow_html=True)

        section_title("Lowest Participating Incubators", "Among incubators with at least one application")
        if len(inc_dir_scope):
            p1_bottom = inc_dir_scope.sort_values("Applications", ascending=True).head(10)
            fig = px.bar(p1_bottom, x="Applications", y="Incubator", orientation="h", color_discrete_sequence=[RED])
            fig.update_traces(hovertemplate="%{y}<br>Applications: %{x:,}<extra></extra>")
            fig.update_layout(yaxis=dict(title=None), xaxis_title="Applications")
            apply_theme(fig, 360)
            st.plotly_chart(fig, use_container_width=True, config={"displayModeBar": False})
        else:
            empty_state()

        same_pref_df = fdf[fdf["Same Incubator Both Preferences"]]
        if len(same_pref_df):
            section_title("Applicants Selecting the Same Incubator for Both Preferences",
                          f"{fmt_num(len(same_pref_df))} applications ({fmt_pct(len(same_pref_df), len(fdf))} of scope)")
            sp = same_pref_df["Incubator 1 Name"].value_counts().head(10)
            fig = px.bar(x=sp.values, y=sp.index, orientation="h", color_discrete_sequence=[NAVY_MID])
            fig.update_traces(hovertemplate="%{y}<br>Applications: %{x:,}<extra></extra>")
            fig.update_layout(yaxis=dict(autorange="reversed", title=None), xaxis_title="Applications")
            apply_theme(fig, 320)
            st.plotly_chart(fig, use_container_width=True, config={"displayModeBar": False})

        if len(inc_dir_scope):
            insight(f"Incubator Insight: <b>{inc_dir_scope.iloc[0]['Incubator']}</b> has the highest number of "
                    f"Preference-1 applications (<b>{fmt_num(inc_dir_scope.iloc[0]['Applications'])}</b>).")


    # ---- TAB: Ecosystem Comparison --------------------------------------------
    with tabs[6]:
        section_title("Ecosystem Comparison Studio", "Choose any two dimensions and a measure — the engine "
                                                       "automatically selects the clearest chart type.")
        dim_options = list(DIMENSIONS.keys())
        # apply any pending preset selection BEFORE the widgets below are instantiated
        if "cs_pending_a" in st.session_state:
            st.session_state["cs_dim_a"] = st.session_state.pop("cs_pending_a")
        if "cs_pending_b" in st.session_state:
            st.session_state["cs_dim_b"] = st.session_state.pop("cs_pending_b")
        if "cs_dim_a" not in st.session_state:
            st.session_state["cs_dim_a"] = dim_options[0]
        if "cs_dim_b" not in st.session_state:
            st.session_state["cs_dim_b"] = dim_options[2]

        cc1, cc2, cc3 = st.columns(3)
        with cc1:
            dim_a = st.selectbox("Dimension A", dim_options, key="cs_dim_a")
        with cc2:
            dim_b = st.selectbox("Dimension B", dim_options, key="cs_dim_b")
        with cc3:
            measure = st.selectbox("Measure", MEASURES, key="cs_measure")

        if dim_a == dim_b:
            st.info("Dimension A and Dimension B are the same — showing a single-dimension breakdown instead.")
            long_a = dimension_long(fdf, dim_a)
            counts = long_a["_val"].value_counts().head(15)
            if len(counts):
                fig = ranked_bar_chart(counts, NAVY, x_title="Application Count", max_label_len=34)
                apply_theme(fig, max(360, 26 * len(counts)))
                st.plotly_chart(fig, use_container_width=True, config={"displayModeBar": False})
            else:
                empty_state()
        else:
            pivot, kind = build_comparison(fdf, dim_a, dim_b, measure)
            chart_label = {"heatmap": "Heatmap", "stacked_bar": "Stacked Bar Chart", "bar": "Bar Chart"}.get(kind, "Chart")
            st.caption(f"Auto-selected visualisation: **{chart_label}** "
                       f"(based on the cardinality of {dim_a} × {dim_b})")
            render_comparison(pivot, kind, dim_a, dim_b, measure)

        st.markdown("<br>", unsafe_allow_html=True)
        section_title("Suggested Combinations", "Click any preset to load it instantly")
        presets = [("State", "Sector"), ("State", "Technology"), ("Incubator (Preference 1)", "Sector"),
                   ("Sector", "Technology"), ("Gender", "Sector"), ("Sector", "Startup Stage")]
        preset_cols = st.columns(len(presets))
        for i, (pa, pb) in enumerate(presets):
            with preset_cols[i]:
                if st.button(f"{pa} × {pb}", key=f"preset_{i}", use_container_width=True):
                    st.session_state["cs_pending_a"] = pa
                    st.session_state["cs_pending_b"] = pb
                    st.rerun()



# =============================================================================
# MAIN DISPATCH
# =============================================================================

render_dashboard(fdf, df, india_geojson, incubator_directory_full)

# =============================================================================
# FOOTER
# =============================================================================
st.markdown(f"""
<div style="text-align:center; color:{TEXT_MUTED}; font-size:11px; margin-top:24px; padding:14px;
            border-top:1px solid {BORDER};">
GENESIS EIR Grant — India Startup Ecosystem Intelligence Platform &nbsp;|&nbsp;
Generated from uploaded application data &nbsp;|&nbsp; All figures computed directly from source records
</div>
""", unsafe_allow_html=True)