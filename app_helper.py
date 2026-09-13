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
