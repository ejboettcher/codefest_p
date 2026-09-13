import io
import uuid
 
import altair as alt
import numpy as np
import pandas as pd
import streamlit as st
# ---------------------------------------------------------------------------
# Helpers: data
# ---------------------------------------------------------------------------
ROW_COLUMNS = ["Type", "Quantity", "Unit Cost"]


def norm(value) -> str:
    """Normalise a type label so 'SUV', ' suv ' and 'Suv' all match."""
    return str(value).strip().lower()
 
 
def empty_rows() -> pd.DataFrame:
    return pd.DataFrame(
        {
            "Type": pd.Series(dtype="object"),
            "Quantity": pd.Series(dtype="int64"),
            "Unit Cost": pd.Series(dtype="float64"),
        }
    )
 
 
@st.cache_data(show_spinner=False)
def load_dataset(file_bytes: bytes, file_name: str) -> pd.DataFrame:
    if file_name.lower().endswith((".xlsx", ".xls")):
        return pd.read_excel(io.BytesIO(file_bytes))
    return pd.read_csv(io.BytesIO(file_bytes))
 
 
def guess_column(columns, keywords):
    for kw in keywords:
        for col in columns:
            if kw in str(col).lower():
                return col
    return columns[0] if len(columns) else None
 
 
def compute_type_stats(df: pd.DataFrame, type_col: str, cost_col: str) -> pd.DataFrame:
    """Count, mean, standard deviation, min and max of cost for each type."""
    d = df[[type_col, cost_col]].copy()
    d[cost_col] = pd.to_numeric(d[cost_col], errors="coerce")
    d = d.dropna()
    d["label"] = d[type_col].astype(str).str.strip()
    d["key"] = d["label"].str.lower()
    stats = (
        d.groupby("key")
        .agg(
            Type=("label", "first"),
            n=(cost_col, "count"),
            mean=(cost_col, "mean"),
            std=(cost_col, "std"),  # sample standard deviation (ddof=1)
            min=(cost_col, "min"),
            max=(cost_col, "max"),
        )
        .reset_index()
        .sort_values("Type")
    )
    return stats
 
 
def apply_editor_changes(base: pd.DataFrame, state) -> pd.DataFrame:
    """Apply st.data_editor's pending edits/additions/deletions to the base rows."""
    df = base.copy().reset_index(drop=True)
    if not state:
        return df
 
    for idx, changes in state.get("edited_rows", {}).items():
        i = int(idx)
        if i < len(df):
            for col, val in changes.items():
                if col in df.columns:
                    df.at[i, col] = val
 
    deleted = [int(i) for i in state.get("deleted_rows", []) if int(i) < len(df)]
    if deleted:
        df = df.drop(index=deleted)
 
    added = state.get("added_rows", [])
    if added:
        df = pd.concat([df, pd.DataFrame(added).reindex(columns=ROW_COLUMNS)], ignore_index=True)
 
    return df.reset_index(drop=True)[ROW_COLUMNS]
 
 
def clean_rows(df: pd.DataFrame) -> pd.DataFrame:
    """Drop incomplete rows and coerce numbers so the totals are safe to compute."""
    df = df.copy()
    df["Type"] = df["Type"].astype("string").str.strip()
    df = df[df["Type"].notna() & (df["Type"] != "")]
    df["Quantity"] = pd.to_numeric(df["Quantity"], errors="coerce").fillna(0)
    df["Unit Cost"] = pd.to_numeric(df["Unit Cost"], errors="coerce").fillna(0.0)
    return df
 
 
# ---------------------------------------------------------------------------
# Helpers: session state for the sidebar groups
# ---------------------------------------------------------------------------
def make_group(name) -> dict:
    gid = uuid.uuid4().hex[:8]
    st.session_state[f"qty_{gid}"] = 1
    st.session_state[f"cost_{gid}"] = 0.0
    return {"id": gid, "name": str(name), "rows": empty_rows(), "version": 0}
 
 
def editor_key(group: dict) -> str:
    # The version bumps whenever rows are added programmatically, which gives
    # the editor a fresh identity so it picks up the new base data cleanly.
    return f"editor_{group['id']}_{group['version']}"
 
 
def find_group(gid: str) -> dict:
    return next(g for g in st.session_state.groups if g["id"] == gid)
 
 
def commit_rows(group: dict, new_rows: pd.DataFrame) -> None:
    st.session_state.pop(editor_key(group), None)
    group["rows"] = new_rows
    group["version"] += 1
 
 

def on_add_row(gid: str) -> None:
    """Add a row built from selection boxes to the specified group."""
    group = find_group(gid)
    current = apply_editor_changes(group["rows"], st.session_state.get(editor_key(group)))
    new_row = pd.DataFrame(
        [
            {
                "Type": st.session_state[f"type_{gid}"],
                "Quantity": int(st.session_state[f"qty_{gid}"]),
                "Unit Cost": float(st.session_state[f"cost_{gid}"]),
            }
        ]
    )
    commit_rows(group, pd.concat([current, new_row], ignore_index=True))


def on_clear_group(gid: str) -> None:
    """Clear all rows from a group."""
    commit_rows(find_group(gid), empty_rows())


def on_remove_group(gid: str) -> None:
    """Remove a group entirely from session state."""
    group = find_group(gid)
    st.session_state.pop(editor_key(group), None)
    for prefix in ("type_", "qty_", "cost_"):
        st.session_state.pop(f"{prefix}{gid}", None)
    st.session_state.groups = [g for g in st.session_state.groups if g["id"] != gid]


def on_add_group() -> None:
    """Append a new line-item builder group."""
    st.session_state.group_counter += 1
    st.session_state.groups.append(make_group(f"New Group {st.session_state.group_counter}"))


def on_type_change(gid: str) -> None:
    """Pre-fill the unit cost with the dataset average for the chosen type."""
    mean = st.session_state.get("type_means", {}).get(norm(st.session_state[f"type_{gid}"]))
    if mean is not None and not np.isnan(mean):
        st.session_state[f"cost_{gid}"] = round(float(mean), 2)
