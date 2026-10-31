from pathlib import Path
import unittest

from efospec.planning import build_plan, compatibility, _select


REFERENCE = Path(__file__).resolve().parents[1] / "trunk/src/ntt"


def frame(name="target", role="science", mjd=60629.1):
    return {"path": f"/data/{name}.fits", "sha256": name, "role": role,
            "night": "20241114", "issues": [],
            "setup": dict(grism="Gr13", filter="Free", slit="slit1.0", binx=2, biny=2,
                          readout="fastL", shape_yx=[1030, 1030]),
            "metadata": {"MJD-OBS": mjd, "EXPTIME": 600, "ESO DET OUT1 GAIN": 0.91,
                         "ESO DET OUT1 RON": 7.8, "RA": 10., "DEC": -30.,
                         "ESO TEL AIRM START": 1.1, "ESO OBS ID": 123, "OBJECT": name}}


def report(frames):
    return {"frames": frames, "errors": [], "identity_conflicts": {}}


class PlanningTests(unittest.TestCase):
    def test_nearer_incompatible_arc_rejected(self):
        target, good, wrong = frame(), frame("good", "arc", 60629.11), frame("bad", "arc", 60629.1)
        wrong["setup"]["filter"] = "GG495"
        result = _select(target, [wrong, good], "arc")
        self.assertEqual(result["files"], [good["path"]])
        self.assertIn("different filter", result["rejected"][0]["reasons"])

    def test_bias_ignores_disperser_but_not_readout(self):
        target, bias = frame(), frame("bias", "bias")
        bias["setup"].update(grism="Free", filter="Free", slit="Free")
        self.assertEqual(compatibility(target, bias, "bias"), [])
        bias["setup"]["readout"] = "slow"
        self.assertIn("different readout", compatibility(target, bias, "bias"))

    def test_wide_slit_arc_exception_only(self):
        target, arc = frame(), frame("arc", "arc")
        target["setup"]["slit"] = "slit5.0"
        self.assertEqual(compatibility(target, arc, "arc"), [])
        self.assertEqual(compatibility(target, arc, "flat"), ["different slit"])

    def test_offnight_arc_requires_explicit_selection(self):
        target, arc = frame(), frame("arc", "arc", 60620)
        arc["night"] = "20241105"
        self.assertEqual(_select(target, [arc], "arc")["status"], "missing")
        result = _select(target, [arc], "arc", [arc["path"]])
        self.assertEqual(result["files"], [arc["path"]])
        self.assertAlmostEqual(result["time_separation_days"], 9.1)

    def test_override_never_silently_falls_back(self):
        target, good, bad = frame(), frame("good", "arc"), frame("bad", "arc")
        bad["setup"]["grism"] = "Gr11"
        self.assertEqual(_select(target, [good, bad], "arc", [bad["path"]])["status"], "missing")

    def test_tie_requires_review(self):
        target = frame(mjd=60000)
        result = _select(target, [frame("a", "arc", 59999), frame("b", "arc", 60001)], "arc")
        self.assertEqual(result["status"], "ambiguous")
        self.assertEqual(result["files"], [])

    def test_flat_groups_need_three_and_prefer_obid(self):
        target = frame()
        same, other = [], []
        for i in range(3):
            a, b = frame(f"a{i}", "flat", 60629.3), frame(f"b{i}", "flat", 60629.1)
            a["metadata"]["OBJECT"] = b["metadata"]["OBJECT"] = "flat"
            b["metadata"]["ESO OBS ID"] = 456
            same.append(a)
            other.append(b)
        self.assertEqual(_select(target, same[:2], "flat")["status"], "missing")
        self.assertEqual(_select(target, other + same, "flat")["files"], [a["path"] for a in same])

    def test_catalogue_match_does_not_depend_on_object_name(self):
        standard = frame("unexpected_label")
        standard["metadata"].update(RA=(23+19/60+58.4/3600)*15, DEC=-(5+9/60+56/3600))
        plan = build_plan(report([standard]), REFERENCE)
        self.assertEqual(plan["exposures"][0]["standard"]["name"], "feige110.dat")
        self.assertEqual(plan["exposures"][0]["role"], "standard")

    def test_incomplete_lamp_flats_do_not_silently_use_dome(self):
        target, lamp = frame(), frame("flat", "flat")
        dome = [frame(f"d{i}", "flat") for i in range(3)]
        for d in dome:
            d["metadata"]["OBJECT"] = "dome"
        self.assertEqual(_select(target, [lamp] + dome, "flat")["status"], "missing")

    def test_complete_raw_associations_do_not_claim_reduction_readiness(self):
        target, standard, arc = frame(), frame("standard", "standard_candidate"), frame("arc", "arc")
        standard["metadata"].update(RA=(23+19/60+58.4/3600)*15, DEC=-(5+9/60+56/3600))
        biases = [frame(f"bias{i}", "bias") for i in range(3)]
        flats = [frame(f"flat{i}", "flat") for i in range(3)]
        for f in flats:
            f["metadata"]["OBJECT"] = "flat"
        plan = build_plan(report([target, standard, arc] + biases + flats), REFERENCE)
        self.assertTrue(plan["associations_complete"])
        self.assertFalse(plan["reduction_ready"])

    def test_unmatched_standard_candidate_is_blocked(self):
        plan = build_plan(report([frame(role="standard_candidate")]), REFERENCE)
        self.assertTrue(any("Unmatched standard" in s for s in plan["blockers"]))
        self.assertFalse(plan["associations_complete"])

    def test_profiles_select_distinct_extinction_and_disable_rapid_corrections(self):
        full = build_plan(report([frame()]), REFERENCE)
        rapid = build_plan(report([frame()]), REFERENCE, "rapid")
        self.assertNotEqual(full["references"]["extinction_1d"]["sha256"],
                            rapid["references"]["extinction_1d"]["sha256"])
        self.assertEqual(rapid["exposures"][0]["calibrations"]["bias"]["status"], "disabled_by_profile")
        self.assertEqual(rapid["exposures"][0]["calibrations"]["flat"]["status"], "disabled_by_profile")
        self.assertFalse(rapid["reduction_ready"])

    def test_standard_association_is_setup_specific(self):
        target, standard = frame(), frame("std", "standard_candidate")
        standard["metadata"].update(RA=(23+19/60+58.4/3600)*15, DEC=-(5+9/60+56/3600))
        standard["setup"]["slit"] = "slit1.5"
        p = build_plan(report([target, standard]), REFERENCE)
        target_plan = next(e for e in p["exposures"] if e["path"] == target["path"])
        self.assertEqual(target_plan["calibrations"]["standard"]["status"], "missing")

    def test_invalid_metadata_prevents_partial_plan(self):
        bad = frame()
        bad["metadata"]["MJD-OBS"] = float("nan")
        plan = build_plan(report([bad]), REFERENCE)
        self.assertEqual(plan["exposures"], [])
        self.assertTrue(plan["invalid_inputs"])

    def test_archive_conflicts_prevent_plan(self):
        r = report([frame()])
        r["identity_conflicts"] = {"id": ["a", "b"]}
        self.assertEqual(build_plan(r, REFERENCE)["exposures"], [])

    def test_explicit_processed_arc_is_rejected(self):
        with self.assertRaisesRegex(ValueError, "inventoried raw arc"):
            build_plan(report([frame(), frame("master", "processed")]), REFERENCE,
                       explicit_arcs=["/data/master.fits"])

    def test_input_order_and_duplicate_content_do_not_change_plan(self):
        target, arc = frame(), frame("arc", "arc")
        duplicate = dict(arc, path="/data/copy.fits", duplicate_of=arc["path"])
        self.assertEqual(build_plan(report([target, arc]), REFERENCE),
                         build_plan(report([duplicate, arc, target]), REFERENCE))


if __name__ == "__main__":
    unittest.main()
