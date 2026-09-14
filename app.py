"""
Vehicle Cost Estimator (PACES)
Run with: streamlit run app.py
"""

from datetime import date

from PIL import Image
import altair as alt
import numpy as np
import pandas as pd
import streamlit as st

# Import our helper module functions and constants
import app_helper as helper

st.set_page_config(page_title="PACES", layout="wide")

st.logo("static/img/pacaf_money_logo.png", size="medium",
       icon_image="static/img/pacaf_money_logo.png")

# Bold, larger, Air Force blue styling for the titles above each results
# table. Scoped to just these three (via the anchor/key hooks below) rather
# than every st.subheader/st.expander in the app.
#
# Note: this can't reach the column-header row *inside* st.dataframe /
# st.data_editor (e.g. "Type", "Units", "Total cost") — that row is painted
# on a <canvas> by Streamlit's grid component from its theme, not real HTML,
# so no CSS selector can touch it.
AIR_FORCE_BLUE = "#00308F"
st.markdown(
    f"""
    <style>
    #totals-by-type,
    .st-key-all_line_items summary,
    .st-key-dataset_cost_stats summary {{
        font-weight: 700 !important;
        font-size: 1.35rem !important;
        color: {AIR_FORCE_BLUE} !important;
    }}
    </style>
    """,
    unsafe_allow_html=True,
)

def update_widget_state(gid, new_value):
    # This runs BEFORE the script executes top-to-bottom, avoiding the exception
    st.session_state[f"type_{gid}"] = new_value.strip()

# ---------------------------------------------------------------------------
# Session State Initialization
# ---------------------------------------------------------------------------
# FM_ITEMS (which Group each Type belongs to, and whether its cost scales with
# Days) is loaded once from a CSV config file, then kept in session state so
# it can be edited in-app or replaced by uploading a different CSV.
if "fm_config" not in st.session_state:
    try:
        st.session_state.fm_config = helper.load_fm_config(helper.DEFAULT_FM_CONFIG_PATH)
    except Exception:  # noqa: BLE001 - missing/bad file: start from an empty config
        st.session_state.fm_config = helper.empty_fm_config()

st.session_state.setdefault("start_date", date.today())
st.session_state.setdefault("end_date", date.today())
st.session_state.setdefault("days", 1)

# Everything below is derived fresh from fm_config on every rerun, so edits
# made in the "Manage cost groups & types" panel take effect immediately.
FM_ITEMS = helper.fm_items_from_config(st.session_state.fm_config)
GROUPS = list(FM_ITEMS.keys())
DEFAULT_TYPES = [item for types in FM_ITEMS.values() for item in types]
TYPE_PER_DAY = helper.type_multiplier_flags(st.session_state.fm_config)

if "groups" not in st.session_state:
    st.session_state.group_counter = len(GROUPS)
    st.session_state.groups = [helper.make_group(i) for i in GROUPS]

# Cached dataset loading mapped to helper function
@st.cache_data(show_spinner=False)
def load_dataset_cached(file_bytes: bytes, file_name: str) -> pd.DataFrame:
    return helper.load_dataset(file_bytes, file_name)

# ---------------------------------------------------------------------------
# Sidebar: dataset upload
# ---------------------------------------------------------------------------
with st.sidebar:
    image_path = "static/img/pacaf_money_logo.png"
    image = Image.open(image_path)
    left_co, cent_co, last_co = st.sidebar.columns([1, 2, 1])
    with cent_co:
        st.image(image, use_container_width=True)
    
    st.header("Cost Builder")

    d1, d2 = st.columns(2)
    d1.date_input("Start date", key="start_date")
    d2.date_input("End date", key="end_date")

    if st.session_state.end_date < st.session_state.start_date:
        st.error("End date is before start date — Days is treated as 0.")

    st.session_state.days = helper.days_between(st.session_state.start_date, st.session_state.end_date)
    st.caption(
        f"Days: **{st.session_state.days}** — types marked '× Days' below have their "
        "unit cost multiplied by this value instead of a flat 1x when totals are computed."
    )

    with st.expander("⚙️ Manage cost groups & types", expanded=False):
        st.caption(
            "Define the Group/Type options offered below. Check '× Days' for types "
            "whose cost should scale with the Days value above instead of a flat 1x."
        )
        config_upload = st.file_uploader(
            "Load from CSV", type=["csv"], key="fm_config_upload",
            help="Columns: Group, Type, Per Day (TRUE/FALSE).",
        )
        if config_upload is not None:
            upload_sig = (config_upload.name, config_upload.size)
            if st.session_state.get("_fm_config_upload_sig") != upload_sig:
                try:
                    st.session_state.fm_config = helper.load_fm_config(config_upload)
                    st.session_state._fm_config_upload_sig = upload_sig
                    st.rerun()
                except Exception as exc:  # noqa: BLE001
                    st.error(f"Couldn't read {config_upload.name}: {exc}")

        edited_config = st.data_editor(
            st.session_state.fm_config,
            key="fm_config_editor",
            num_rows="dynamic",
            hide_index=True,
            width="stretch",
            column_config={
                "Group": st.column_config.TextColumn("Group", required=True),
                "Type": st.column_config.TextColumn("Type", required=True),
                "Per Day": st.column_config.CheckboxColumn("× Days", default=True),
            },
        )
        cleaned_config = helper.clean_fm_config(edited_config)
        if not cleaned_config.equals(st.session_state.fm_config):
            # Rerun immediately so the Group/Type dropdowns below pick up the
            # edit right away, instead of lagging a run behind (Streamlit only
            # reflects a state change from the point it happens onward).
            st.session_state.fm_config = cleaned_config
            st.rerun()

        st.download_button(
            "Download config (CSV)",
            st.session_state.fm_config.to_csv(index=False).encode(),
            file_name="fm_items.csv",
            mime="text/csv",
            width="stretch",
        )

    uploaded = st.file_uploader(
        "Cost dataset (CSV or Excel)",
        type=["csv", "xlsx", "xls"],
        help="Needs one column with the vehicle type and one with the cost.",
    )
    
    dataset, stats = None, None
    if uploaded is not None:
        try:
            dataset = load_dataset_cached(uploaded.getvalue(), uploaded.name)
        except Exception as exc:  # noqa: BLE001
            st.error(f"Couldn't read {uploaded.name}: {exc}")
            
    if dataset is not None and not dataset.empty:
        numeric_cols = dataset.select_dtypes("number").columns.tolist()
        text_cols = [c for c in dataset.columns if c not in numeric_cols] or dataset.columns.tolist()
        if not numeric_cols:
            st.error("The dataset has no numeric column to use as cost.")
            dataset = None
        else:
            with st.expander("Dataset columns", expanded=False):
                default_type = helper.guess_column(text_cols, ["type", "category", "class", "segment", "body"])
                default_cost = helper.guess_column(numeric_cols, ["cost", "price", "amount", "value"])
                type_col = st.selectbox("Type column", text_cols, index=text_cols.index(default_type))
                cost_col = st.selectbox("Cost column", numeric_cols, index=numeric_cols.index(default_cost))
            
            stats = helper.compute_type_stats(dataset, type_col, cost_col)
            st.caption(f"Loaded {len(dataset):,} rows across {len(stats)} types.")

    st.session_state.type_means = {} if stats is None else dict(zip(stats["key"], stats["mean"]))
    type_stds = {} if stats is None else dict(zip(stats["key"], stats["std"]))
    
    # Dropdown options: dataset types (or defaults), plus any type already used in a row.
    type_options = list(stats["Type"]) if stats is not None else list(DEFAULT_TYPES)
    known = {helper.norm(t) for t in type_options}
    for g in st.session_state.groups:
        for t in g["rows"]["Type"].dropna():
            if helper.norm(t) not in known:
                type_options.append(t)
                known.add(helper.norm(t))

    st.divider()
    st.subheader("Line items")
    
    # -----------------------------------------------------------------------
    # Sidebar: one dropdown section per group
    # -----------------------------------------------------------------------
    group_tables = []
    for group in st.session_state.groups:
        gid = group["id"]
        with st.expander(group["name"], expanded=True):
            #--------
            # Types configured for this group in fm_config (the "Manage cost
            # groups & types" panel above), which is the single source of
            # truth for Group/Type options.
            current_type_options = FM_ITEMS.get(group["name"], list(DEFAULT_TYPES))

            # 2. Check for and process a newly submitted custom type
            # This input value comes from the st.text_input further down.
            new_option = st.session_state.get(f"new_input_{gid}", "").strip()
            if new_option and new_option not in current_type_options:
                # Persist the new option into fm_config for this group, so it
                # shows up in the config editor and survives reruns.
                st.session_state.fm_config = helper.add_type_to_config(
                    st.session_state.fm_config, group["name"], new_option
                )
                # Set the selectbox to this new option
                st.session_state[f"type_{gid}"] = new_option
                # Clear the text input for the next use
                st.session_state[f"new_input_{gid}"] = ""
                # Rerun to update the selectbox options and selection
                st.rerun()

            # 3. Prepare options for display and manage default selection
            display_options = current_type_options + ["+ Add new custom type..."]
            
            # Ensure the current selection is valid
            if st.session_state.get(f"type_{gid}") not in display_options:
                st.session_state[f"type_{gid}"] = display_options[0]
        
            # This seems to be a custom logic trigger, which is fine
            if st.session_state.get(f"cost_{gid}") == 0:
                helper.on_type_change(gid)
        
            # 4. Render the selectbox
            selected_option = st.selectbox(
                "Type",
                display_options,
                key=f"type_{gid}",
                on_change=helper.on_type_change,
                args=(gid,)
            )
        
            # 5. If the user wants to add a new type, show the text input box
            if selected_option == "+ Add new custom type...":
                st.text_input(
                    "Enter new type name and press Enter:",
                    key=f"new_input_{gid}"
                ) 

            #------------------
            c1, c2 = st.columns([1, 1.4])
            c1.number_input("Quantity", min_value=1, step=1, key=f"qty_{gid}")
            c2.number_input("Unit cost ($)", min_value=0.0, step=100.0, format="%.2f", key=f"cost_{gid}")
            
            sel_key = helper.norm(st.session_state[f"type_{gid}"])
            if sel_key in st.session_state.type_means:
                sd = type_stds.get(sel_key)
                sd_txt = f", σ ${sd:,.0f}" if sd is not None and not np.isnan(sd) else ""
                st.caption(f"Dataset average ${st.session_state.type_means[sel_key]:,.0f}{sd_txt}")
                
            st.button("Add row", key=f"add_{gid}", on_click=helper.on_add_row, args=(gid,),
                      type="primary", width="stretch")
            
            edited = st.data_editor(
                group["rows"],
                key=helper.editor_key(group),
                num_rows="dynamic",
                hide_index=True,
                width="stretch",
                column_config={
                    "Type": st.column_config.SelectboxColumn("Type", options=type_options, required=True),
                    "Quantity": st.column_config.NumberColumn("Qty", min_value=0, step=1, format="%d", required=True),
                    "Unit Cost": st.column_config.NumberColumn("Unit cost", min_value=0.0, format="dollar", required=True),
                },
            )
            group_tables.append(edited.assign(Group=group["name"]))
            
            b1, b2 = st.columns(2)
            b1.button("Clear rows", key=f"clear_{gid}", on_click=helper.on_clear_group, args=(gid,), width="stretch")
            if len(st.session_state.groups) > 1:
                b2.button("Remove group", key=f"remove_{gid}", on_click=helper.on_remove_group, args=(gid,), width="stretch")
                
    st.button("➕ Add group", on_click=helper.on_add_group, width="stretch")

# ---------------------------------------------------------------------------
# Main panel
# ---------------------------------------------------------------------------
st.title("PACES (Predictive Analytic Cost Execution Simulator)")

entries = helper.clean_rows(pd.concat(group_tables, ignore_index=True)) if group_tables else helper.clean_rows(helper.empty_rows())
entries["key"] = entries["Type"].map(helper.norm)
# Types flagged "× Days" in the group/type config scale by the Days value
# above instead of a flat 1x (e.g. a daily rate rather than a one-time cost).
days = st.session_state.get("days", 1)
entries["Multiplier"] = entries["key"].map(lambda k: helper.cost_multiplier(k, TYPE_PER_DAY, days))
entries["Line Total"] = entries["Quantity"] * entries["Unit Cost"] * entries["Multiplier"]

if entries.empty and stats is None:
    st.info(
        "Upload a cost dataset in the sidebar to see the spread of costs for each type, "
        "then pick a type, enter a quantity and unit cost, and select **Add row**."
    )
    st.stop()

# Per-type totals from the line items
by_type = (
    entries.groupby("key")
    .agg(Type=("Type", "first"), Units=("Quantity", "sum"), Total=("Line Total", "sum"))
    .reset_index()
)

# Join dataset statistics; outer join so every dataset type is listed
if stats is not None:
    summary = by_type.merge(
        stats[["key", "Type", "n", "mean", "std"]], on="key", how="outer", suffixes=("", "_ds")
    )
    summary["Type"] = summary["Type"].fillna(summary["Type_ds"])
    summary = summary.drop(columns="Type_ds")
else:
    summary = by_type.assign(n=np.nan, mean=np.nan, std=np.nan)

summary[["Units", "Total"]] = summary[["Units", "Total"]].fillna(0)
summary["Avg Unit Cost"] = np.where(summary["Units"] > 0, summary["Total"] / summary["Units"].replace(0, np.nan), np.nan)

# A type's total scales by its × Days multiplier, so its uncertainty does too.
summary["Multiplier"] = summary["key"].map(lambda k: helper.cost_multiplier(k, TYPE_PER_DAY, days))

# Calculate total deviation
summary["Total σ"] = summary["std"] * np.sqrt(summary["Units"]) * summary["Multiplier"]
summary = summary.sort_values(["Total", "Type"], ascending=[False, True]).reset_index(drop=True)

grand_total = float(entries["Line Total"].sum())
total_units = int(entries["Quantity"].sum())
combined_sigma = float(
    np.sqrt((summary["Units"] * summary["std"].fillna(0) ** 2 * summary["Multiplier"] ** 2).sum())
)

m1, m2, m3, m4 = st.columns(4)
m1.metric("Total cost", f"${grand_total:,.2f}")
m2.metric("Units", f"{total_units:,}")
m3.metric("Line items", f"{len(entries):,}")
m4.metric(
    "Total σ",
    f"±${combined_sigma:,.0f}" if stats is not None else "—",
    help="Estimated spread of the total cost, assuming each unit's cost varies "
    "independently with its type's standard deviation from the dataset: "
    "√Σ(units × σ × multiplier)², where multiplier is Days for '× Days' types, else 1.",
)

missing = summary[(summary["Units"] > 0) & summary["std"].isna()]["Type"].tolist()
if stats is None:
    st.caption("Upload a dataset to add standard deviations by type.")
elif missing:
    st.warning(
        "No standard deviation available for: " + ", ".join(missing)
        + ". These types are missing from the dataset or have only one cost record."
    )

st.subheader("Totals by type", anchor="totals-by-type")
summary_display_cols = {
    "Type": "Type",
    "Units": "Units",
    "Total": "Total cost",
    "Avg Unit Cost": "Avg unit cost (entered)",
    "mean": "Dataset mean",
    "std": "Dataset σ (per unit)",
    "n": "Dataset records",
    "Total σ": "σ of total",
}
st.dataframe(
    summary[list(summary_display_cols)],
    hide_index=True,
    width="stretch",
    column_config={
        "Units": st.column_config.NumberColumn("Units", format="%d"),
        "Total": st.column_config.NumberColumn("Total cost", format="dollar"),
        "Avg Unit Cost": st.column_config.NumberColumn("Avg unit cost (entered)", format="dollar"),
        "mean": st.column_config.NumberColumn("Dataset mean", format="dollar"),
        "std": st.column_config.NumberColumn("Dataset σ (per unit)", format="dollar"),
        "n": st.column_config.NumberColumn("Dataset records", format="%d"),
        "Total σ": st.column_config.NumberColumn(
            "σ of total", format="dollar", help="Dataset σ × √units × multiplier (Days for '× Days' types, else 1)"
        ),
    },
)
st.iframe(
    helper.copy_table_html(summary[list(summary_display_cols)].rename(columns=summary_display_cols)),
    height=44,
)

chart_df = summary[summary["Total"] > 0].rename(columns={"Total": "total", "Total σ": "sigma"})
if not chart_df.empty:
    chart_df["sigma"] = chart_df["sigma"].fillna(0)
    chart_df["low"] = (chart_df["total"] - chart_df["sigma"]).clip(lower=0)
    chart_df["high"] = chart_df["total"] + chart_df["sigma"]
    
    tooltip = [
        alt.Tooltip("Type:N"),
        alt.Tooltip("Units:Q", format=",d"),
        alt.Tooltip("total:Q", title="Total cost", format="$,.2f"),
        alt.Tooltip("sigma:Q", title="σ of total", format="$,.0f"),
    ]
    base = alt.Chart(chart_df).encode(x=alt.X("Type:N", sort="-y", title=None))
    bars = base.mark_bar(cornerRadiusTopLeft=3, cornerRadiusTopRight=3).encode(
        y=alt.Y("total:Q", title="Total cost ($)", axis=alt.Axis(format="$,.0f")), tooltip=tooltip
    )
    whiskers = base.mark_rule(strokeWidth=2, color="#333").encode(y="low:Q", y2="high:Q")
    st.altair_chart((bars + whiskers).properties(height=340), width="stretch")
    st.caption("Whiskers show ± one standard deviation of each type's total.")

with st.expander("All line items", key="all_line_items"):
    detail = entries[["Group", "Type", "Quantity", "Unit Cost", "Multiplier", "Line Total"]]
    st.dataframe(
        detail,
        hide_index=True,
        width="stretch",
        column_config={
            "Quantity": st.column_config.NumberColumn(format="%d"),
            "Unit Cost": st.column_config.NumberColumn(format="dollar"),
            "Multiplier": st.column_config.NumberColumn(
                "× Days?", format="%.0f", help="1 for a flat cost, or the Days value for a per-day cost."
            ),
            "Line Total": st.column_config.NumberColumn(format="dollar"),
        },
    )
    st.download_button(
        "Download line items (CSV)",
        detail.to_csv(index=False).encode(),
        file_name="line_items.csv",
        mime="text/csv",
        disabled=detail.empty,
    )

if stats is not None:
    with st.expander("Dataset cost statistics", key="dataset_cost_stats"):
        st.dataframe(
            stats[["Type", "n", "mean", "std", "min", "max"]],
            hide_index=True,
            width="stretch",
            column_config={
                "n": st.column_config.NumberColumn("Records", format="%d"),
                "mean": st.column_config.NumberColumn("Mean", format="dollar"),
                "std": st.column_config.NumberColumn("Std dev (σ)", format="dollar"),
                "min": st.column_config.NumberColumn("Min", format="dollar"),
                "max": st.column_config.NumberColumn("Max", format="dollar"),
            },
        )
