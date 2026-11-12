"""Các mục bảng trái cho T4 (ánh sáng + bóng) và T5 (chế độ sinh tồn + vật lý): Mode và Lighting."""

"""
sections = [ModeSection(app), LightingSection(app)]     # SidePanel vẽ chúng cùng các mục khác
"""

from imgui_bundle import imgui

from ..core.lighting import MAX_LIGHTS
from . import widgets
from .sections import PanelSection


class ModeSection(PanelSection):
    title = "Mode"
    LABEL_WIDTH = 100

    def draw(self):
        app, physics = self.app, self.app.physics
        active = imgui.ImVec4(0.26, 0.52, 0.96, 1.0)
        spacing = imgui.get_style().item_spacing.x
        width = (imgui.get_content_region_avail().x - spacing) / 2
        for label, mode in (("Fly", "creative"), ("Walk", "survival")):
            is_active = app.mode == mode
            if is_active:
                imgui.push_style_color(imgui.Col_.button, active)
            if imgui.button(label, imgui.ImVec2(width, 0)):
                app.set_mode(mode)
            if is_active:
                imgui.pop_style_color()
            if mode == "creative":
                imgui.same_line()
        widgets.tooltip("M: toggle.\nFly: move freely through everything.\n"
                        "Walk: gravity, jumping and collision against the ply surface.")
        if app.mode != "survival":
            imgui.text_disabled("WASD fly, Space up, Shift down")
            return

        imgui.text_disabled("WASD walk, Space jump, Ctrl sprint,\nShift sneak. Drag to look around.")
        imgui.push_item_width(-self.LABEL_WIDTH)
        changed, height = imgui.input_float("Player height", physics.height, 0.0, 0.0, "%.4f",
                                            imgui.InputTextFlags_.enter_returns_true)
        if changed and height > 0.0:
            physics.set_height(height)
        widgets.tooltip("Splat scenes have no real unit: match the player's height to the scene.\n"
                        "Walk speed, jump and gravity scale with it. Changing it rebuilds the collision map.")
        _, physics.gravity_scale = imgui.slider_float("Gravity", physics.gravity_scale, 0.1, 3.0, "x%.2f")
        imgui.pop_item_width()
        imgui.text_disabled(physics.status)
        if widgets.full_width_button("Respawn Here"):
            app.set_mode("creative")
            app.set_mode("survival")


class LightingSection(PanelSection):
    title = "Lighting"
    LABEL_WIDTH = 90

    def draw(self):
        lighting = self.app.lighting
        _, lighting.enabled = imgui.checkbox("Enable lighting", lighting.enabled)
        widgets.tooltip("Phong shading (ambient + diffuse + specular) for every gaussian.\n"
                        "The normal is the gaussian's shortest axis, facing the camera.")
        imgui.push_item_width(-self.LABEL_WIDTH)
        _, lighting.ambient = imgui.slider_float("Ambient", lighting.ambient, 0.0, 1.0, "%.2f")
        _, lighting.specular = imgui.slider_float("Specular", lighting.specular, 0.0, 1.0, "%.2f")
        _, lighting.shininess = imgui.slider_float("Shininess", lighting.shininess, 2.0, 128.0, "%.0f",
                                                   imgui.SliderFlags_.logarithmic)
        imgui.pop_item_width()
        _, lighting.shadows = imgui.checkbox("Sun shadows (shadow map)", lighting.shadows)

        clicked = widgets.button_row(["Remove Sun" if lighting.sun_on else "Add Sun", "Add Light Block"])
        if clicked == 0:
            if lighting.sun_on:
                lighting.remove_sun()
            else:
                self.app.actions.trigger("add_sun")
        elif clicked == 1:
            self.app.actions.trigger("add_light")
        if len(lighting.lights) >= MAX_LIGHTS:
            imgui.text_disabled(f"Maximum {MAX_LIGHTS} light blocks")

        if lighting.sun_on:
            self._draw_sun(lighting)
        if lighting.lights:
            self._draw_lights(lighting)

    def _draw_sun(self, lighting):
        imgui.separator_text("Sun / day-night")
        imgui.push_item_width(-self.LABEL_WIDTH)
        _, lighting.hour = imgui.slider_float("Time", lighting.hour, 0.0, 24.0, "%.1f h")
        _, lighting.sun_intensity = imgui.slider_float("Sun power", lighting.sun_intensity, 0.0, 2.0, "%.2f")
        _, lighting.sun_azimuth = imgui.slider_float("Azimuth", lighting.sun_azimuth, 0.0, 360.0, "%.0f deg")
        _, lighting.day_length = imgui.slider_float("Day length", lighting.day_length, 5.0, 300.0, "%.0f s",
                                                    imgui.SliderFlags_.logarithmic)
        imgui.pop_item_width()
        _, lighting.animate = imgui.checkbox("Animate day-night", lighting.animate)
        _, lighting.sky_follows = imgui.checkbox("Sky follows time", lighting.sky_follows)
        imgui.text_disabled(f"State: {lighting.cycle.state.value}   (night > dawn > day > dusk)")

    def _draw_lights(self, lighting):
        physics = self.app.physics
        imgui.separator_text(f"Light blocks ({len(lighting.lights)})")
        for i, light in enumerate(lighting.lights):
            imgui.push_id(i)
            _, light.on = imgui.checkbox("##on", light.on)
            widgets.tooltip("Switch this light on / off")
            imgui.same_line()
            clicked, _ = imgui.selectable(light.name, i == lighting.selected)
            if clicked:
                lighting.selected = i
            imgui.pop_id()
        light = lighting.active_light
        if light is None:
            return

        imgui.spacing()
        imgui.push_item_width(-self.LABEL_WIDTH)
        changed, pos = imgui.drag_float3("Position", [float(v) for v in light.position],
                                         self.app.drag_speed(), format="%.3f")
        if changed:
            light.position[:] = pos
            light.resting = False
        _, light.intensity = imgui.slider_float("Intensity", light.intensity, 0.0, 10.0, "%.2f")
        _, light.range = imgui.slider_float("Range", light.range, physics.height * 0.5, physics.height * 40.0,
                                            "%.3f", imgui.SliderFlags_.logarithmic)
        _, color = imgui.color_edit3("Color", list(light.color))
        light.color = tuple(color)
        imgui.pop_item_width()
        _, light.auto_night = imgui.checkbox("On at night, off by day", light.auto_night)
        widgets.tooltip("Switched by the day-night state machine (needs the sun)")
        _, lighting.fireflies = imgui.checkbox("Fireflies around lights", lighting.fireflies)
        if widgets.danger_button("Remove light##remove_light"):
            lighting.remove_light(lighting.selected)
