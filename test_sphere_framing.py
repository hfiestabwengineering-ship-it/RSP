"""
Regression test: RSP sphere-framing
====================================
Verifies two bugs that were fixed on 2026-10-05:

1. CLIPPING  – When a sphere is visible (patch or 2-pole, any mode), the
   3D axis ranges must fully contain the sphere's center ± radius.
   Before the fix, `rspPolishSceneFigure` overrode the ranges with
   structure-only bounds in 'selected' / 'only-selected' modes,
   slicing the sphere off at the plot boundary.

2. OVAL      – In 'true-sphere' view mode the scene must use
   aspectmode: 'cube' so spheres render as true circles.
   Before the fix the mode used 'manual' with a 1:1:1 ratio which
   Plotly ignores when explicit ranges are set, producing ellipses.

Run:
    C:\\Users\\hvrfi\\Downloads\\general-muji-main\\general-muji-main\\.venv\\Scripts\\python.exe test_sphere_framing.py

Exit code 0 = all pass, 1 = any fail.
"""

import json
import sys
import os

# --- config -----------------------------------------------------------------
# HTML path is overridable via the RSP_HTML env var (used by the mutation
# check that verifies this test actually fails against the pre-fix code).
HTML = os.environ.get(
    "RSP_HTML",
    os.path.join(os.path.dirname(os.path.abspath(__file__)), "index.html"),
)
URL  = "file:///" + HTML.replace("\\", "/")

# Tolerance: allow 0.1 m of rounding error on range checks
TOL = 0.1

# --- helpers ----------------------------------------------------------------

def _get_scene(pg):
    """Read live scene-plot layout from the rendered Plotly div."""
    return pg.evaluate(r"""
    () => {
      const d = document.getElementById('scene-plot');
      if (!d || !d.layout || !d.layout.scene) return null;
      const s = d.layout.scene;
      return {
        aspectmode: s.aspectmode,
        zrange: s.zaxis ? s.zaxis.range : null,
        xrange: s.xaxis ? s.xaxis.range : null,
        yrange: s.yaxis ? s.yaxis.range : null,
        // grab surface trace extents so we can compare against axis ranges
        surfaces: (d.data || []).filter(t => t.type === 'surface').map(t => {
          // surface traces: X/Y/Z are 2-D arrays (rows of points)
          const flat = (arr) => arr.flat ? arr.flat() : arr;
          const zx = flat(t.x), zy = flat(t.y), zz = flat(t.z);
          return {
            name: t.name,
            xmin: Math.min(...zx), xmax: Math.max(...zx),
            ymin: Math.min(...zy), ymax: Math.max(...zy),
            zmin: Math.min(...zz), zmax: Math.max(...zz),
          };
        })
      };
    }
    """)


def _set_select(pg, id_, value):
    if value is None:
        # use the first available option
        value = pg.evaluate(
            f"document.getElementById('{id_}').options.length ? document.getElementById('{id_}').options[0].value : ''"
        )
    pg.evaluate(
        f"document.getElementById('{id_}').value = {json.dumps(value)};"
        f"document.getElementById('{id_}').dispatchEvent(new Event('change', {{bubbles:true}}));"
    )
    pg.wait_for_timeout(400)


def _check_contains(label, range_, lo, hi, tol=TOL):
    """Assert that [range_lo, range_hi] fully contains [lo, hi]."""
    if range_ is None:
        return False, f"{label}: range is None (expected to contain [{lo:.2f}, {hi:.2f}])"
    rlo, rhi = range_
    ok = rlo <= lo + tol and rhi >= hi - tol
    msg = f"{label}: range [{rlo:.2f}, {rhi:.2f}] contains [{lo:.2f}, {hi:.2f}] → {'✓' if ok else '✗ CLIPPED'}"
    return ok, msg


def _run_mode(pg, label, mode_id, mode_val, select_id=None, select_val=None):
    """
    Set a sphere display mode, read the scene, and verify the axis ranges
    contain every visible surface trace.
    Returns (ok: bool, msgs: list[str]).
    """
    _set_select(pg, mode_id, mode_val)
    if select_id and select_val is not None:
        _set_select(pg, select_id, select_val)

    scene = _get_scene(pg)
    if scene is None:
        return False, [f"{label}: scene-plot not found"]

    msgs = []
    ok = True

    # --- aspectmode check ---
    view_mode = pg.evaluate("document.getElementById('view-mode').value")
    expected_aspect = 'cube' if view_mode == 'true-sphere' else 'data'
    a_ok = scene['aspectmode'] == expected_aspect
    msgs.append(
        f"{label}: aspectmode={scene['aspectmode']} (expected {expected_aspect}) → {'✓' if a_ok else '✗'}"
    )
    ok = ok and a_ok

    # --- range containment check ---
    surfaces = scene.get('surfaces', [])
    if not surfaces:
        # No surface traces rendered – nothing to clip, but flag it
        msgs.append(f"{label}: no surface traces found (mode may not render any)")
    for s in surfaces:
        for axis, rng_key in [('x', 'xrange'), ('y', 'yrange'), ('z', 'zrange')]:
            lo = s[f'{axis}min']
            hi = s[f'{axis}max']
            axis_ok, axis_msg = _check_contains(
                f"{label} / {s['name'][:30]}",
                scene[rng_key],
                lo, hi
            )
            msgs.append("  " + axis_msg)
            ok = ok and axis_ok

    return ok, msgs


# --- test cases ---------------------------------------------------------------

TESTS = [
    # (label, mode_id, mode_val, select_id, select_val)
    ("patch=on",            "show-sphere-mode", "on",       None, None),
    ("patch=selected",      "show-sphere-mode", "selected", "patch-sphere-select", "0"),
    ("arc=on",              "show-arc-spheres", "on",       None, None),
    ("arc=selected",        "show-arc-spheres", "selected", "arc-sphere-select", None),  # first edge
    ("patch=on + arc=on",   "show-sphere-mode", "on",       "show-arc-spheres", "on"),
    ("patch=selected + arc=selected", "show-sphere-mode", "selected",
     "patch-sphere-select", "0"),
]
# NOTE: the combined "patch+arc" test above sets only one select; the other
# stays at whatever the previous test left it at.  That's intentional — the
# point is that *any* visible sphere must be fully inside the axis ranges.

# Separate test: true-sphere view mode aspect
def _test_true_sphere_aspect(pg):
    _set_select(pg, "show-sphere-mode", "on")
    _set_select(pg, "view-mode", "true-sphere")
    scene = _get_scene(pg)
    if scene is None:
        return False, ["true-sphere view: scene-plot not found"]
    ok = scene['aspectmode'] == 'cube'
    msg = f"true-sphere view: aspectmode={scene['aspectmode']} (expected 'cube') → {'✓' if ok else '✗'}"
    return ok, [msg]


def _test_engineering_aspect(pg):
    _set_select(pg, "show-sphere-mode", "off")
    _set_select(pg, "view-mode", "engineering")
    scene = _get_scene(pg)
    if scene is None:
        return False, ["engineering view: scene-plot not found"]
    ok = scene['aspectmode'] == 'data'
    msg = f"engineering view (spheres off): aspectmode={scene['aspectmode']} (expected 'data') → {'✓' if ok else '✗'}"
    return ok, [msg]


# --- main --------------------------------------------------------------------

def main():
    from playwright.sync_api import sync_playwright

    all_ok = True
    results = []

    with sync_playwright() as p:
        browser = p.chromium.launch()
        pg = browser.new_page()
        errs = []
        pg.on("console", lambda m: errs.append(m.text) if m.type == "error" else None)
        pg.on("pageerror", lambda e: errs.append(str(e)))

        print(f"Loading {URL}")
        pg.goto(URL, timeout=60000, wait_until="domcontentloaded")
        pg.wait_for_timeout(5000)

        if errs:
            print(f"⚠  Console errors on load: {errs[:5]}")

        # Use the app's built-in 'fast' performance mode so the test runs
        # in seconds instead of a minute (test speed, not a model change).
        _set_select(pg, "performance-mode", "fast")

        # --- per-mode framing tests ---
        for label, mode_id, mode_val, sel_id, sel_val in TESTS:
            ok, msgs = _run_mode(pg, label, mode_id, mode_val, sel_id, sel_val)
            results.append((label, ok, msgs))
            all_ok = all_ok and ok

        # --- aspect mode tests ---
        for fn in (_test_true_sphere_aspect, _test_engineering_aspect):
            ok, msgs = fn(pg)
            results.append((fn.__name__, ok, msgs))
            all_ok = all_ok and ok

        browser.close()

    # --- report ---
    print("\n" + "=" * 70)
    print("SPHERE FRAMING REGRESSION TEST")
    print("=" * 70)

    for label, ok, msgs in results:
        icon = "✓" if ok else "✗ FAIL"
        print(f"\n[{icon}] {label}")
        for m in msgs:
            print(f"   {m}")

    print("\n" + "=" * 70)
    total = len(results)
    passed = sum(1 for _, ok, _ in results if ok)
    print(f"RESULT: {passed}/{total} passed  →  {'ALL PASS ✓' if all_ok else 'FAILURES DETECTED ✗'}")
    print("=" * 70)

    return 0 if all_ok else 1


if __name__ == "__main__":
    sys.exit(main())
