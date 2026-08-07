"""Developer/debug helpers unlocked by Crazy Hack Mode (see main_window.py
MainWindow._set_hack_mode_active()). Not shown in the regular UI — these
exist for whoever is poking at the app's own internals, not for the
painting workflow.
"""

from __future__ import annotations

import datetime

VERBOSE_LOGGING = False


def log(message: str) -> None:
    """Print a timestamped line if verbose logging is currently on;
    otherwise a no-op. Call this from spots worth watching live (tool
    activation, selection changes, undo-stack moves) rather than gating
    every print site with `if VERBOSE_LOGGING` at the call site.
    """
    if not VERBOSE_LOGGING:
        return
    stamp = datetime.datetime.now().strftime("%H:%M:%S.%f")[:-3]
    print(f"[{stamp}] {message}")


def scene_stats(scene) -> str:
    """One-line summary of live scene state for the Hack Mode stats
    overlay: item counts per layer, selection size, and undo depth.
    """
    ref_n = len(scene.reference_layer.items())
    comp_n = len(scene.composition_layer.all_items())
    light_n = len(scene.lighting_layer.all_items())
    vp_n = len(scene.perspective_layer.vps)
    sel_n = len(scene.selected_items())
    undo_n = scene.undo_stack.index()
    return (
        f"ref={ref_n} comp={comp_n} light={light_n} vp={vp_n} "
        f"sel={sel_n} undo={undo_n}"
    )
