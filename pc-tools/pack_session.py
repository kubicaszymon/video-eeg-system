"""Pack a recorded session into a single .zip for manual transfer/upload.

The "upload" half (local zip + manual): turns a ``recordings/session_*``
folder into one file you can copy anywhere. On the other machine, unzip it
and run ``check_session.py`` on the resulting folder.

Run (PC)::

    .venv-pc\\Scripts\\python pc_examples\\pack_session.py recordings\\session_YYYYmmdd-HHMMSS
    .venv-pc\\Scripts\\python pc_examples\\pack_session.py recordings\\session_... --out D:\\share\\
"""

import argparse
import os
import sys
import zipfile


def main(argv=None):
    ap = argparse.ArgumentParser(description="Zip a recorded session.")
    ap.add_argument("session", help="Path to a session_* folder.")
    ap.add_argument("--out", default=None,
                    help="Output .zip path or directory (default: next to "
                         "the session folder).")
    a = ap.parse_args(argv if argv is not None else sys.argv[1:])

    src = os.path.abspath(os.path.normpath(a.session))
    if not os.path.isdir(src) or not os.path.exists(
            os.path.join(src, "meta.json")):
        print("Not a session folder (no meta.json): %s" % src)
        sys.exit(1)
    name = os.path.basename(src)

    out = a.out
    if out is None:
        out = os.path.join(os.path.dirname(src), name + ".zip")
    elif os.path.isdir(out):
        out = os.path.join(out, name + ".zip")
    if not out.lower().endswith(".zip"):
        out += ".zip"

    files = []
    for root, _, fnames in os.walk(src):
        for fn in fnames:
            files.append(os.path.join(root, fn))

    total = 0
    with zipfile.ZipFile(out, "w", zipfile.ZIP_DEFLATED) as z:
        for fp in files:
            # store under "<session_name>/..." so it unzips into one folder
            arc = os.path.join(name, os.path.relpath(fp, src))
            z.write(fp, arc)
            total += os.path.getsize(fp)

    zsz = os.path.getsize(out)
    print("Packed %d files (%.1f MB raw) -> %s (%.1f MB)"
          % (len(files), total / 1e6, out, zsz / 1e6))
    print("Transfer that .zip anywhere. To review: unzip it, then run")
    print("  python pc_examples/check_session.py <unzipped session folder>")


if __name__ == "__main__":
    main()
