"""SuperSplat Py - Gaussian splat editor (Python + OpenGL port of PlayCanvas SuperSplat).

Usage:
    python main.py [files ...]            # .ply / .splat / .ksplat / .spz / .sog / .ssproj
    python main.py --demo 200000          # synthetic demo scene
    python main.py --smoke-test --demo 20000   # hidden window self-test (exit code 0 = OK)
"""

from __future__ import annotations

import argparse
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))


def main(argv=None) -> int:
    p = argparse.ArgumentParser(description="SuperSplat Py - 3D Gaussian Splat editor")
    p.add_argument('files', nargs='*', help='files to open (gaussian splats or .ssproj project)')
    p.add_argument('--demo', type=int, default=0, metavar='N', help='add a synthetic demo scene with N gaussians')
    p.add_argument('--smoke-test', action='store_true', help='run an automated hidden-window self test and exit')
    p.add_argument('--frames', type=int, default=30, help='frames to simulate in --smoke-test')
    p.add_argument('--size', default='1600x900', help='initial window size WxH')
    args = p.parse_args(argv)

    if args.smoke_test:
        from splat_editor.app.smoke import run_smoke_test
        return run_smoke_test(args.files, demo=args.demo or 20000, frames=args.frames)

    from splat_editor.app.app import App
    from splat_editor.app.demo import make_demo_splat
    try:
        w, h = (int(v) for v in args.size.lower().split('x'))
    except ValueError:
        w, h = 1600, 900
    app = App(files=args.files, width=w, height=h)
    if args.demo:
        app.file_ops.add_splat(make_demo_splat(args.demo))
        app.scene.history.mark_saved()
        app.focus_scene(animate=False)
    app.run()
    return 0


if __name__ == '__main__':
    sys.exit(main())
