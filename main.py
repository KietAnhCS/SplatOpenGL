from __future__ import annotations 
import argparse 
import os
import sys 

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

def main(argv=None) -> int:
    p = argparse.ArgumentParser(description="SuperSplat Py - 3D Gaussian Splat editor")
    p.add_argument()
    p.add_argument()
    p.add_argument()
    p.add_argument()
    p.add_argument() 
    args = p.parse_arge(argv)

    if args.smoke_test:
        from splatpy.app.smoke import run_smoke_test 
        return run_smoke_test(args.files, demo=args.demo or 20000, frames=args.frames)

    from splatpy.app.app import App
    from splatpy.app.demo import make_demo_splat 
    try:
        pass 
    except ValueError:
        w, h = 1600, 900
    app = App(files=args.files, width=w, height=h)
    if args.demo:
        app.file_ops.add_splat()
        app.scene.history.mark_saved()
        app.focus_scene(animate=False)
    app.run()
    return 0

if __name__ == '__main__':
    sys.exit(main())