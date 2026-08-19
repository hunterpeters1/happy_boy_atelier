"""Shared "this placement tool is currently armed" glow accent -- see
settings.futuristic_accents_enabled(). Used by both LayersPanel
(composition/lighting/perspective placement tools) and SwatchesPanel
(the eyedropper) so the same subtle "this is live" glow reads
consistently on every tool-activation button in the app, rather than
each panel setting up its own QGraphicsDropShadowEffect/QPropertyAnimation.

Deliberately just the glow's own construction/animation -- gating on the
settings flag and tracking which button currently owns one is each
panel's own job (its buttons, its bookkeeping), same shape as before
this was split out.
"""

from __future__ import annotations

from PySide6.QtCore import QPropertyAnimation
from PySide6.QtGui import QColor
from PySide6.QtWidgets import QGraphicsDropShadowEffect, QToolButton

from .. import constants as C

# Slow, low-amplitude "breathing" glow, not a fast/bright pulse -- these
# buttons sit next to content someone may click repeatedly while placing
# several markers, so it needs to read as "this is live" without being
# distracting. Kept as a small glow (QGraphicsDropShadowEffect with no
# offset, not a real drop shadow).
TOOL_GLOW_COLOR = C.COLOR_BRASS_BRIGHT
TOOL_GLOW_MIN_BLUR = 6.0
TOOL_GLOW_MAX_BLUR = 18.0
TOOL_GLOW_PERIOD_MS = 3000


def start_tool_glow(btn: QToolButton) -> QPropertyAnimation:
    # Constructed with btn as its parent, not QGraphicsDropShadowEffect()
    # followed by setGraphicsEffect(effect) -- confirmed at runtime that
    # despite setGraphicsEffect() documenting a Qt-level ownership
    # transfer, PySide6 doesn't recognize that as a reason to keep the
    # Python wrapper alive: without an explicit parent here, the effect
    # was garbage-collected (and silently cleared off the button) the
    # moment the enclosing function returned.
    effect = QGraphicsDropShadowEffect(btn)
    effect.setColor(QColor(TOOL_GLOW_COLOR))
    effect.setOffset(0, 0)
    effect.setBlurRadius(TOOL_GLOW_MIN_BLUR)
    btn.setGraphicsEffect(effect)

    # A single looped animation with a middle keyframe (rather than two
    # animations played back to back, or setLoopCount() with Alternate
    # direction) gives one smooth breathe-in/breathe-out cycle per loop
    # with the least moving parts.
    anim = QPropertyAnimation(effect, b"blurRadius", btn)
    anim.setDuration(TOOL_GLOW_PERIOD_MS)
    anim.setKeyValueAt(0.0, TOOL_GLOW_MIN_BLUR)
    anim.setKeyValueAt(0.5, TOOL_GLOW_MAX_BLUR)
    anim.setKeyValueAt(1.0, TOOL_GLOW_MIN_BLUR)
    anim.setLoopCount(-1)
    anim.start()
    return anim
