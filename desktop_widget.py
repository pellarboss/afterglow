"""
Desktop widget for Afterglow: a small panel on the desktop showing the
current theme, the colour that's showing, the palette (click a colour to jump
to it) and a countdown to the next colour. With no theme running it shows
the light's current colour.

It sits on the desktop behind your windows (or on top, if you choose), shows
on every Space, and you can drag it anywhere. Its position is remembered.
"""

from __future__ import annotations

import colorsys
import math

import objc
from AppKit import (
    NSColor,
    NSEvent,
    NSFont,
    NSLineBreakByTruncatingTail,
    NSMakeRect,
    NSPanel,
    NSScreen,
    NSTextAlignmentRight,
    NSTextField,
    NSView,
    NSVisualEffectView,
)

W, H = 300, 156
PAD = 16
SWATCH = 52
DOT, DOT_GAP = 18, 8
MAX_DOTS = 8

# AppKit / CoreGraphics constants (numeric so we don't depend on Quartz bindings)
STYLE_BORDERLESS_NONACTIVATING = 0 | (1 << 7)
BACKING_BUFFERED = 2
JOIN_ALL_SPACES, STATIONARY, IGNORES_CYCLE = 1 << 0, 1 << 4, 1 << 6
FLOATING_LEVEL = 3
MATERIAL_POPOVER, BLEND_BEHIND_WINDOW, STATE_ACTIVE = 6, 0, 1


def desktop_level() -> int:
    try:
        from Quartz import CGWindowLevelForKey, kCGDesktopIconWindowLevelKey

        return int(CGWindowLevelForKey(kCGDesktopIconWindowLevelKey)) + 1
    except Exception:
        return -1  # just below normal windows


def ns_colour(hex_str: str):
    h = hex_str.lstrip("#")
    r, g, b = (int(h[i : i + 2], 16) / 255 for i in (0, 2, 4))
    return NSColor.colorWithSRGBRed_green_blue_alpha_(r, g, b, 1.0)


def hs_hex(hue: float, sat: float) -> str:
    r, g, b = colorsys.hsv_to_rgb((hue % 360) / 360, max(0, min(100, sat)) / 100, 1.0)
    return "#%02X%02X%02X" % (round(r * 255), round(g * 255), round(b * 255))


def kelvin_hex(mireds: int) -> str:
    """Approximate on-screen colour of a white light (Tanner Helland's fit)."""
    t = 1_000_000 / max(1, mireds) / 100
    r = 255 if t <= 66 else 329.698727446 * ((t - 60) ** -0.1332047592)
    g = 99.4708025861 * math.log(t) - 161.1195681661 if t <= 66 else 288.1221695283 * ((t - 60) ** -0.0755148492)
    b = 255 if t >= 66 else (0 if t <= 19 else 138.5177312231 * math.log(t - 10) - 305.0447927307)
    clamp = lambda v: max(0, min(255, round(v)))
    return "#%02X%02X%02X" % (clamp(r), clamp(g), clamp(b))


def label(size: float, weight: float, secondary: bool = False):
    f = NSTextField.labelWithString_("")
    f.setFont_(NSFont.systemFontOfSize_weight_(size, weight))
    f.setTextColor_(NSColor.secondaryLabelColor() if secondary else NSColor.labelColor())
    f.setLineBreakMode_(NSLineBreakByTruncatingTail)
    return f


class DotView(NSView):
    """A palette colour; click to jump to it. Set .index and .widget after creating."""

    def acceptsFirstMouse_(self, _event):
        return True

    def mouseDown_(self, _event):
        self.widget.dot_clicked(int(self.index))


class DragView(NSView):
    """Root view: drags the panel; lets clicks through to the dots. Set .widget after creating."""

    _start_mouse = None
    _start_origin = None

    def isFlipped(self):
        return True

    def acceptsFirstMouse_(self, _event):
        return True

    def hitTest_(self, point):
        view = objc.super(DragView, self).hitTest_(point)
        if isinstance(view, DotView):
            return view
        return self if view is not None else None

    def mouseDown_(self, _event):
        self._start_mouse = NSEvent.mouseLocation()
        self._start_origin = self.window().frame().origin

    def mouseDragged_(self, _event):
        if self._start_mouse is None:
            return
        now = NSEvent.mouseLocation()
        self.window().setFrameOrigin_((
            self._start_origin.x + now.x - self._start_mouse.x,
            self._start_origin.y + now.y - self._start_mouse.y,
        ))

    def mouseUp_(self, _event):
        if self._start_mouse is not None:
            origin = self.window().frame().origin
            self.widget.moved(origin.x, origin.y)
        self._start_mouse = None


class DesktopWidget:
    def __init__(self, backend):
        self.b = backend
        self.panel = None
        self.dots: list = []
        self._dot_hexes: list[str] = []
        self._last_swatch = None

    # --- window -------------------------------------------------------------
    def _build(self):
        panel = NSPanel.alloc().initWithContentRect_styleMask_backing_defer_(
            NSMakeRect(0, 0, W, H), STYLE_BORDERLESS_NONACTIVATING, BACKING_BUFFERED, False
        )
        panel.setOpaque_(False)
        panel.setBackgroundColor_(NSColor.clearColor())
        panel.setHasShadow_(True)
        panel.setHidesOnDeactivate_(False)
        panel.setReleasedWhenClosed_(False)
        panel.setCollectionBehavior_(JOIN_ALL_SPACES | STATIONARY | IGNORES_CYCLE)

        root = DragView.alloc().initWithFrame_(NSMakeRect(0, 0, W, H))
        root.widget = self
        root.setWantsLayer_(True)
        root.layer().setCornerRadius_(16)
        root.layer().setMasksToBounds_(True)

        blur = NSVisualEffectView.alloc().initWithFrame_(NSMakeRect(0, 0, W, H))
        blur.setMaterial_(MATERIAL_POPOVER)
        blur.setBlendingMode_(BLEND_BEHIND_WINDOW)
        blur.setState_(STATE_ACTIVE)
        root.addSubview_(blur)

        self.title = label(13, 0.3)
        self.title.setFrame_(NSMakeRect(PAD, PAD - 2, W - 2 * PAD - 90, 18))
        self.countdown = label(11, 0.0, secondary=True)
        self.countdown.setAlignment_(NSTextAlignmentRight)
        self.countdown.setFrame_(NSMakeRect(W - PAD - 110, PAD, 110, 16))

        self.swatch = NSView.alloc().initWithFrame_(NSMakeRect(PAD, PAD + 26, SWATCH, SWATCH))
        self.swatch.setWantsLayer_(True)
        self.swatch.layer().setCornerRadius_(12)
        self.swatch.layer().setBorderWidth_(0.5)
        self.swatch.layer().setBorderColor_(NSColor.separatorColor().CGColor())

        self.colour_name = label(15, 0.23)
        self.colour_name.setFrame_(NSMakeRect(PAD + SWATCH + 12, PAD + 32, W - SWATCH - 2 * PAD - 12, 20))
        self.detail = label(11, 0.0, secondary=True)
        self.detail.setFrame_(NSMakeRect(PAD + SWATCH + 12, PAD + 54, W - SWATCH - 2 * PAD - 12, 16))

        for v in (self.title, self.countdown, self.swatch, self.colour_name, self.detail):
            root.addSubview_(v)

        self.dots = []
        for i in range(MAX_DOTS):
            dot = DotView.alloc().initWithFrame_(
                NSMakeRect(PAD + 3 + i * (DOT + DOT_GAP), H - PAD - DOT - 2, DOT, DOT)
            )
            dot.index, dot.widget = i, self
            dot.setWantsLayer_(True)
            dot.layer().setCornerRadius_(DOT / 2)
            dot.setHidden_(True)
            root.addSubview_(dot)
            self.dots.append(dot)

        panel.setContentView_(root)
        self.panel = panel
        self._place()
        self.apply_level()

    def _place(self):
        pos = self.b.cfg.get("widget_pos")
        if pos and len(pos) == 2:
            self.panel.setFrameOrigin_((float(pos[0]), float(pos[1])))
            return
        vis = NSScreen.mainScreen().visibleFrame()
        self.panel.setFrameOrigin_((vis.origin.x + vis.size.width - W - 24,
                                    vis.origin.y + vis.size.height - H - 24))

    def apply_level(self):
        if self.panel is not None:
            self.panel.setLevel_(FLOATING_LEVEL if self.b.cfg.get("widget_on_top") else desktop_level())

    # --- visibility ---------------------------------------------------------
    @property
    def visible(self) -> bool:
        return self.panel is not None and bool(self.panel.isVisible())

    def show(self):
        if self.panel is None:
            self._build()
        self.panel.orderFrontRegardless()
        self.update()

    def hide(self):
        if self.panel is not None:
            self.panel.orderOut_(None)

    # --- callbacks from views -----------------------------------------------
    def dot_clicked(self, index: int):
        if self.b.themes.active:
            self.b.theme_jump(index)

    def moved(self, x: float, y: float):
        self.b.set_option("widget_pos", [round(x), round(y)])

    # --- content --------------------------------------------------------------
    def _set_swatch(self, hex_str: str):
        if hex_str != self._last_swatch:
            self.swatch.layer().setBackgroundColor_(ns_colour(hex_str).CGColor())
            self._last_swatch = hex_str

    def _set_dots(self, colours: list[tuple[str, str, int]], active: int | None):
        for i, dot in enumerate(self.dots):
            if i < len(colours):
                hex_str = colours[i][1]
                if i >= len(self._dot_hexes) or self._dot_hexes[i] != hex_str:
                    dot.layer().setBackgroundColor_(ns_colour(hex_str).CGColor())
                dot.setToolTip_(colours[i][0])
                is_active = i == active
                dot.layer().setBorderWidth_(2.0 if is_active else 0.5)
                dot.layer().setBorderColor_(
                    (NSColor.labelColor() if is_active else NSColor.separatorColor()).CGColor()
                )
                dot.setHidden_(False)
            else:
                dot.setHidden_(True)
        self._dot_hexes = [c[1] for c in colours]

    def update(self):
        if not self.visible:
            return
        snap = self.b.snapshot()
        st = self.b.theme_status()
        if st:
            self.title.setStringValue_(st["name"])
            name, hex_str = st["colour"]
            self._set_swatch(hex_str)
            self.colour_name.setStringValue_(name)
            n = len(st["colours"])
            extra = f" · {st['daypart']} whites" if st.get("daypart") else ""
            self.detail.setStringValue_(f"{st['index'] + 1} of {n} · {st['brightness']}%{extra}")
            if not snap["on"] or st["paused"]:
                self.countdown.setStringValue_("Light off")
            elif st["flicker"]:
                self.countdown.setStringValue_("flickering")
            else:
                secs = int(round(st["seconds_left"]))
                self.countdown.setStringValue_(f"next in {secs // 60}:{secs % 60:02d}")
            self._set_dots(st["colours"], st["index"])
            return

        # No theme: show the light's current colour.
        self.title.setStringValue_(snap["name"] if snap["configured"] else "Afterglow")
        if not snap["ready"]:
            self._set_swatch("#3A3A3A")
            self.colour_name.setStringValue_("No light set up")
            self.detail.setStringValue_("Use Set Up Light in the menu bar")
            self.countdown.setStringValue_("")
        else:
            if snap["mode"] == "hs":
                hex_str = hs_hex(snap["hue"], snap["sat"])
                name = "Colour"
            else:
                hex_str = kelvin_hex(snap["ct"])
                name = f"White {round(1_000_000 / snap['ct'] / 100) * 100:,} K"
            self._set_swatch(hex_str if snap["on"] else "#3A3A3A")
            self.colour_name.setStringValue_(name if snap["on"] else "Off")
            self.detail.setStringValue_(f"{snap['brightness']}% brightness" if snap["on"] else "Pick a theme from the menu bar")
            self.countdown.setStringValue_("no theme")
        self._set_dots([], None)
