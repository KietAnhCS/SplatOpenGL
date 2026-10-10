"""Immediate-mode UI toolkit (ImGui-like) on top of Draw2D.

Usage per frame:
    ui.begin_frame(w, h, dt)
    if ui.begin_panel('right', x, y, w, h, title='Scene'):
        if ui.button('Hello'): ...
        ui.end_panel()
    ui.end_frame()        # renders

Input arrives between frames via on_* handlers (InputEvent, framebuffer pixels, top-left origin);
they return True when the UI consumed the event. Hit testing for consumption uses the window rects
of the previous frame.

IDs: label text + current scope (panel / popup / menu / push_id). 'Text##key' shows 'Text' with an
id from the whole string; 'Text###key' uses only '###key' as id.

Sizes: panel rects, histogram w/h and widget `width` are framebuffer pixels; `icon_button(size)`
and `spacing(px)` are logical pixels multiplied by ui.scale.
"""

from __future__ import annotations

import colorsys
import time

from ..core.tool_base import Mods
from .draw2d import Draw2D
from .theme import Theme

# glfw key codes
KEY_ENTER, KEY_KP_ENTER, KEY_ESCAPE, KEY_TAB = 257, 335, 256, 258
KEY_BACKSPACE, KEY_DELETE = 259, 261
KEY_RIGHT, KEY_LEFT, KEY_DOWN, KEY_UP = 262, 263, 264, 265
KEY_HOME, KEY_END = 268, 269
KEY_A, KEY_C, KEY_V, KEY_X = 65, 67, 86, 88

DOUBLE_CLICK_TIME = 0.35
TOOLTIP_DELAY = 0.5

L_PANEL = 0
L_MENUBAR = 10
L_MENU = 20            # + 2 * depth
L_MODAL = 30           # + 2 * stack index
L_OVERLAY = 50
L_TOP = 60


class _Window:
    __slots__ = ('id', 'kind', 'layer', 'order', 'x', 'y', 'w', 'h', 'view_y', 'view_h', 'cx0', 'cw',
                 'cursor_y', 'max_y', 'last', 'same', 'scroll', 'state', 'prev_layer', 'need_w', 'label_w',
                 'pad', 'depth', 'menu_x')


def _clamp(v, a, b):
    return a if v < a else (b if v > b else v)


class UI:
    def __init__(self, scale: float = 1.0, draw: Draw2D | None = None):
        self.draw = draw or Draw2D()
        self.theme = Theme(scale)
        self.width, self.height = 1, 1
        self.dt = 0.0
        self.time = 0.0
        self.frame = 0
        self.menu_bar_height = float(self.theme.menu_bar_h)
        self.clipboard_window = None          # glfw window used for the system clipboard
        self._clipboard = ''
        self.mods = Mods()

        # mouse / queued input
        self.mouse_x = self.mouse_y = -1e6
        self._held = [False] * 3
        self._captured = [False] * 3
        self._ext_held = [False] * 3
        self._q_pressed = [False] * 3
        self._q_released = [False] * 3
        self._q_press_pos = (0.0, 0.0)
        self._q_raw_press = False
        self._q_double = False
        self._q_wheel = 0.0
        self._q_input = []
        self._last_down_t = -10.0
        self._last_down_pos = (-1e9, -1e9)
        # per-frame snapshot
        self._pressed = [False] * 3
        self._released = [False] * 3
        self._press_pos = (0.0, 0.0)
        self._raw_press = False
        self._double = False
        self._wheel = 0.0
        self._input = []

        # widget state
        self._active = None
        self._active_seen = False
        self._deactivated = None
        self._hot = None
        self._hot_prev = None
        self._hover_time = 0.0
        self._focus = None
        self._focus_seen = False
        self._ts = {}
        self._pending_commit = {}
        self._drag = {}
        self._open_headers = {}
        self._panel_state = {}
        self._last_id = None
        self._last_rect = (0, 0, 0, 0)
        self._last_hovered = False
        self._last_active = False
        self._last_deact = False
        self._last_changed = False

        # windows
        self._windows_prev = []
        self._windows_cur = []
        self._order = 0
        self._win = None
        self._win_stack = []
        self._id_stack = []
        self._hover_id = None
        self._modal_layer_prev = None
        self._press_blocked = False

        # menus / popups / overlays
        self._open_menus = []
        self._menu_sizes = {}
        self._menu_stack = []
        self._menubar_seen = False
        self._popup_stack = []
        self._popup_sizes = {}
        self._popup_opened = {}
        self._popups_seen = set()
        self._cur_popup = []
        self._overlay = None
        self._overlay_seen = False
        self._picker = {}
        self._toasts = []
        self._tooltip = None

    # ================================================================== properties
    @property
    def scale(self) -> float:
        return self.theme.scale

    @scale.setter
    def scale(self, v: float):
        self.theme.set_scale(v)
        self.menu_bar_height = float(self.theme.menu_bar_h)

    @property
    def wants_keyboard(self) -> bool:
        return self._focus is not None

    @property
    def wants_mouse(self) -> bool:
        return self._would_consume(self.mouse_x, self.mouse_y)

    def needs_redraw(self) -> bool:
        """True while something animates (toasts, pending tooltip, active widget)."""
        return bool(self._toasts) or self._hot is not None or self._active is not None or self._focus is not None

    def item_active(self) -> bool:
        return self._last_active

    def item_deactivated(self) -> bool:
        return self._last_deact

    def item_changed(self) -> bool:
        return self._last_changed

    def is_item_hovered(self) -> bool:
        return self._last_hovered

    def item_clicked(self, button: int = 0) -> bool:
        """Last item hovered and `button` pressed this frame (e.g. right-click context actions)."""
        return self._last_hovered and self._pressed[button]

    def item_rect(self) -> tuple:
        return self._last_rect

    def key_pressed(self, key: int) -> bool:
        return any(e[0] == 'key' and e[1] == key for e in self._input)

    # ================================================================== input
    def _window_at(self, x, y, windows=None):
        best = None
        modal = self._modal_layer_prev
        for w in (self._windows_prev if windows is None else windows):
            layer, order, wid, kind, wx, wy, ww, wh = w
            if modal is not None and layer < modal:
                continue
            if wx <= x < wx + ww and wy <= y < wy + wh:
                if best is None or (layer, order) > (best[0], best[1]):
                    best = w
        return best

    def _would_consume(self, x, y) -> bool:
        return bool(self._popup_stack or self._open_menus or self._overlay is not None
                    or self._active is not None or any(self._captured)
                    or self._window_at(x, y) is not None)

    def _set_mods(self, ev):
        m = getattr(ev, 'mods', None)
        if m is not None:
            self.mods = m

    def on_mouse_down(self, ev) -> bool:
        self._set_mods(ev)
        self.mouse_x, self.mouse_y = float(ev.x), float(ev.y)
        if ev.kind == 'double_click':
            consumed = self._would_consume(ev.x, ev.y)
            if consumed:
                self._q_double = True
            return consumed
        b = ev.button
        now = time.perf_counter()
        lx, ly = self._last_down_pos
        dbl = (now - self._last_down_t) < DOUBLE_CLICK_TIME and abs(ev.x - lx) < 5 and abs(ev.y - ly) < 5
        self._last_down_t = -10.0 if dbl else now
        self._last_down_pos = (ev.x, ev.y)
        consumed = self._would_consume(ev.x, ev.y)
        self._q_raw_press = True
        if 0 <= b < 3:
            if consumed:
                self._q_pressed[b] = True
                self._captured[b] = True
                self._held[b] = True
                self._q_press_pos = (float(ev.x), float(ev.y))
                if dbl and b == 0:
                    self._q_double = True
            else:
                self._ext_held[b] = True
        return consumed

    on_double_click = on_mouse_down

    def on_mouse_up(self, ev) -> bool:
        self._set_mods(ev)
        self.mouse_x, self.mouse_y = float(ev.x), float(ev.y)
        b = ev.button
        if not 0 <= b < 3:
            return False
        self._held[b] = False
        self._ext_held[b] = False
        self._q_released[b] = True
        c = self._captured[b]
        self._captured[b] = False
        return c

    def on_mouse_move(self, ev) -> bool:
        self._set_mods(ev)
        self.mouse_x, self.mouse_y = float(ev.x), float(ev.y)
        if any(self._captured) or self._active is not None:
            return True
        if any(self._ext_held) and not self._popup_stack:
            return False
        return self._would_consume(ev.x, ev.y)

    def on_scroll(self, ev) -> bool:
        self._set_mods(ev)
        if self._would_consume(ev.x, ev.y):
            self._q_wheel += float(ev.scroll_y)
            return True
        return False

    def on_key(self, ev) -> bool:
        self._set_mods(ev)
        if ev.action in (1, 2):
            self._q_input.append(('key', ev.key, ev.mods))
            if ev.key == KEY_ESCAPE and self._focus is None and (self._open_menus or self._overlay is not None):
                self._open_menus = []
                self._overlay = None
                return True
        return self._focus is not None or bool(self._popup_stack)

    def on_char(self, ev) -> bool:
        if self._focus is not None:
            self._q_input.append(('char', ev.char, None))
            return True
        return False

    # ================================================================== frame
    def begin_frame(self, width, height, dt=0.0):
        self.width, self.height = max(1, int(width)), max(1, int(height))
        self.dt = float(dt)
        self.time += self.dt
        self.frame += 1
        self._pressed, self._q_pressed = self._q_pressed, [False] * 3
        self._released, self._q_released = self._q_released, [False] * 3
        self._press_pos = self._q_press_pos
        self._raw_press, self._q_raw_press = self._q_raw_press, False
        self._double, self._q_double = self._q_double, False
        self._wheel, self._q_wheel = self._q_wheel, 0.0
        self._input, self._q_input = self._q_input, []
        self._deactivated = None
        self._hot = None
        self._tooltip = None
        self._active_seen = False
        self._focus_seen = False
        self._overlay_seen = False
        self._menubar_seen = False
        self._popups_seen = set()
        self._windows_cur = []
        self._order = 0
        self._last_hovered = self._last_active = self._last_deact = self._last_changed = False

        hw = self._window_at(self.mouse_x, self.mouse_y)
        if hw is not None:
            self._hover_id = hw[2]
        else:
            self._hover_id = None if self._modal_layer_prev is not None else ('root',)
        # clicking outside open menus / overlays closes them and swallows the click
        self._press_blocked = False
        if any(self._pressed):
            pw = self._window_at(*self._press_pos)
            if self._overlay is not None and (pw is None or pw[2] != ('overlay',) + self._overlay):
                self._overlay = None
                self._press_blocked = True
            if self._open_menus and (pw is None or pw[3] not in ('menubar', 'menu')):
                self._open_menus = []
                self._press_blocked = True
            if self._press_blocked:
                self._pressed = [False] * 3
        self.draw.begin(self.width, self.height)
        self.draw.set_layer(L_PANEL)
        self._id_stack = [('root',)]
        root = self._new_window(('root',), 'root', 0, 0, self.width, self.height, L_PANEL, pad=self.theme.pad)
        root.state = {'scroll': 0.0, 'content_h': 0.0}
        self._win_stack = [root]
        self._win = root

    def end_frame(self):
        th = self.theme
        self._win_stack = []
        self._win = None
        # release / stale-state housekeeping
        if self._released[0] and self._active is not None:
            self._deactivated = self._active
            self._active = None
        if self._active is not None and not self._active_seen:
            self._active = None
        if self._focus is not None and not self._focus_seen:
            self._focus = None
        if self._overlay is not None and not self._overlay_seen:
            self._overlay = None
        if self._open_menus and not self._menubar_seen:
            self._open_menus = []
        for pid in list(self._popup_stack):
            if pid not in self._popups_seen and self._popup_opened.get(pid, 0) < self.frame:
                self._popup_stack.remove(pid)
        # tooltip
        if self._hot is not None and self._hot == self._hot_prev:
            self._hover_time += self.dt
        else:
            self._hover_time = 0.0
        self._hot_prev = self._hot
        d = self.draw
        d.set_layer(L_TOP)
        if self._tooltip:
            fs = th.font_size
            tw, tht = d.text_size(self._tooltip, fs)
            p = th.tooltip_pad
            x = self.mouse_x + th.s(14)
            y = self.mouse_y + th.s(20)
            x = _clamp(x, 2, self.width - tw - 2 * p - 2)
            if y + tht + 2 * p > self.height:
                y = self.mouse_y - tht - 2 * p - th.s(6)
            d.rect(x, y, tw + 2 * p, tht + 2 * p, th.tooltip_bg, radius=th.radius)
            d.rect_outline(x, y, tw + 2 * p, tht + 2 * p, th.border, 1, radius=th.radius)
            d.text(x + p, y + p, self._tooltip, th.text, fs)
        # toasts
        alive = []
        y = self.height - th.s(56)
        for t in reversed(self._toasts):
            t[1] -= self.dt
            if t[1] <= 0:
                continue
            alive.append(t)
            a = min(1.0, t[1] / 0.3, (t[2] - t[1]) / 0.15 + 0.2)
            fs = th.font_size
            tw, tht = d.text_size(t[0], fs)
            p = th.s(10)
            bw, bh = tw + 2 * p, tht + 2 * p
            x = (self.width - bw) * 0.5
            y -= bh
            bg = th.toast_bg
            d.rect(x, y, bw, bh, (bg[0], bg[1], bg[2], bg[3] * a), radius=th.radius)
            d.rect(x, y, th.s(3), bh, (*th.accent[:3], a))
            d.text(x + p, y + p, t[0], (1, 1, 1, a), fs)
            y -= th.s(6)
        self._toasts = list(reversed(alive))
        # modal layer for next frame's hit testing
        modal = [w[0] for w in self._windows_cur if w[3] == 'modal']
        self._modal_layer_prev = max(modal) if modal else None
        self._windows_prev = self._windows_cur
        d.set_layer(L_PANEL)
        d.end()

    # ================================================================== ids / layout
    def _parse(self, label):
        label = str(label)
        if '###' in label:
            disp, key = label.split('###', 1)
            key = '###' + key
        elif '##' in label:
            disp = label.split('##', 1)[0]
            key = label
        else:
            disp = key = label
        return disp, self._id_stack[-1] + (key,)

    def push_id(self, x):
        self._id_stack.append(self._id_stack[-1] + (x,))

    def pop_id(self):
        if len(self._id_stack) > 1:
            self._id_stack.pop()

    def _new_window(self, wid, kind, x, y, w, h, layer, pad=None, header=0.0):
        win = _Window()
        win.id, win.kind, win.layer = wid, kind, layer
        win.order = self._order
        self._order += 1
        win.x, win.y, win.w, win.h = float(x), float(y), float(w), float(h)
        win.pad = self.theme.pad if pad is None else pad
        win.view_y = win.y + header
        win.view_h = max(0.0, win.h - header)
        win.cx0 = win.x + win.pad
        win.cw = max(1.0, win.w - 2 * win.pad)
        win.scroll = 0.0
        win.cursor_y = win.view_y + win.pad
        win.max_y = win.cursor_y
        win.last = None
        win.same = False
        win.need_w = 0.0
        win.label_w = None
        win.depth = 0
        win.menu_x = 0.0
        win.prev_layer = layer
        return win

    def _push_window(self, wid, kind, x, y, w, h, layer, content_layer=None, scroll=False, header=0.0,
                     pad=None, register=True):
        th = self.theme
        win = self._new_window(wid, kind, x, y, w, h, layer, pad, header)
        st = self._panel_state.setdefault(wid, {'scroll': 0.0, 'content_h': 0.0})
        win.state = st
        overflow = scroll and st['content_h'] > win.view_h + 0.5
        if scroll and self._wheel and self._hover_id == wid and overflow:
            st['scroll'] -= self._wheel * th.s(40)
            self._wheel = 0.0
        if not overflow:
            st['scroll'] = 0.0
        st['scroll'] = _clamp(st['scroll'], 0.0, max(0.0, st['content_h'] - win.view_h))
        win.scroll = st['scroll'] if scroll else 0.0
        if overflow:
            win.cw = max(1.0, win.cw - th.scrollbar_w - 2)
        win.cursor_y = win.view_y + win.pad - win.scroll
        win.max_y = win.cursor_y
        st['overflow'] = overflow
        win.prev_layer = self.draw.set_layer(layer if content_layer is None else content_layer)
        self.draw.push_clip(win.x, win.view_y, win.w, win.view_h)
        if register:
            self._windows_cur.append((layer, win.order, wid, kind, win.x, win.y, win.w, win.h))
        self._id_stack.append(wid if isinstance(wid, tuple) else (wid,))
        self._win_stack.append(win)
        self._win = win
        return win

    def _pop_window(self):
        th = self.theme
        win = self._win_stack.pop()
        st = win.state
        content_h = (win.max_y + win.scroll) - win.view_y + win.pad
        st['content_h'] = content_h
        d = self.draw
        if st.get('overflow') and content_h > win.view_h:
            # scrollbar (draggable)
            sbw = th.scrollbar_w
            tx = win.x + win.w - sbw - 2
            frac = win.view_h / content_h
            th_h = max(th.s(20), win.view_h * frac)
            max_scroll = content_h - win.view_h
            ty = win.view_y + (win.view_h - th_h) * (st['scroll'] / max_scroll if max_scroll > 0 else 0)
            sid = (win.id, '#scrollbar')
            hov, held, pressed, _ = self._behavior(sid, tx - 2, win.view_y, sbw + 4, win.view_h)
            if pressed:
                self._drag[sid] = (self.mouse_y, st['scroll'])
            if held and sid in self._drag:
                my0, s0 = self._drag[sid]
                rng = max(1.0, win.view_h - th_h)
                st['scroll'] = _clamp(s0 + (self.mouse_y - my0) / rng * max_scroll, 0.0, max_scroll)
            col = th.accent if held else (th.bg_light if hov else th.scrollbar)
            d.rect(tx, ty, sbw, th_h, col, radius=sbw * 0.5)
        d.pop_clip()
        d.set_layer(win.prev_layer)
        if self._id_stack and len(self._id_stack) > 1:
            self._id_stack.pop()
        self._win = self._win_stack[-1] if self._win_stack else None
        return win

    def _place(self, w=None, h=None):
        """Returns (x, y, w, h) for the next item and records nothing yet."""
        win = self._win
        th = self.theme
        h = th.item_h if h is None else h
        if win.same and win.last is not None:
            lx, ly, lw, lh = win.last
            x, y = lx + lw + th.spacing_x, ly
        else:
            x, y = win.cx0, win.cursor_y
        avail = win.cx0 + win.cw - x
        if w is None:
            w = max(1.0, avail)
        elif w < 0:
            w = max(1.0, avail + w)
        return x, y, w, h

    def _add_item(self, id, x, y, w, h, hovered=False):
        win = self._win
        th = self.theme
        win.last = (x, y, w, h)
        win.same = False
        win.cursor_y = max(win.cursor_y, y + h + th.spacing_y)
        win.max_y = max(win.max_y, y + h)
        win.need_w = max(win.need_w, x + w - win.x + win.pad)
        if win.kind == 'root' and w > 0 and h > 0:
            self._windows_cur.append((L_PANEL, self._order, ('root',), 'rootitem', x, y, w, h))
            self._order += 1
        self._last_id = id
        self._last_rect = (x, y, w, h)
        self._last_hovered = hovered
        a, f, dz = self._active, self._focus, self._deactivated
        self._last_active = bool((a is not None and _prefix(a, id)) or (f is not None and _prefix(f, id)))
        self._last_deact = bool(dz is not None and _prefix(dz, id))

    def same_line(self):
        if self._win is not None:
            self._win.same = True

    def spacing(self, px=6):
        win = self._win
        win.same = False
        win.cursor_y += self.theme.s(px)
        win.max_y = max(win.max_y, win.cursor_y)

    def available_width(self) -> float:
        win = self._win
        return max(1.0, win.cx0 + win.cw - win.cx0)

    def cursor_pos(self) -> tuple:
        x, y, _, _ = self._place(0, 0)
        return x, y

    def reserve(self, w=None, h=24.0):
        """Reserves a (w x h px) layout rect for custom drawing via ui.draw. Returns (x, y, w, h)."""
        x, y, w, h = self._place(w, h)
        hov = self._hover(x, y, w, h)
        if hov:
            self._hot = ('reserve', x, y)
        self._add_item(None, x, y, w, h, hov)
        return x, y, w, h

    # ================================================================== interaction
    def _hover(self, x, y, w, h) -> bool:
        win = self._win
        if win is None or self._hover_id != win.id:
            return False
        mx, my = self.mouse_x, self.mouse_y
        if not (x <= mx < x + w and y <= my < y + h):
            return False
        clip = self.draw.current_clip()
        if clip is not None and not (clip[0] <= mx < clip[2] and clip[1] <= my < clip[3]):
            return False
        return True

    def _behavior(self, id, x, y, w, h, button=0):
        """-> (hovered, held, pressed_this_frame, clicked_on_release)."""
        hovered = self._hover(x, y, w, h) and (self._active is None or self._active == id)
        if hovered:
            self._hot = id
        pressed = clicked = False
        if hovered and self._pressed[button] and self._active is None:
            self._active = id
            self._pressed = list(self._pressed)
            self._pressed[button] = False      # one widget per press
            pressed = True
        held = self._active == id
        if held:
            self._active_seen = True
            if self._released[button]:
                clicked = hovered
                self._active = None
                self._deactivated = id
                held = False
        return hovered, held, pressed, clicked

    def _row(self, disp):
        """Labelled row: label in a left column, control on the right. -> (x,y,w,h,cx,cw)."""
        th = self.theme
        x, y, w, h = self._place()
        if disp:
            lw = self._win.label_w
            if lw is None:
                lw = max(th.label_min_w, round(w * 0.38))
            lw = min(lw, w * 0.6)
            fs = th.font_size
            self.draw.text(x, self._ty(y, h, fs), self._elide(disp, lw - th.s(4), fs), th.text_secondary, fs)
            return x, y, w, h, x + lw, w - lw
        return x, y, w, h, x, w

    def _ty(self, y, h, size, bold=False):
        return round(y + h * 0.5 - self.draw.face(size, bold).mid)

    def _elide(self, s, maxw, size, bold=False):
        f = self.draw.face(size, bold)
        if f.width(s) <= maxw:
            return s
        ell = '…'
        while s and f.width(s + ell) > maxw:
            s = s[:-1]
        return s + ell if s else ''

    # ================================================================== containers
    def begin_panel(self, id, x, y, w, h, title=None, scroll=True, radius=None, bg=None) -> bool:
        """Panel with optional header; always returns True (call end_panel)."""
        th = self.theme
        d = self.draw
        hdr = th.header_h if title else 0.0
        layer = self._win.layer if self._win is not None and self._win.kind != 'root' else L_PANEL
        if self._win is not None and self._win.kind in ('modal', 'overlay', 'menu'):
            layer = d.layer
        prev = d.layer
        d.set_layer(layer)
        r = th.panel_radius if w > 4 * th.panel_radius and h > 4 * th.panel_radius else 0
        if radius is not None:
            r = radius
        d.rect(x, y, w, h, th.bg_window if bg is None else bg, radius=r)
        if title:
            d.push_clip(x, y, w, hdr)
            d.rect(x, y, w, hdr + r, th.bg_header, radius=r)
            d.pop_clip()
            d.text(x + th.pad + th.s(2), self._ty(y, hdr, th.font_size, True), str(title).upper(), th.text,
                   th.font_size, bold=True)
        d.set_layer(prev)
        self._push_window(str(id), 'panel', x, y, w, h, layer, scroll=scroll, header=hdr)
        return True

    def end_panel(self):
        if self._win is not None and self._win.kind == 'panel':
            self._pop_window()

    def collapsing_header(self, label, default_open=True, icon=None) -> bool:
        """Section header: optional accent icon, bold upper-case title, chevron at the right."""
        from .icons import draw_icon
        th = self.theme
        disp, id = self._parse(label)
        x, y, w, h = self._place(None, th.s(40))
        hov, held, pressed, clicked = self._behavior(id, x, y, w, h)
        is_open = self._open_headers.get(id, default_open)
        if clicked:
            is_open = not is_open
            self._open_headers[id] = is_open
        d = self.draw
        d.rect(x - th.pad + th.s(4), y + th.s(1), w + 2 * th.pad - th.s(8), h - th.s(2),
               th.header_hover if hov else th.bg_header, radius=th.s(6))
        cy = y + h * 0.5
        tx = x + th.s(4)
        if icon:
            draw_icon(d, icon, x + th.s(14), cy, th.s(16), th.accent, max(1.2, th.s(1.5)))
            tx = x + th.s(34)
        fs = th.font_size + th.s(1)
        d.text(tx, self._ty(y, h, fs, True), disp.upper(), th.text, fs, bold=True)
        draw_icon(d, 'chevron_d' if is_open else 'chevron_r', x + w - th.s(10), cy, th.s(10), th.text_secondary,
                  max(1.2, th.s(1.5)))
        self._add_item(id, x, y, w, h, hov)
        return is_open

    def header_bar(self, title, icon=None, actions=()):
        """Static (non-collapsing) section header with right-aligned icon actions.
        `actions` = ((icon_name, tooltip), ...); returns the index of the clicked action or -1."""
        from .icons import draw_icon
        th = self.theme
        x, y, w, h = self._place(None, th.s(40))
        d = self.draw
        d.rect(x - th.pad + th.s(4), y + th.s(1), w + 2 * th.pad - th.s(8), h - th.s(2), th.bg_header,
               radius=th.s(6))
        cy = y + h * 0.5
        tx = x + th.s(4)
        if icon:
            draw_icon(d, icon, x + th.s(14), cy, th.s(16), th.accent, max(1.2, th.s(1.5)))
            tx = x + th.s(34)
        fs = th.font_size + th.s(1)
        d.text(tx, self._ty(y, h, fs, True), str(title).upper(), th.text, fs, bold=True)
        clicked_idx = -1
        bs = th.s(26)
        ax = x + w - bs
        for i, (name, tip) in reversed(list(enumerate(actions))):
            hov, held, pressed, clicked = self._behavior(('hbar', title, i), ax, y + (h - bs) * 0.5, bs, bs)
            col = th.accent_hover if hov else th.accent
            draw_icon(d, name, ax + bs * 0.5, cy, th.s(15), col, max(1.2, th.s(1.5)))
            if hov and tip:
                self._tooltip = str(tip)
            if clicked:
                clicked_idx = i
            ax -= bs + th.s(2)
        self._add_item(('hbar', title), x, y, w, h, False)
        return clicked_idx

    def interact(self, id, x, y, w, h):
        """Absolute-positioned hit area inside the current window -> (hovered, held, clicked).
        The caller draws the widget itself with ui.draw."""
        hov, held, pressed, clicked = self._behavior(('interact', id), x, y, w, h)
        self._add_item(('interact', id), x, y, w, h, hov)
        return hov, held, clicked

    # ================================================================== basic widgets
    def label(self, text, color=None):
        th = self.theme
        fs = th.font_size
        d = self.draw
        text = str(text)
        x, y, w, _ = self._place()
        f = d.face(fs)
        lines = []
        for para in text.split('\n'):
            if f.width(para) <= w or ' ' not in para:
                lines.append(para)
                continue
            cur = ''
            for word in para.split(' '):
                t = word if not cur else cur + ' ' + word
                if f.width(t) <= w or not cur:
                    cur = t
                else:
                    lines.append(cur)
                    cur = word
            lines.append(cur)
        col = th.text if color is None else color
        if len(lines) <= 1:
            h = th.item_h
            tw = f.width(lines[0] if lines else '')
            d.text(x, self._ty(y, h, fs), lines[0] if lines else '', col, fs)
        else:
            lh = f.line_height
            h = lh * len(lines) + th.s(4)
            tw = 0.0
            for i, ln in enumerate(lines):
                tw = max(tw, d.text(x, y + th.s(2) + i * lh, ln, col, fs))
        hov = self._hover(x, y, tw, h)
        if hov:
            self._hot = ('label', self._id_stack[-1], text)
        self._add_item(('label', text), x, y, max(tw, 1.0), h, hov)

    text = label

    def separator(self):
        th = self.theme
        win = self._win
        win.same = False
        x, y, w, _ = self._place()
        h = th.s(9)
        self.draw.rect(x, y + h * 0.5 - 0.5, w, max(1.0, th.s(1)), th.separator)
        self._add_item(None, x, y, w, h)

    def _button_core(self, id, disp, x, y, w, h, active=False, bold=False, size=None):
        th = self.theme
        hov, held, pressed, clicked = self._behavior(id, x, y, w, h)
        d = self.draw
        if active:
            bg = th.accent_hover if hov else th.accent
        else:
            bg = th.button_active if held else (th.button_hover if hov else th.button)
        d.rect(x, y, w, h, bg, radius=th.radius)
        fs = size or th.font_size
        f = d.face(fs, bold)
        s = self._elide(disp, w - th.s(6), fs, bold)
        tw = f.width(s)
        d.text(x + (w - tw) * 0.5, self._ty(y, h, fs, bold), s, th.text, fs, bold=bold)
        self._add_item(id, x, y, w, h, hov)
        return clicked

    def button(self, label, width=None, tooltip=None) -> bool:
        th = self.theme
        disp, id = self._parse(label)
        if width is None:
            width = self.draw.text_width(disp, th.font_size) + 2 * th.s(10)
        x, y, w, h = self._place(width)
        c = self._button_core(id, disp, x, y, w, h)
        if tooltip:
            self.tooltip(tooltip)
        return c

    def toggle_button(self, label, active, tooltip=None, width=None) -> bool:
        th = self.theme
        disp, id = self._parse(label)
        if width is None:
            width = self.draw.text_width(disp, th.font_size) + 2 * th.s(10)
        x, y, w, h = self._place(width)
        c = self._button_core(id, disp, x, y, w, h, active=bool(active))
        if tooltip:
            self.tooltip(tooltip)
        return c

    def icon_button(self, text, active=False, tooltip=None, size=32, icon=None) -> bool:
        th = self.theme
        disp, id = self._parse(text)
        s = th.s(size)
        x, y, w, h = self._place(s, s)
        hov, held, pressed, clicked = self._behavior(id, x, y, w, h)
        d = self.draw
        if active:
            bg = th.accent
        elif held:
            bg = th.button_active
        elif hov:
            bg = th.bg_darkest
        else:
            bg = None
        if bg is not None:
            d.rect(x, y, w, h, bg, radius=th.radius)
        fs = max(8.0, min(th.font_size, s * 0.42))
        col = th.text if active else (th.accent_hover if hov else th.icon_hilight)
        if icon:
            from .icons import draw_icon
            draw_icon(d, icon, x + w * 0.5, y + h * 0.5, s * 0.5, col, max(1.3, th.s(1.6)))
            self._add_item(id, x, y, w, h, hov)
            if tooltip:
                self.tooltip(tooltip)
            return clicked
        s2 = self._elide(disp, w - 2, fs, True)
        tw = d.text_width(s2, fs, True)
        d.text(x + (w - tw) * 0.5, self._ty(y, h, fs, True), s2, col, fs, bold=True)
        self._add_item(id, x, y, w, h, hov)
        if tooltip:
            self.tooltip(tooltip)
        return clicked

    def selectable(self, label, selected=False, width=None, height=None) -> bool:
        th = self.theme
        disp, id = self._parse(label)
        x, y, w, h = self._place(width, height)
        hov, held, pressed, clicked = self._behavior(id, x, y, w, h)
        d = self.draw
        if selected:
            d.rect(x, y, w, h, th.accent_soft, radius=th.radius)
        elif hov:
            d.rect(x, y, w, h, th.menu_hover, radius=th.radius)
        fs = th.font_size
        d.text(x + th.s(6), self._ty(y, h, fs), self._elide(disp, w - th.s(8), fs), th.text, fs)
        self._add_item(id, x, y, w, h, hov)
        return clicked

    def checkbox(self, label, value) -> bool:
        th = self.theme
        disp, id = self._parse(label)
        x, y, w, h, cx, cw = self._row(disp)
        hov, held, pressed, clicked = self._behavior(id, x, y, w, h)
        value = bool(value)
        changed = False
        if clicked:
            value = not value
            changed = True
        d = self.draw
        b = th.checkbox
        bx, by = cx, y + (h - b) * 0.5
        if value:
            d.rect(bx, by, b, b, th.accent_hover if hov else th.accent, radius=th.s(3))
            d.polyline([(bx + b * 0.22, by + b * 0.52), (bx + b * 0.42, by + b * 0.72), (bx + b * 0.78, by + b * 0.3)],
                       th.text, max(1.5, th.s(2)))
        else:
            d.rect(bx, by, b, b, th.frame_hover if hov else th.frame, radius=th.s(3))
            d.rect_outline(bx, by, b, b, th.bg_light if hov else th.border, 1, radius=th.s(3))
        self._add_item(id, x, y, w, h, hov)
        self._last_changed = changed
        return value

    # ------------------------------------------------------------------ text editing core
    def _start_edit(self, id, text, select_all=False):
        if self._focus is not None and self._focus != id:
            old = self._ts
            self._pending_commit[self._focus] = old.get('buf', '')
        self._focus = id
        self._focus_seen = True
        s = str(text)
        self._ts = {'buf': s, 'caret': len(s), 'anchor': 0 if select_all else len(s), 'scroll': 0.0,
                    'frame': self.frame, 'orig': s}

    def _clip_get(self) -> str:
        try:
            import glfw
            v = glfw.get_clipboard_string(self.clipboard_window)
            if v is not None:
                return v.decode('utf-8', 'replace') if isinstance(v, bytes) else str(v)
        except Exception:
            pass
        return self._clipboard

    def _clip_set(self, s: str):
        self._clipboard = s
        try:
            import glfw
            glfw.set_clipboard_string(self.clipboard_window, s)
        except Exception:
            pass

    def _text_field(self, id, x, y, w, h, text, select_all=False, numeric=False):
        """Single-line editable field. Returns (buffer_or_text, committed, cancelled, focused)."""
        th = self.theme
        d = self.draw
        fs = th.font_size
        f = d.face(fs)
        padx = th.s(6)
        if id in self._pending_commit:
            buf = self._pending_commit.pop(id)
            self._deactivated = id
            self._draw_field_text(x, y, w, h, buf, False, None)
            return buf, True, False, False
        hovered = self._hover(x, y, w, h) and (self._active is None or self._active == id)
        if hovered:
            self._hot = id
        focused = self._focus == id
        committed = cancelled = False
        if hovered and self._pressed[0]:
            self._pressed = [False] + list(self._pressed[1:])
            if not focused:
                self._start_edit(id, text, select_all)
                focused = True
            st = self._ts
            self._active = id
            self._active_seen = True
            if st['frame'] != self.frame or not select_all:
                c = self._caret_at(st, x + padx, f)
                st['caret'] = c
                if not self.mods.shift:
                    st['anchor'] = c
            if self._double:
                st['anchor'], st['caret'] = 0, len(st['buf'])
        if focused:
            st = self._ts
            self._focus_seen = True
            if self._active == id:
                self._active_seen = True
                if self._held[0] and not self._released[0]:
                    st['caret'] = self._caret_at(st, x + padx, f)
                if self._released[0]:
                    self._active = None
            if self._raw_press and not hovered and st['frame'] != self.frame:
                committed = True
            buf, caret, anchor = st['buf'], st['caret'], st['anchor']
            for ev in self._input:
                if committed or cancelled:
                    break
                if ev[0] == 'char':
                    ch = ev[1]
                    if not ch or ch < ' ':
                        continue
                    lo, hi = min(caret, anchor), max(caret, anchor)
                    buf = buf[:lo] + ch + buf[hi:]
                    caret = anchor = lo + len(ch)
                    continue
                key, mods = ev[1], ev[2] or Mods()
                lo, hi = min(caret, anchor), max(caret, anchor)
                if key == KEY_BACKSPACE:
                    if lo != hi:
                        buf = buf[:lo] + buf[hi:]
                        caret = anchor = lo
                    elif caret > 0:
                        n = caret - _word_left(buf, caret) if mods.ctrl else 1
                        buf = buf[:caret - n] + buf[caret:]
                        caret = anchor = caret - n
                elif key == KEY_DELETE:
                    if lo != hi:
                        buf = buf[:lo] + buf[hi:]
                        caret = anchor = lo
                    elif caret < len(buf):
                        n = _word_right(buf, caret) - caret if mods.ctrl else 1
                        buf = buf[:caret] + buf[caret + n:]
                elif key == KEY_LEFT:
                    if lo != hi and not mods.shift:
                        caret = lo
                    else:
                        caret = _word_left(buf, caret) if mods.ctrl else max(0, caret - 1)
                    if not mods.shift:
                        anchor = caret
                elif key == KEY_RIGHT:
                    if lo != hi and not mods.shift:
                        caret = hi
                    else:
                        caret = _word_right(buf, caret) if mods.ctrl else min(len(buf), caret + 1)
                    if not mods.shift:
                        anchor = caret
                elif key in (KEY_HOME, KEY_UP):
                    caret = 0
                    if not mods.shift:
                        anchor = caret
                elif key in (KEY_END, KEY_DOWN):
                    caret = len(buf)
                    if not mods.shift:
                        anchor = caret
                elif key in (KEY_ENTER, KEY_KP_ENTER, KEY_TAB):
                    committed = True
                elif key == KEY_ESCAPE:
                    cancelled = True
                elif mods.ctrl and key == KEY_A:
                    anchor, caret = 0, len(buf)
                elif mods.ctrl and key in (KEY_C, KEY_X):
                    if lo != hi:
                        self._clip_set(buf[lo:hi])
                        if key == KEY_X:
                            buf = buf[:lo] + buf[hi:]
                            caret = anchor = lo
                elif mods.ctrl and key == KEY_V:
                    s = self._clip_get().replace('\r', '').replace('\n', ' ')
                    buf = buf[:lo] + s + buf[hi:]
                    caret = anchor = lo + len(s)
            st['buf'], st['caret'], st['anchor'] = buf, caret, anchor
            if committed or cancelled:
                self._focus = None
                if self._active == id:
                    self._active = None
                self._deactivated = id
                result = st['orig'] if cancelled else buf
                self._draw_field_text(x, y, w, h, result, False, None)
                return result, committed, cancelled, False
            self._draw_field_text(x, y, w, h, buf, True, st)
            return buf, False, False, True
        self._draw_field_text(x, y, w, h, str(text), False, None, hovered)
        return str(text), False, False, False

    def _caret_at(self, st, x0, f):
        offs = f.offsets(st['buf'])
        rx = self.mouse_x - x0 + st['scroll']
        best, bd = 0, 1e9
        for i, o in enumerate(offs):
            dd = abs(o - rx)
            if dd < bd:
                best, bd = i, dd
        return best

    def _draw_field_text(self, x, y, w, h, s, focused, st, hovered=False):
        th = self.theme
        d = self.draw
        fs = th.font_size
        f = d.face(fs)
        padx = th.s(6)
        d.rect(x, y, w, h, th.frame_active if focused else (th.frame_hover if hovered else th.frame), radius=th.radius)
        if focused:
            d.rect_outline(x, y, w, h, th.accent, 1, radius=th.radius)
        ty = self._ty(y, h, fs)
        d.push_clip(x + 2, y, w - 4, h)
        if st is None:
            d.text(x + padx, ty, s, th.text, fs)
        else:
            offs = f.offsets(s)
            cx = offs[st['caret']]
            inner = w - 2 * padx
            if cx - st['scroll'] > inner:
                st['scroll'] = cx - inner
            if cx - st['scroll'] < 0:
                st['scroll'] = cx
            st['scroll'] = max(0.0, min(st['scroll'], max(0.0, offs[-1] - inner)))
            ox = x + padx - st['scroll']
            lo, hi = min(st['caret'], st['anchor']), max(st['caret'], st['anchor'])
            if lo != hi:
                d.rect(ox + offs[lo], y + th.s(4), offs[hi] - offs[lo], h - th.s(8), th.selection)
            d.text(ox, ty, s, th.text, fs)
            d.rect(round(ox + cx), y + th.s(4), max(1.0, th.s(1)), h - th.s(8), th.text)
        d.pop_clip()

    def text_input(self, id, text, width=None, live=False) -> str:
        """Single-line text field. Returns `text` unchanged until the edit is committed (Enter or
        click elsewhere), then the new string (live=True returns the buffer while typing).
        Escape cancels."""
        disp, wid = self._parse(id)
        x, y, w, h = self._place(width)
        res, committed, cancelled, focused = self._text_field(wid, x, y, w, h, text)
        self._add_item(wid, x, y, w, h, self._hover(x, y, w, h))
        self._last_changed = committed and res != text
        if focused:
            return res if live else text
        return res

    # ------------------------------------------------------------------ sliders / drags
    def _edit_start_requested(self, pressed) -> bool:
        return pressed and (self.mods.ctrl or self._double)

    def slider(self, label, value, vmin, vmax, fmt='%.2f') -> float:
        return self._slider(label, float(value), float(vmin), float(vmax), fmt, False)

    def slider_int(self, label, value, vmin, vmax) -> int:
        return int(self._slider(label, int(value), int(vmin), int(vmax), '%d', True))

    def _slider(self, label, value, vmin, vmax, fmt, is_int):
        th = self.theme
        d = self.draw
        disp, id = self._parse(label)
        x, y, w, h, cx, cw = self._row(disp)
        changed = False
        lo, hi = (vmin, vmax) if vmax >= vmin else (vmax, vmin)
        if self._focus == id or id in self._pending_commit:
            res, committed, cancelled, focused = self._text_field(id, cx, y, cw, h, _fmt(fmt, value), True)
            if committed:
                try:
                    v = float(_safe_num(res))
                    v = _clamp(v, lo, hi)
                    value = int(round(v)) if is_int else v
                    changed = True
                except ValueError:
                    pass
            self._add_item(id, x, y, w, h, False)
            self._last_changed = changed
            return value
        hov, held, pressed, clicked = self._behavior(id, cx, y, cw, h)
        if self._edit_start_requested(pressed):
            self._active = None
            self._start_edit(id, _fmt(fmt, value), select_all=True)
            held = False
        if held and cw > 0:
            t = _clamp((self.mouse_x - cx) / cw, 0.0, 1.0)
            v = vmin + t * (vmax - vmin)
            if is_int:
                v = int(round(v))
            if v != value:
                value = v
                changed = True
        span = (vmax - vmin)
        t = _clamp((value - vmin) / span, 0.0, 1.0) if span else 0.0
        d.rect(cx, y + th.s(2), cw, h - th.s(4), th.frame_hover if (hov or held) else th.frame, radius=th.radius)
        fw = cw * t
        if fw > 0.5:
            d.push_clip(cx, y, fw, h)
            d.rect(cx, y + th.s(2), cw, h - th.s(4), th.accent if held else (*th.accent[:3], 0.75), radius=th.radius)
            d.pop_clip()
        fs = th.font_size
        s = _fmt(fmt, value)
        tw = d.text_width(s, fs)
        d.text(cx + (cw - tw) * 0.5, self._ty(y, h, fs), s, th.text, fs)
        self._add_item(id, x, y, w, h, hov)
        self._last_changed = changed
        return value

    def drag_float(self, label, value, speed=0.01, vmin=None, vmax=None, fmt='%.3f', narrow=False) -> float:
        """Single drag field (drag horizontally; ctrl+click / double-click to type).
        narrow=True: one-third width bordered field (lines up with a drag_float3 column)."""
        disp, id = self._parse(label)
        x, y, w, h, cx, cw = self._row(disp)
        if narrow:
            cw = (cw - 2 * self.theme.s(3)) / 3.0
        v, ch = self._drag_field(id, cx, y, cw, h, float(value), speed, vmin, vmax, fmt, None,
                                 letter='' if narrow else None)
        self._add_item(id, x, y, w, h, self._hover(cx, y, cw, h))
        self._last_changed = ch
        return v

    def drag_float3(self, label, values, speed=0.01, fmt='%.3f', letters=None) -> tuple:
        """Three drag fields (X/Y/Z). Returns the (possibly changed) values as a tuple."""
        th = self.theme
        disp, id = self._parse(label)
        x, y, w, h, cx, cw = self._row(disp)
        vals = [float(v) for v in tuple(values)[:3]]
        while len(vals) < 3:
            vals.append(0.0)
        gap = th.s(3)
        fw = (cw - 2 * gap) / 3.0
        changed = False
        for i in range(3):
            fx = cx + i * (fw + gap)
            v, ch = self._drag_field(id + (i,), fx, y, fw, h, vals[i], speed, None, None, fmt, th.axis_colors[i],
                                     letter=letters[i] if letters else None)
            vals[i] = v
            changed = changed or ch
        self._add_item(id, x, y, w, h, self._hover(cx, y, cw, h))
        self._last_changed = changed
        return tuple(vals)

    def _drag_field(self, id, x, y, w, h, value, speed, vmin, vmax, fmt, accent, letter=None):
        th = self.theme
        d = self.draw
        changed = False
        if self._focus == id or id in self._pending_commit:
            res, committed, cancelled, focused = self._text_field(id, x, y, w, h, _fmt(fmt, value), True)
            if committed:
                try:
                    v = float(_safe_num(res))
                    if vmin is not None:
                        v = max(vmin, v)
                    if vmax is not None:
                        v = min(vmax, v)
                    changed = v != value
                    value = v
                except ValueError:
                    pass
            return value, changed
        hov, held, pressed, clicked = self._behavior(id, x, y, w, h)
        if self._edit_start_requested(pressed):
            self._active = None
            self._start_edit(id, _fmt(fmt, value), select_all=True)
            held = False
        if pressed and self._active == id:
            self._drag[id] = (self.mouse_x, value)
        if held and id in self._drag:
            mx0, v0 = self._drag[id]
            k = 10.0 if self.mods.shift else (0.1 if self.mods.alt else 1.0)
            v = v0 + (self.mouse_x - mx0) * speed * k
            if vmin is not None:
                v = max(vmin, v)
            if vmax is not None:
                v = min(vmax, v)
            if v != value:
                value = v
                changed = True
        elif not held:
            self._drag.pop(id, None)
        d.rect(x, y + th.s(2), w, h - th.s(4), th.frame_active if held else (th.frame_hover if hov else th.frame),
               radius=th.radius)
        fs = th.font_size
        if letter is not None:
            d.rect_outline(x, y + th.s(2), w, h - th.s(4), th.border, 1, radius=th.radius)
            lw = d.text_width(letter, th.font_size_small)
            d.text(x + w - lw - th.s(6), self._ty(y, h, th.font_size_small), letter, th.text_secondary,
                   th.font_size_small)
            s = self._elide(_fmt(fmt, value), w - lw - th.s(18), fs)
            d.push_clip(x, y, w, h)
            d.text(x + th.s(7), self._ty(y, h, fs), s, th.text_secondary, fs)
            d.pop_clip()
            return value, changed
        if accent is not None:
            d.rect(x, y + th.s(5), th.s(2), h - th.s(10), accent)
        s = self._elide(_fmt(fmt, value), w - th.s(6), fs)
        tw = d.text_width(s, fs)
        d.push_clip(x, y, w, h)
        d.text(x + (w - tw) * 0.5, self._ty(y, h, fs), s, th.text, fs)
        d.pop_clip()
        return value, changed

    # ------------------------------------------------------------------ combo
    def combo(self, label, index, items) -> int:
        th = self.theme
        d = self.draw
        disp, id = self._parse(label)
        items = [str(i) for i in items]
        x, y, w, h, cx, cw = self._row(disp)
        hov, held, pressed, clicked = self._behavior(id, cx, y, cw, h)
        is_open = self._overlay == id
        if clicked:
            self._overlay = None if is_open else id
            is_open = not is_open
        idx = int(index) if index is not None else -1
        bh = h - th.s(2)
        by = y + th.s(1)
        d.rect(cx, by, cw, bh, th.frame_hover if (hov or is_open) else th.frame, radius=th.radius)
        if is_open:
            d.rect_outline(cx, by, cw, bh, th.accent, 1, radius=th.radius)
        fs = th.font_size
        cur = items[idx] if 0 <= idx < len(items) else ''
        d.text(cx + th.s(6), self._ty(y, h, fs), self._elide(cur, cw - th.s(24), fs), th.text, fs)
        ax, ay, s = cx + cw - th.s(11), y + h * 0.5, th.s(3.5)
        d.triangle(ax - s, ay - s * 0.5, ax + s, ay - s * 0.5, ax, ay + s * 0.7, th.text_secondary)
        self._add_item(id, x, y, w, h, hov)
        result = idx
        if is_open:
            self._overlay_seen = True
            ih = th.item_h
            pad = th.s(4)
            lh = min(len(items) * ih + 2 * pad, th.combo_max_h)
            oy = y + h
            if oy + lh > self.height and y - lh >= 0:
                oy = y - lh
            ow = max(cw, max((d.text_width(i, fs) for i in items), default=0) + th.s(24))
            ox = min(cx, self.width - ow - 2)
            d.set_layer(L_OVERLAY)
            d.rect(ox, oy, ow, lh, th.menu_bg, radius=th.radius)
            d.rect_outline(ox, oy, ow, lh, th.border, 1, radius=th.radius)
            win = self._push_window(('overlay',) + id, 'overlay', ox, oy, ow, lh, L_OVERLAY, L_OVERLAY + 0.5,
                                    scroll=True, pad=pad)
            win.label_w = 0
            for i, it in enumerate(items):
                if self.selectable(f'{it}##{i}', i == idx, height=ih - th.s(2)):
                    result = i
                    self._overlay = None
            self._pop_window()
            self._last_id = id
            self._last_rect = (x, y, w, h)
        self._last_changed = result != idx
        return result

    # ------------------------------------------------------------------ colour
    def color_edit(self, label, rgba) -> tuple:
        th = self.theme
        d = self.draw
        disp, id = self._parse(label)
        rgba = tuple(float(c) for c in rgba)
        n = len(rgba)
        has_alpha = n >= 4
        x, y, w, h, cx, cw = self._row(disp)
        hov, held, pressed, clicked = self._behavior(id, cx, y, cw, h)
        is_open = self._overlay == id
        if clicked:
            is_open = not is_open
            self._overlay = id if is_open else None
            if is_open:
                self._picker[id] = list(colorsys.rgb_to_hsv(*[_clamp(c, 0, 1) for c in rgba[:3]]))
        by, bh = y + th.s(2), h - th.s(4)
        self._checker(cx, by, cw, bh)
        col = rgba[:3] + ((rgba[3],) if has_alpha else (1.0,))
        d.rect(cx, by, cw, bh, col, radius=th.radius)
        d.rect_outline(cx, by, cw, bh, th.accent if is_open else (th.bg_light if hov else th.border), 1, radius=th.radius)
        hexs = '#%02X%02X%02X' % tuple(int(round(_clamp(c, 0, 1) * 255)) for c in rgba[:3])
        lum = 0.299 * rgba[0] + 0.587 * rgba[1] + 0.114 * rgba[2]
        fs = th.font_size_small
        tw = d.text_width(hexs, fs)
        d.text(cx + (cw - tw) * 0.5, self._ty(y, h, fs), hexs, (0, 0, 0, 0.8) if lum > 0.55 else (1, 1, 1, 0.85), fs)
        self._add_item(id, x, y, w, h, hov)
        out = list(rgba)
        changed = False
        if is_open:
            self._overlay_seen = True
            hsv = self._picker.setdefault(id, list(colorsys.rgb_to_hsv(*[_clamp(c, 0, 1) for c in rgba[:3]])))
            cur_hsv = colorsys.rgb_to_hsv(*[_clamp(c, 0, 1) for c in rgba[:3]])
            if self._active is None or not _prefix(self._active, id):
                # follow external changes, keep hue when unsaturated
                if abs(cur_hsv[2] - hsv[2]) > 1e-4 or abs(cur_hsv[1] - hsv[1]) > 1e-4 or \
                        (cur_hsv[1] > 1e-4 and abs(cur_hsv[0] - hsv[0]) > 1e-4):
                    hsv[:] = [cur_hsv[0] if cur_hsv[1] > 1e-4 else hsv[0], cur_hsv[1], cur_hsv[2]]
            pad = th.pad
            sq = th.s(150)
            hb = th.s(16)
            ow = pad * 3 + sq + hb
            nsl = 4 if has_alpha else 3
            oh = pad * 2 + sq + th.spacing_y + nsl * (th.item_h + th.spacing_y)
            ox = _clamp(cx + cw - ow, 2, max(2, self.width - ow - 2))
            oy = y + h + 2
            if oy + oh > self.height and y - oh - 2 >= 0:
                oy = y - oh - 2
            d.set_layer(L_OVERLAY)
            d.rect(ox, oy, ow, oh, th.menu_bg, radius=th.radius)
            d.rect_outline(ox, oy, ow, oh, th.border, 1, radius=th.radius)
            win = self._push_window(('overlay',) + id, 'overlay', ox, oy, ow, oh, L_OVERLAY, L_OVERLAY + 0.5, pad=pad)
            win.label_w = th.s(18)
            self._id_stack.append(id)
            sx, sy = ox + pad, oy + pad
            # SV square
            hue_rgb = colorsys.hsv_to_rgb(hsv[0], 1, 1)
            d.rect_multicolor(sx, sy, sq, sq, (1, 1, 1, 1), (*hue_rgb, 1), (*hue_rgb, 1), (1, 1, 1, 1))
            d.rect_multicolor(sx, sy, sq, sq, (0, 0, 0, 0), (0, 0, 0, 0), (0, 0, 0, 1), (0, 0, 0, 1))
            sid = id + ('#sv',)
            _, sheld, _, _ = self._behavior(sid, sx, sy, sq, sq)
            if sheld:
                hsv[1] = _clamp((self.mouse_x - sx) / sq, 0, 1)
                hsv[2] = 1 - _clamp((self.mouse_y - sy) / sq, 0, 1)
                changed = True
            px, py = sx + hsv[1] * sq, sy + (1 - hsv[2]) * sq
            d.circle(px, py, th.s(5), (0, 0, 0, 1), 2)
            d.circle(px, py, th.s(4), (1, 1, 1, 1), 1)
            # hue bar
            hx = sx + sq + pad
            for i in range(6):
                c0 = colorsys.hsv_to_rgb(i / 6, 1, 1)
                c1 = colorsys.hsv_to_rgb((i + 1) / 6, 1, 1)
                y0 = sy + sq * i / 6
                d.rect_multicolor(hx, y0, hb, sq / 6 + 0.5, (*c0, 1), (*c0, 1), (*c1, 1), (*c1, 1))
            hid = id + ('#hue',)
            _, hheld, _, _ = self._behavior(hid, hx, sy, hb, sq)
            if hheld:
                hsv[0] = _clamp((self.mouse_y - sy) / sq, 0, 0.9999)
                changed = True
            hy = sy + hsv[0] * sq
            d.rect_outline(hx - 2, hy - 3, hb + 4, 6, (1, 1, 1, 1), 1)
            if changed:
                out[0:3] = colorsys.hsv_to_rgb(*hsv)
            win.cursor_y = sy + sq + th.spacing_y + pad * 0.5
            win.max_y = win.cursor_y
            names = 'RGBA'
            for i in range(nsl):
                v = self.slider(names[i], out[i], 0.0, 1.0, '%.3f')
                if self._last_changed:
                    out[i] = v
                    changed = True
                    if i < 3:
                        nh = colorsys.rgb_to_hsv(*[_clamp(c, 0, 1) for c in out[:3]])
                        hsv[:] = [nh[0] if nh[1] > 1e-4 else hsv[0], nh[1], nh[2]]
            self._id_stack.pop()
            self._pop_window()
            a, dz = self._active, self._deactivated
            self._last_id = id
            self._last_rect = (x, y, w, h)
            self._last_active = bool(a is not None and _prefix(a, id)) or bool(self._focus and _prefix(self._focus, id))
            self._last_deact = bool(dz is not None and _prefix(dz, id))
        self._last_changed = changed
        return tuple(out[:n])

    def _checker(self, x, y, w, h):
        d = self.draw
        s = max(4.0, self.theme.s(5))
        d.rect(x, y, w, h, (0.8, 0.8, 0.8, 1))
        d.push_clip(x, y, w, h)
        yy, r = y, 0
        while yy < y + h:
            xx = x + (s if r % 2 else 0)
            while xx < x + w:
                d.rect(xx, yy, s, s, (0.55, 0.55, 0.55, 1))
                xx += 2 * s
            yy += s
            r += 1
        d.pop_clip()

    # ------------------------------------------------------------------ misc widgets
    def progress_bar(self, fraction, text=''):
        th = self.theme
        d = self.draw
        x, y, w, h = self._place(None, th.s(18))
        f = _clamp(float(fraction), 0.0, 1.0)
        d.rect(x, y, w, h, th.frame, radius=th.radius)
        if f > 0:
            d.push_clip(x, y, w * f, h)
            d.rect(x, y, w, h, th.accent, radius=th.radius)
            d.pop_clip()
        if text:
            fs = th.font_size_small
            tw = d.text_width(text, fs)
            d.text(x + (w - tw) * 0.5, self._ty(y, h, fs), text, th.text, fs)
        self._add_item(None, x, y, w, h)

    def histogram(self, id, counts, w, h, sel_range=None):
        """Bar histogram (w, h framebuffer px; w None = available width). Click-drag selects a range:
        returns (t0, t1) with 0 <= t0 <= t1 <= 1 while dragging and on the release frame, else None."""
        th = self.theme
        d = self.draw
        _, hid = self._parse(id)
        x, y, aw, _ = self._place(None, 1)
        w = aw if (w is None or w <= 0) else min(float(w), aw)
        h = float(h)
        hov, held, pressed, clicked = self._behavior(hid, x, y, w, h)
        released = self._deactivated == hid
        tmouse = _clamp((self.mouse_x - x) / w, 0.0, 1.0) if w > 0 else 0.0
        result = None
        if pressed:
            self._drag[hid] = tmouse
        if (held or released) and hid in self._drag:
            t0 = self._drag[hid]
            result = (min(t0, tmouse), max(t0, tmouse))
            if released:
                self._drag.pop(hid, None)
        d.rect(x, y, w, h, th.bg_darker, radius=th.radius)
        vals = [float(c) for c in counts] if counts is not None else []
        n = len(vals)
        rng = result if result is not None else sel_range
        if n:
            mx = max(vals) or 1.0
            bw = w / n
            for i, c in enumerate(vals):
                if c <= 0:
                    continue
                bh = (h - 2) * min(1.0, c / mx)
                t_mid = (i + 0.5) / n
                insel = rng is not None and rng[0] <= t_mid <= rng[1]
                d.rect(x + i * bw, y + h - 1 - bh, max(1.0, bw - (1 if bw > 3 else 0)), bh,
                       th.histogram_sel if insel else th.histogram_bar)
        if rng is not None:
            x0, x1 = x + rng[0] * w, x + rng[1] * w
            d.rect(x0, y, max(1.0, x1 - x0), h, (*th.accent[:3], 0.15))
            d.rect(x0, y, 1, h, th.accent)
            d.rect(x1 - 1, y, 1, h, th.accent)
        self._add_item(hid, x, y, w, h, hov)
        return result

    # ================================================================== menus
    def begin_main_menu_bar(self, floating=None) -> bool:
        """Full-width bar at the top, or (floating=(x, y, h, lead_w)) a rounded floating bar whose width is
        measured from the previous frame; `lead_w` px at the left are reserved for the caller's logo."""
        th = self.theme
        self._menubar_seen = True
        d = self.draw
        d.set_layer(L_MENUBAR)
        if floating is None:
            h = th.menu_bar_h
            self.menu_bar_height = float(h)
            d.rect(0, 0, self.width, h, th.bg_header)
            d.rect(0, h - 1, self.width, 1, th.bg_darkest)
            win = self._push_window(('menubar',), 'menubar', 0, 0, self.width, h, L_MENUBAR, pad=0)
            win.menu_x = th.s(6)
            win.state['origin'] = (0.0, 0.0)
        else:
            bx, by, h, lead = floating
            bw = getattr(self, '_menubar_w', th.s(400))
            self.menu_bar_height = float(by + h)
            d.rect(bx, by, bw, h, th.bg_window, radius=th.panel_radius)
            win = self._push_window(('menubar',), 'menubar', bx, by, bw, h, L_MENUBAR, pad=0)
            win.menu_x = bx + lead
            win.state['origin'] = (bx, by)
            win.state['h'] = h
        self._menu_stack = []
        return True

    def end_main_menu_bar(self):
        if self._win is not None and self._win.kind == 'menubar':
            ox = self._win.state.get('origin', (0.0, 0.0))[0]
            if ox:
                self._menubar_w = self._win.menu_x - ox + self.theme.s(8)
            self._pop_window()

    def begin_menu(self, label, enabled=True) -> bool:
        th = self.theme
        d = self.draw
        disp, id = self._parse(label)
        id = ('menu',) + id[-1:] + (len(self._menu_stack),) if self._win.kind == 'menubar' else id
        win = self._win
        fs = th.font_size
        depth = len(self._menu_stack)
        if win.kind == 'menubar':
            tw = d.text_width(disp, fs)
            ox, oy = win.state.get('origin', (0.0, 0.0))
            x, y, w, h = win.menu_x, oy, tw + th.s(24), win.state.get('h', th.menu_bar_h)
            win.menu_x += w
            hov = self._hover(x, y, w, h)
            if hov:
                self._hot = id
            if hov and self._pressed[0]:
                self._pressed = [False] + list(self._pressed[1:])
                self._open_menus = [] if self._open_menus[:1] == [id] else [id]
            elif hov and self._open_menus and self._open_menus[0] != id:
                self._open_menus = [id]
            is_open = self._open_menus[:1] == [id]
            if is_open or hov:
                d.rect(x + 2, y + 3, w - 4, h - 6, th.menu_hover if not is_open else th.bg_lighter, radius=th.radius)
            d.text(x + th.s(12), self._ty(y, h, fs), disp, th.text_secondary if enabled and not (is_open or hov)
                   else (th.text if enabled else th.text_disabled), fs)
            win.last = (x, y, w, h)
            self._last_id, self._last_rect, self._last_hovered = id, (x, y, w, h), hov
            px, py = x, y + h + (th.s(6) if oy else 0)
        else:
            x, y, w, h = win.x, win.cursor_y, win.w, th.menu_item_h
            hov = self._hover(x, y, w, h) and enabled
            if hov:
                self._hot = id
                self._open_menus = self._open_menus[:depth] + [id]
            is_open = len(self._open_menus) > depth and self._open_menus[depth] == id
            if hov or is_open:
                d.rect(x + 3, y, w - 6, h, th.menu_hover, radius=th.radius)
            gut = th.menu_gutter
            d.text(x + gut, self._ty(y, h, fs), disp, th.text if enabled else th.text_disabled, fs)
            ax, ay, s = x + w - th.s(12), y + h * 0.5, th.s(3.5)
            d.triangle(ax - s * 0.6, ay - s, ax + s * 0.6, ay, ax - s * 0.6, ay + s, th.text_secondary)
            win.need_w = max(win.need_w, gut + d.text_width(disp, fs) + th.s(40))
            win.cursor_y += h
            win.max_y = max(win.max_y, win.cursor_y)
            self._last_id, self._last_rect, self._last_hovered = id, (x, y, w, h), hov
            px, py = x + w - th.s(2), y - th.s(4)
        if not is_open or not enabled:
            return False
        mw, mh = self._menu_sizes.get(id, (th.s(200), th.menu_item_h * 4))
        mw = max(mw, th.s(160))
        px = _clamp(px, 0, max(0, self.width - mw - 1))
        if py + mh > self.height:
            py = max(0, self.height - mh - 1)
        layer = L_MENU + 2 * depth
        nwin = self._push_window(('menuwin',) + id, 'menu', px, py, mw, max(mh, 1), layer, layer + 1, pad=th.s(4))
        nwin.depth = depth
        nwin.cursor_y = py + th.s(4)
        nwin.max_y = nwin.cursor_y
        nwin.need_w = 0.0
        self._menu_stack.append(id)
        self.draw.pop_clip()      # menu contents are not clipped (size from the previous frame)
        self.draw.push_clip(0, 0, self.width, self.height)
        return True

    def end_menu(self):
        if self._win is None or self._win.kind != 'menu':
            return
        th = self.theme
        win = self._win
        mid = self._menu_stack.pop() if self._menu_stack else None
        h = win.max_y - win.y + th.s(4)
        w = max(th.s(160), win.need_w)
        if mid is not None:
            self._menu_sizes[mid] = (w, h)
        d = self.draw
        prev = d.set_layer(win.layer)
        d.rect(win.x, win.y, w, h, th.menu_bg, radius=th.radius)
        d.rect_outline(win.x, win.y, w, h, th.border, 1, radius=th.radius)
        d.set_layer(prev)
        # fix up the hit-test rect with the measured size
        for i, e in enumerate(self._windows_cur):
            if e[2] == win.id:
                self._windows_cur[i] = (e[0], e[1], e[2], e[3], win.x, win.y, w, h)
        self._pop_window()

    def menu_item(self, label, shortcut='', enabled=True, checked=None) -> bool:
        th = self.theme
        d = self.draw
        win = self._win
        disp, id = self._parse(label)
        fs = th.font_size
        if win.kind != 'menu':
            # outside a menu: behave like a selectable row
            return self.selectable(label) and enabled
        x, y, w, h = win.x, win.cursor_y, win.w, th.menu_item_h
        hov = self._hover(x, y, w, h)
        clicked = False
        if hov:
            self._hot = id
            self._open_menus = self._open_menus[:win.depth + 1]
            if enabled:
                d.rect(x + 3, y, w - 6, h, th.menu_hover, radius=th.radius)
                if self._released[0] or self._pressed[0]:
                    if self._released[0]:
                        clicked = True
                    self._pressed = [False] + list(self._pressed[1:])
        col = th.text if enabled else th.text_disabled
        gut = th.menu_gutter
        if checked:
            cx, cy, s = x + gut * 0.5, y + h * 0.5, th.s(5)
            d.polyline([(cx - s, cy), (cx - s * 0.3, cy + s * 0.7), (cx + s, cy - s * 0.7)], th.accent,
                       max(1.5, th.s(2)))
        d.text(x + gut, self._ty(y, h, fs), disp, col, fs)
        sw = 0.0
        if shortcut:
            sfs = th.font_size_small
            sw = d.text_width(shortcut, sfs)
            d.text(x + w - sw - th.s(12), self._ty(y, h, sfs), shortcut, th.text_disabled, sfs)
        win.need_w = max(win.need_w, gut + d.text_width(disp, fs) + (sw + th.s(36) if shortcut else th.s(24)))
        win.cursor_y += h
        win.max_y = max(win.max_y, win.cursor_y)
        self._last_id, self._last_rect, self._last_hovered = id, (x, y, w, h), hov
        if clicked:
            self._open_menus = []
        return clicked

    def menu_separator(self):
        th = self.theme
        win = self._win
        if win.kind != 'menu':
            return self.separator()
        h = th.s(7)
        self.draw.rect(win.x + th.s(8), win.cursor_y + h * 0.5, win.w - th.s(16), 1, th.separator)
        win.cursor_y += h
        win.max_y = max(win.max_y, win.cursor_y)

    # ================================================================== popups
    def open_popup(self, id):
        if id not in self._popup_stack:
            self._popup_stack.append(id)
            self._popup_opened[id] = self.frame
        # any open menu / overlay closes
        self._open_menus = []
        self._overlay = None

    def is_popup_open(self, id) -> bool:
        return id in self._popup_stack

    def begin_popup_modal(self, id, title, w=360) -> bool:
        if id not in self._popup_stack:
            return False
        th = self.theme
        d = self.draw
        self._popups_seen.add(id)
        idx = self._popup_stack.index(id)
        layer = L_MODAL + 2 * idx
        pw = min(th.s(w), self.width - 8)
        ph = self._popup_sizes.get(id, 0.0)
        px = round((self.width - pw) * 0.5)
        py = round(max(4.0, (self.height - ph) * 0.5))
        d.set_layer(layer)
        d.rect(0, 0, self.width, self.height, th.dim)
        hdr = th.header_h
        win = self._push_window(('popup', id), 'modal', px, py, pw, max(ph, hdr + 1), layer, layer + 1,
                                header=hdr)
        # contents may exceed last frame's height: don't clip vertically
        d.pop_clip()
        d.push_clip(px, py + hdr, pw, self.height)
        win.state['title'] = str(title)
        self._cur_popup.append(id)
        return True

    def end_popup(self):
        if self._win is None or self._win.kind != 'modal':
            return
        th = self.theme
        win = self._win
        pid = self._cur_popup.pop() if self._cur_popup else None
        h = min(win.max_y - win.y + win.pad, self.height - 8)
        if pid is not None:
            self._popup_sizes[pid] = h
        d = self.draw
        prev = d.set_layer(win.layer)
        r = th.panel_radius
        d.rect(win.x, win.y, win.w, h, th.bg_window, radius=r)
        hdr = th.header_h
        d.push_clip(win.x, win.y, win.w, hdr)
        d.rect(win.x, win.y, win.w, hdr + r, th.bg_header, radius=r)
        d.pop_clip()
        title = win.state.get('title', '')
        d.text(win.x + th.pad + th.s(2), self._ty(win.y, hdr, th.font_size, True), title.upper(), th.text,
               th.font_size, bold=True)
        d.set_layer(prev)
        for i, e in enumerate(self._windows_cur):
            if e[2] == win.id:
                self._windows_cur[i] = (e[0], e[1], e[2], e[3], win.x, win.y, win.w, h)
        self._pop_window()

    def close_current_popup(self):
        if self._cur_popup:
            pid = self._cur_popup[-1]
            if pid in self._popup_stack:
                self._popup_stack.remove(pid)
            if self._focus is not None:
                self._focus = None

    def close_popup(self, id):
        if id in self._popup_stack:
            self._popup_stack.remove(id)

    # ================================================================== notifications
    def notify(self, text, seconds=3.0):
        self._toasts.append([str(text), float(seconds), float(seconds)])
        if len(self._toasts) > 6:
            self._toasts = self._toasts[-6:]

    def tooltip(self, text):
        if self._last_hovered and self._active is None and self._hover_time >= TOOLTIP_DELAY \
                and self._hot_prev is not None and self._hot_prev == self._hot:
            self._tooltip = str(text)


# ---------------------------------------------------------------------- helpers
def _prefix(ident, group) -> bool:
    if ident == group:
        return True
    return isinstance(ident, tuple) and isinstance(group, tuple) and len(ident) > len(group) \
        and ident[:len(group)] == group


def _fmt(fmt, v):
    try:
        return fmt % v
    except (TypeError, ValueError):
        return str(v)


def _safe_num(s: str) -> float:
    s = s.strip().replace(',', '.')
    if not s:
        raise ValueError('empty')
    try:
        return float(s)
    except ValueError:
        pass
    allowed = set('0123456789.+-*/() eE')
    if all(c in allowed for c in s):
        try:
            return float(eval(s, {'__builtins__': {}}, {}))  # arithmetic only
        except Exception:
            pass
    raise ValueError(s)


def _word_left(s, i):
    i = max(0, i - 1)
    while i > 0 and s[i - 1] == ' ':
        i -= 1
    while i > 0 and s[i - 1] != ' ':
        i -= 1
    return i


def _word_right(s, i):
    n = len(s)
    while i < n and s[i] == ' ':
        i += 1
    while i < n and s[i] != ' ':
        i += 1
    return i
