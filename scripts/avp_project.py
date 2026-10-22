#!/usr/bin/env python3
"""Compile a resolved template spec (JSON) into an avp project file (.avp).

Must run under the Python interpreter that has `avp` installed (render.py finds
it). avp has no headless API for building projects, so this drives its own Core
and component widgets offscreen, exactly as the GUI would, then asks Core to
write the project. Values are given in GUI units: pixels at the template's
output resolution, percentages where the GUI shows %, combo items by label.

Usage: avp_project.py SPEC.json OUT.avp CONFIG_DIR
  CONFIG_DIR becomes avp's dataDir (settings.ini, presets). Run avp afterwards
  with XDG_CONFIG_HOME=<parent of CONFIG_DIR> so it reads the same settings.
"""
import json
import os
import sys

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

from PyQt6 import QtGui, QtWidgets  # noqa: E402

from avp.core import Core  # noqa: E402

# Friendly component names -> avp component names
COMPONENTS = {
    "image": "Image",
    "video": "Video",
    "color": "Color",
    "text": "Title Text",
    "waveform": "Waveform",
    "spectrum": "Spectrum",
    "classic": "Classic Visualizer",
    "sound": "Sound",
    "life": "Conway's Game of Life",
}

# Preset-key aliases (avp renames some attrs when saving presets)
ALIASES = {
    "Image": {"image": "imagePath", "x": "xPosition", "y": "yPosition"},
    "Video": {"video": "videoPath", "x": "xPosition", "y": "yPosition"},
    "Color": {"width": "sizeWidth", "height": "sizeHeight"},
}


def hex_to_rgb(val):
    if isinstance(val, (list, tuple)):
        return ",".join(str(int(v)) for v in val)
    s = str(val).strip()
    if s.startswith("#"):
        s = s[1:]
        if len(s) == 3:
            s = "".join(c * 2 for c in s)
        return ",".join(str(int(s[i:i + 2], 16)) for i in (0, 2, 4))
    return s  # assume already "r,g,b"


def set_widget(comp, key, widget, val):
    if key in getattr(comp, "_colorWidgets", {}):
        widget.setText(hex_to_rgb(val))
    elif isinstance(widget, QtWidgets.QLineEdit):
        widget.setText(str(val))
    elif isinstance(widget, QtWidgets.QCheckBox):
        widget.setChecked(bool(val))
    elif isinstance(widget, QtWidgets.QComboBox):
        if isinstance(val, str) and not val.isdigit():
            labels = [widget.itemText(i) for i in range(widget.count())]
            match = [i for i, t in enumerate(labels) if t.lower() == val.lower()]
            if not match:
                raise SystemExit(f"{comp.name}.{key}: '{val}' not one of {labels}")
            widget.setCurrentIndex(match[0])
        else:
            widget.setCurrentIndex(int(val))
    elif isinstance(widget, QtWidgets.QDoubleSpinBox):
        widget.setValue(float(val))
    elif isinstance(widget, QtWidgets.QSpinBox):
        widget.setValue(int(round(float(val))))
    else:
        raise SystemExit(f"{comp.name}.{key}: unsupported widget {type(widget).__name__}")


def apply_layer(comp, settings):
    tracked = comp._trackedWidgets
    aliases = ALIASES.get(comp.name, {})
    for key, val in settings.items():
        if key == "font":  # Title Text font family
            if os.path.isfile(str(val)):
                fid = QtGui.QFontDatabase.addApplicationFont(str(val))
                fams = QtGui.QFontDatabase.applicationFontFamilies(fid)
                val = fams[0] if fams else val
            comp.page.fontComboBox_titleFont.setCurrentFont(QtGui.QFont(str(val)))
            continue
        attr = aliases.get(key, key)
        if attr not in tracked:
            raise SystemExit(
                f"{comp.name}: unknown setting '{key}'. Known: {sorted(tracked)}"
            )
        set_widget(comp, attr, tracked[attr], val)
    comp.update()
    if comp.name == "Title Text" and comp.page.comboBox_textAlign.currentIndex() == 0:
        left_align_workaround(comp)


def left_align_workaround(comp):
    """avp 2.2.4 raises 'Alignment value 0 unknown' when rendering Left-aligned
    text (Text.getXY only handles Middle/Right). Emulate Left: switch to Middle
    and move x right by half the rendered text width.
    Remove once upstream getXY handles alignment 0."""
    page = comp.page
    font = QtGui.QFont(page.fontComboBox_titleFont.currentFont())
    font.setPixelSize(page.spinBox_fontSize.value())
    if page.comboBox_fontStyle.currentIndex() in (1, 2, 4):
        font.setWeight(
            QtGui.QFont.Weight.DemiBold
            if page.comboBox_fontStyle.currentIndex() == 1
            else QtGui.QFont.Weight.Bold
        )
    width = QtGui.QFontMetrics(font).horizontalAdvance(page.lineEdit_title.text())
    page.comboBox_textAlign.setCurrentIndex(1)
    page.spinBox_xTextAlign.setValue(page.spinBox_xTextAlign.value() + width // 2)
    comp.update()


def main():
    spec_path, out_path, config_dir = sys.argv[1:4]
    with open(spec_path) as f:
        spec = json.load(f)
    out = spec.get("output", {})

    Core.storeSettings(config_dir)
    s = Core.settings
    s.setValue("outputWidth", int(out.get("width", 1920)))
    s.setValue("outputHeight", int(out.get("height", 1080)))
    s.setValue("outputFrameRate", int(out.get("fps", 30)))
    # avp's own encode is only an intermediate: keep it near-lossless and fast.
    s.setValue("outputVideoBitrate", str(out.get("intermediate_kbps", 16000)))
    s.setValue("outputPreset", "veryfast")
    s.setValue("outputAudioBitrate", "320")
    s.sync()
    Core.loadDefaultSettings()

    app = QtWidgets.QApplication(sys.argv[:1])  # noqa: F841
    from avp.command import Command

    cmd = Command()
    core = cmd.core
    # avp keeps the topmost layer at index 0; spec lists layers bottom -> top.
    for layer in spec["layers"]:
        name = COMPONENTS.get(layer["component"].lower(), layer["component"])
        if name not in core.compNames:
            raise SystemExit(f"Unknown component {layer['component']}")
        idx = core.insertComponent(0, core.compNames.index(name), cmd)
        apply_layer(core.selectedComponents[idx], layer.get("set", {}))

    core.createProjectFile(out_path)
    print(out_path)


if __name__ == "__main__":
    main()
