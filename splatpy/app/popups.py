"""Modal popups: keyboard shortcuts, about, export options, image export settings.
(ports of supersplat ui/shortcuts-popup.ts, about-popup.ts, export-popup.ts, image-settings-dialog.ts)"""

from __future__ import annotations

VERSION = '0.1.0'

IMAGE_PRESETS = [('Viewport', None), ('HD 1280x720', (1280, 720)), ('Full HD 1920x1080', (1920, 1080)),
                 ('QHD 2560x1440', (2560, 1440)), ('4K 3840x2160', (3840, 2160)), ('Square 1024', (1024, 1024)), ('Custom', 'custom')]


class Popups:
    def __init__(self, app):
        self.app = app
        self._pending: list[str] = []
        ex = app.prefs.export or {}
        self.export_format = ex.get('format', 'ply')
        self.export_sh = int(ex.get('sh_bands', 3))
        self.export_selected = bool(ex.get('selected_only', False))
        im = app.prefs.image or {}
        self.image_preset = int(im.get('preset', 0))
        self.image_w = int(im.get('width', 1920))
        self.image_h = int(im.get('height', 1080))
        self.image_transparent = bool(im.get('transparent', False))
        self.image_overlays = bool(im.get('overlays', False))

    # ------------------------------------------------------------------ api
    def open(self, name: str):
        self._pending.append(name)

    def open_export(self, fmt: str):
        self.export_format = fmt
        self.open('export')

    def open_image(self):
        self.open('image')

    # ------------------------------------------------------------------ frame
    def draw(self, w, h):
        ui = self.app.ui
        for name in self._pending:
            ui.open_popup(name)
        self._pending.clear()
        for name, fn in (('shortcuts', self._shortcuts), ('about', self._about), ('export', self._export),
                         ('image', self._image)):
            try:
                fn(w, h)
            except Exception:
                self.app.log_error_once(f'popup:{name}')

    def _shortcuts(self, w, h):
        ui = self.app.ui
        if not ui.begin_popup_modal('shortcuts', 'Keyboard Shortcuts', w=520):
            return
        try:
            for cat, rows in self.app.shortcuts.help_rows():
                ui.label(cat, color=(1.0, 0.6, 0.2, 1.0))
                for keys, desc in rows:
                    ui.label(f'  {keys:<30} {desc}')
                ui.spacing(4)
            if ui.button('Close'):
                ui.close_current_popup()
        finally:
            ui.end_popup()

    def _about(self, w, h):
        ui = self.app.ui
        if not ui.begin_popup_modal('about', 'About SuperSplat Py', w=420):
            return
        try:
            ui.label(f'SuperSplat Py {VERSION}')
            ui.label('A Python + OpenGL 3.3 port of PlayCanvas SuperSplat,')
            ui.label('the 3D Gaussian Splat editor.')
            ui.spacing()
            ui.label('Built with numpy, PyOpenGL, glfw and Pillow.', color=(0.7, 0.7, 0.7, 1))
            ui.label('Original: github.com/playcanvas/supersplat (MIT)', color=(0.7, 0.7, 0.7, 1))
            if ui.button('Close'):
                ui.close_current_popup()
        finally:
            ui.end_popup()

    def _export(self, w, h):
        app, ui = self.app, self.app.ui
        if not ui.begin_popup_modal('export', 'Export', w=380):
            return
        try:
            formats = list(app.file_ops.save_formats().items())
            if not formats:
                ui.label('No writer available (splatpy.io.writer missing)')
                if ui.button('Close'):
                    ui.close_current_popup()
                return
            names = [f'{f} ({e})' for f, e in formats]
            keys = [f for f, _ in formats]
            idx = keys.index(self.export_format) if self.export_format in keys else 0
            idx = ui.combo('Format', idx, names)
            self.export_format = keys[idx]
            self.export_sh = ui.slider_int('SH Bands', self.export_sh, 0, 3)
            self.export_selected = ui.checkbox('Selected gaussians only', self.export_selected)
            n_vis = sum(s.num_visible for s in app.scene.splats if s.visible)
            n_sel = sum(s.num_selected for s in app.scene.splats if s.visible)
            ui.label(f'Will write {(n_sel if self.export_selected else n_vis):,} gaussians',
                     color=(0.7, 0.7, 0.7, 1))
            if ui.button('Export...'):
                ui.close_current_popup()
                app.prefs.export = dict(format=self.export_format, sh_bands=self.export_sh,
                                        selected_only=self.export_selected)
                app.prefs_dirty = True
                fmt, sh, sel = self.export_format, self.export_sh, self.export_selected
                app.defer(lambda: app.file_ops.export_dialog(fmt, sh, sel))
            ui.same_line()
            if ui.button('Cancel'):
                ui.close_current_popup()
        finally:
            ui.end_popup()

    def _image(self, w, h):
        app, ui = self.app, self.app.ui
        if not ui.begin_popup_modal('image', 'Export Image', w=380):
            return
        try:
            self.image_preset = ui.combo('Size', min(self.image_preset, len(IMAGE_PRESETS) - 1),
                                         [p[0] for p in IMAGE_PRESETS])
            preset = IMAGE_PRESETS[self.image_preset][1]
            if preset is None:
                iw, ih = app.viewport_size()
                ui.label(f'{iw} x {ih}', color=(0.7, 0.7, 0.7, 1))
            elif preset == 'custom':
                self.image_w = int(ui.slider_int('Width', self.image_w, 16, 8192))
                self.image_h = int(ui.slider_int('Height', self.image_h, 16, 8192))
                iw, ih = self.image_w, self.image_h
            else:
                iw, ih = preset
                ui.label(f'{iw} x {ih}', color=(0.7, 0.7, 0.7, 1))
            self.image_transparent = ui.checkbox('Transparent background', self.image_transparent)
            self.image_overlays = ui.checkbox('Show overlays (grid, bound)', self.image_overlays)
            if ui.button('Render...'):
                ui.close_current_popup()
                app.prefs.image = dict(preset=self.image_preset, width=iw, height=ih,
                                       transparent=self.image_transparent, overlays=self.image_overlays)
                app.prefs_dirty = True
                t, o = self.image_transparent, self.image_overlays
                app.defer(lambda: app.file_ops.export_image_dialog(iw, ih, t, o))
            ui.same_line()
            if ui.button('Cancel'):
                ui.close_current_popup()
        finally:
            ui.end_popup()
