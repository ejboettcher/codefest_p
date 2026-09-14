import io
import json
import uuid

import altair as alt
import numpy as np
import pandas as pd
import streamlit as st
# ---------------------------------------------------------------------------
# Helpers: data
# ---------------------------------------------------------------------------
ROW_COLUMNS = ["Type", "Quantity", "Unit Cost"]
FM_CONFIG_COLUMNS = ["Group", "Type", "Per Day"]
DEFAULT_FM_CONFIG_PATH = "config/fm_items.csv"


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
 
 
def copy_table_html(df: pd.DataFrame, label: str = "📋 Copy table") -> str:
    """A small self-contained button that copies `df` (tab-separated, so it
    pastes into a spreadsheet as columns) to the clipboard.

    st.dataframe's built-in toolbar (search / download / fullscreen) has no
    slot for a custom "copy" icon, so this renders as a standalone button via
    st.iframe instead, placed next to the table.
    """
    tsv = df.to_csv(sep="\t", index=False)
    payload = json.dumps(tsv)
    button_id = f"copy-btn-{uuid.uuid4().hex[:8]}"
    return f"""
    <div style="font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', sans-serif;">
      <button id="{button_id}" style="
        font-size: 14px; padding: 0.35rem 0.9rem; border-radius: 0.5rem;
        border: 1px solid rgba(49, 51, 63, 0.2); background: transparent;
        cursor: pointer; color: inherit;">{label}</button>
    </div>
    <script>
      (function() {{
        const text = {payload};
        const btn = document.getElementById("{button_id}");
        const original = btn.textContent;
        btn.addEventListener("click", async function() {{
          try {{
            await navigator.clipboard.writeText(text);
          }} catch (err) {{
            const ta = document.createElement("textarea");
            ta.value = text;
            ta.style.position = "fixed";
            ta.style.opacity = "0";
            document.body.appendChild(ta);
            ta.focus();
            ta.select();
            document.execCommand("copy");
            document.body.removeChild(ta);
          }}
          btn.textContent = "Copied!";
          setTimeout(() => {{ btn.textContent = original; }}, 1200);
        }});
      }})();
    </script>
    """


def clean_rows(df: pd.DataFrame) -> pd.DataFrame:
    """Drop incomplete rows and coerce numbers so the totals are safe to compute."""
    df = df.copy()
    df["Type"] = df["Type"].astype("string").str.strip()
    df = df[df["Type"].notna() & (df["Type"] != "")]
    df["Quantity"] = pd.to_numeric(df["Quantity"], errors="coerce").fillna(0)
    df["Unit Cost"] = pd.to_numeric(df["Unit Cost"], errors="coerce").fillna(0.0)
    return df
 
 
# ---------------------------------------------------------------------------
# Helpers: FM_ITEMS config (which groups/types exist, and which scale by Days)
# ---------------------------------------------------------------------------
def _to_bool(value) -> bool:
    """Parse a CSV/editor cell as a boolean (TRUE/FALSE, yes/no, 1/0, ...)."""
    if isinstance(value, bool):
        return value
    if pd.isna(value):
        return False
    return str(value).strip().lower() in {"true", "1", "yes", "y", "days", "daily"}


def empty_fm_config() -> pd.DataFrame:
    return pd.DataFrame(
        {
            "Group": pd.Series(dtype="object"),
            "Type": pd.Series(dtype="object"),
            "Per Day": pd.Series(dtype="bool"),
        }
    )


def clean_fm_config(df: pd.DataFrame) -> pd.DataFrame:
    """Drop incomplete rows and coerce types after a CSV load or in-app edit."""
    df = df.copy()
    for col in FM_CONFIG_COLUMNS:
        if col not in df.columns:
            df[col] = False if col == "Per Day" else ""
    df["Group"] = df["Group"].astype("string").str.strip()
    df["Type"] = df["Type"].astype("string").str.strip()
    df = df[df["Group"].notna() & (df["Group"] != "") & df["Type"].notna() & (df["Type"] != "")]
    df["Per Day"] = df["Per Day"].apply(_to_bool)
    # Last edit for a given (Group, Type) pair wins; keep first-seen order.
    df = df.drop_duplicates(subset=["Group", "Type"], keep="last")
    return df.reset_index(drop=True)[FM_CONFIG_COLUMNS]


def load_fm_config(path_or_buffer) -> pd.DataFrame:
    """Load the Group/Type/Per Day config from a CSV file path or uploaded file."""
    df = pd.read_csv(path_or_buffer)
    df.columns = [str(c).strip() for c in df.columns]
    return clean_fm_config(df)


def add_type_to_config(config: pd.DataFrame, group: str, type_name: str, per_day: bool = False) -> pd.DataFrame:
    """Append a new (Group, Type) row, unless that pair is already present."""
    group = str(group).strip()
    type_name = str(type_name).strip()
    exists = (
        (config["Group"].str.lower() == group.lower()) & (config["Type"].str.lower() == type_name.lower())
    ).any()
    if exists or not type_name:
        return config
    new_row = pd.DataFrame([{"Group": group, "Type": type_name, "Per Day": per_day}])
    return clean_fm_config(pd.concat([config, new_row], ignore_index=True))


def fm_items_from_config(config: pd.DataFrame) -> dict:
    """Group -> ordered list of unique type names, for the sidebar dropdowns."""
    items = {}
    for group, sub in config.groupby("Group", sort=False):
        seen = []
        for t in sub["Type"]:
            if t not in seen:
                seen.append(t)
        items[group] = seen
    return items


def type_multiplier_flags(config: pd.DataFrame) -> dict:
    """norm(type) -> True if that type's cost should scale with Days, not a flat 1x."""
    return {norm(t): bool(p) for t, p in zip(config["Type"], config["Per Day"])}


def cost_multiplier(type_key: str, flags: dict, days) -> float:
    """The factor a line's Quantity × Unit Cost is scaled by: `days` if flagged, else 1."""
    return float(days) if flags.get(type_key, False) else 1.0


def days_between(start, end) -> int:
    """Inclusive day count from start to end (a single day counts as 1).

    Returns 0 if either date is missing or end is before start.
    """
    if start is None or end is None or end < start:
        return 0
    return (end - start).days + 1


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
