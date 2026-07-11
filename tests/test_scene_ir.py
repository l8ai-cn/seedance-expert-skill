from __future__ import annotations

import copy
import json
import random
import subprocess
import sys
import unittest
from pathlib import Path

from scripts import render_surface_bindings as bindings
from scripts import scene_ir_check as scene_check


ROOT = Path(__file__).resolve().parents[1]
SCRIPT = ROOT / "scripts" / "scene_ir_check.py"


def _event(
    event_id: str,
    index: int,
    phase: str,
    dependencies: list[str],
    *,
    actor_ids: list[str] | None = None,
    target_ids: list[str] | None = None,
    interaction: str = "none",
    material_ids: list[str] | None = None,
) -> dict:
    return {
        "event_id": event_id,
        "event_index": index,
        "phase": phase,
        "actor_ids": actor_ids if actor_ids is not None else ["performer"],
        "target_ids": target_ids if target_ids is not None else ["glass"],
        "depends_on": dependencies,
        "visible_state_change": f"The visible state advances at {phase}.",
        "interaction_kind": interaction,
        "material_ids": material_ids or [],
    }


def valid_scene(*, material_contact: bool = True) -> dict:
    decisive_interaction = "contact" if material_contact else "non_material_state_change"
    response_interaction = "material_change" if material_contact else "non_material_state_change"
    decisive_materials = ["glass_material"] if material_contact else []
    response_materials = ["glass_material"] if material_contact else []
    entities = [
        {
            "entity_id": "performer",
            "label": "Performer",
            "kind": "character",
            "stable_features": ["dark jacket", "readable silhouette"],
        },
        {
            "entity_id": "glass",
            "label": "Glass panel" if material_contact else "Stage light",
            "kind": "object" if material_contact else "effect",
            "stable_features": ["center-frame target"],
        },
    ]
    materials = (
        [
            {
                "material_id": "glass_material",
                "entity_id": "glass",
                "kind": "rigid",
                "response_properties": ["brittle", "transparent"],
            }
        ]
        if material_contact
        else []
    )
    events = [
        _event("start", 1, "initial_state", []),
        _event("cue", 2, "trigger", ["start"]),
        _event(
            "decision",
            3,
            "contact_or_state_change",
            ["cue"],
            interaction=decisive_interaction,
            material_ids=decisive_materials,
        ),
        _event(
            "response",
            4,
            "primary_response",
            ["decision"],
            interaction=response_interaction,
            material_ids=response_materials,
        ),
        _event("follow", 5, "follow_through", ["response"]),
        _event("endpoint", 6, "settled_endpoint", ["follow"]),
    ]
    if not material_contact:
        for event in events:
            event["target_ids"] = ["glass"]
        events[2]["visible_state_change"] = "The stage light changes from blue to warm amber."
        events[3]["visible_state_change"] = "Warm light reveals the performer's held expression."

    return {
        "$schema": scene_check.SCENE_IR_SCHEMA_URI,
        "schema_version": 1,
        "entities": entities,
        "materials": materials,
        "shots": [
            {
                "shot_id": "shot_one",
                "shot_index": 1,
                "events": events,
                "camera": {
                    "primary_move": {
                        "kind": "locked",
                        "start_framing": "Medium-wide frontal view.",
                        "path": "No translation or rotation.",
                        "speed": "static",
                        "subject_relationship": "Both subjects stay readable.",
                        "endpoint_framing": "The response remains unobstructed.",
                    },
                    "observability": {
                        "before_state_event_id": "start",
                        "decisive_event_id": "decision",
                        "consequence_event_ids": ["response"],
                        "endpoint_event_id": "endpoint",
                        "occlusion_risks": ["The performer's hand may cross the target."],
                        "mitigations": ["Keep the hand below the target center."],
                    },
                },
            }
        ],
        "audio_events": [
            {
                "audio_event_id": "sound_one",
                "shot_id": "shot_one",
                "linked_event_id": "decision",
                "temporal_relationship": "on_contact_or_state_change",
                "semantic_function": "sound_effect" if material_contact else "ambience",
                "source_entity_ids": ["glass"],
                "description": "A short synchronized cue is audible.",
            }
        ],
        "requested_invariants": [
            {
                "invariant_id": "identity_stable",
                "entity_ids": ["performer"],
                "description": "The performer remains recognizably the same person.",
            }
        ],
        "known_fragilities": [
            {
                "fragility_id": "response_visibility",
                "event_ids": ["decision", "response"],
                "description": "The decisive change and response may visually merge.",
            }
        ],
        "acceptance_tests": [
            {
                "acceptance_id": "causal_read",
                "event_ids": ["start", "decision", "response", "endpoint"],
                "observable": "The before-state, change, response, and endpoint are distinct.",
                "pass_condition": "A reviewer can order all four states without prompt access.",
            }
        ],
        "post_fallbacks": [
            {
                "fallback_id": "simplify_take",
                "trigger_acceptance_ids": ["causal_read"],
                "action": "Shorten the motion path and preserve the endpoint.",
            }
        ],
    }


class SceneIRTests(unittest.TestCase):
    def assert_scene_error(self, scene: dict, code: str) -> None:
        with self.assertRaises(bindings.BindingError) as caught:
            scene_check.validate_scene_ir(scene)
        self.assertEqual(caught.exception.code, code)

    def test_material_contact_and_quiet_non_material_performance_are_valid(self) -> None:
        contact = valid_scene()
        quiet = valid_scene(material_contact=False)
        self.assertIs(scene_check.validate_scene_ir(contact), contact)
        self.assertIs(scene_check.validate_scene_ir(quiet), quiet)
        self.assertEqual(
            scene_check.causal_order(contact),
            [
                {
                    "shot_id": "shot_one",
                    "event_ids": ["start", "cue", "decision", "response", "follow", "endpoint"],
                }
            ],
        )

    def test_phase_order_cardinality_and_bool_integer_are_fail_closed(self) -> None:
        missing_initial = valid_scene()
        missing_events = missing_initial["shots"][0]["events"]
        missing_events.pop(0)
        secondary = copy.deepcopy(missing_events[2])
        secondary["event_id"] = "secondary"
        secondary["phase"] = "secondary_response"
        missing_events.insert(3, secondary)
        for index, event in enumerate(missing_events, start=1):
            event["event_index"] = index
        self.assert_scene_error(missing_initial, "EVT001_INITIAL_STATE_REQUIRED")

        out_of_order = valid_scene()
        out_of_order["shots"][0]["events"][1]["phase"] = "primary_response"
        self.assert_scene_error(out_of_order, "EVT003_PHASE_ORDER_INVALID")

        bool_index = valid_scene()
        bool_index["shots"][0]["shot_index"] = True
        self.assert_scene_error(bool_index, "EVT003_SHOT_ORDER_INVALID")

    def test_dependency_future_cycle_bypass_and_endpoint_reachability_fail(self) -> None:
        future_cycle = valid_scene()
        future_cycle["shots"][0]["events"][1]["depends_on"] = ["decision"]
        self.assert_scene_error(future_cycle, "EVT003_FUTURE_DEPENDENCY")

        bypass = valid_scene()
        bypass["shots"][0]["events"][3]["depends_on"] = ["cue"]
        self.assert_scene_error(bypass, "EVT004_CAUSAL_CHAIN_UNREACHABLE")

        endpoint = valid_scene()
        endpoint["shots"][0]["events"][5]["depends_on"] = ["decision"]
        self.assert_scene_error(endpoint, "EVT004_CAUSAL_CHAIN_UNREACHABLE")

        unknown = valid_scene()
        unknown["shots"][0]["events"][2]["depends_on"] = ["missing"]
        self.assert_scene_error(unknown, "EVT003_DEPENDENCY_UNKNOWN")

    def test_decisive_event_requires_a_visible_typed_consequence(self) -> None:
        no_material_response = valid_scene()
        no_material_response["shots"][0]["events"][3]["interaction_kind"] = "none"
        no_material_response["shots"][0]["events"][3]["material_ids"] = []
        self.assert_scene_error(no_material_response, "EVT002_MATERIAL_RESPONSE_REQUIRED")

        no_state_response = valid_scene(material_contact=False)
        no_state_response["shots"][0]["events"][3]["interaction_kind"] = "none"
        self.assert_scene_error(no_state_response, "EVT002_VISIBLE_CONSEQUENCE_REQUIRED")

        invented_material = valid_scene(material_contact=False)
        invented_material["shots"][0]["events"][2]["material_ids"] = ["missing_material"]
        self.assert_scene_error(invented_material, "EVENT_MATERIAL_UNKNOWN")

        contact_without_material = valid_scene()
        contact_without_material["shots"][0]["events"][2]["material_ids"] = []
        self.assert_scene_error(contact_without_material, "EVT002_MATERIAL_RESPONSE_REQUIRED")

        contact_during_trigger = valid_scene()
        contact_during_trigger["shots"][0]["events"][1]["interaction_kind"] = "contact"
        contact_during_trigger["shots"][0]["events"][1]["material_ids"] = ["glass_material"]
        self.assert_scene_error(contact_during_trigger, "EVT003_PHASE_INTERACTION_INVALID")

        unrelated_material = valid_scene()
        unrelated_material["entities"].append(
            {
                "entity_id": "bystander_prop",
                "label": "unrelated rigid prop",
                "kind": "object",
                "stable_features": ["outside the contact pair"],
            }
        )
        unrelated_material["materials"].append(
            {
                "material_id": "unrelated_material",
                "entity_id": "bystander_prop",
                "kind": "rigid",
                "response_properties": ["remains still"],
            }
        )
        unrelated_material["shots"][0]["events"][2]["material_ids"] = [
            "unrelated_material"
        ]
        self.assert_scene_error(
            unrelated_material,
            "EVENT_MATERIAL_OWNER_NOT_PARTICIPANT",
        )

    def test_camera_observability_is_event_exact_and_allows_one_primary_move(self) -> None:
        missing_response = valid_scene()
        missing_response["shots"][0]["camera"]["observability"]["consequence_event_ids"] = ["follow"]
        self.assert_scene_error(missing_response, "EVT005_PRIMARY_RESPONSE_NOT_OBSERVED")

        wrong_decisive = valid_scene()
        wrong_decisive["shots"][0]["camera"]["observability"]["decisive_event_id"] = "cue"
        self.assert_scene_error(wrong_decisive, "EVT005_CAMERA_PHASE_MISMATCH")

        occluded = valid_scene()
        occluded["shots"][0]["camera"]["observability"]["mitigations"] = []
        self.assert_scene_error(occluded, "EVT005_OCCLUSION_UNMITIGATED")

        second_move = valid_scene()
        second_move["shots"][0]["camera"]["secondary_move"] = copy.deepcopy(
            second_move["shots"][0]["camera"]["primary_move"]
        )
        self.assert_scene_error(second_move, "OBJECT_FIELDS_INVALID")

        locked_motion = valid_scene()
        locked_motion["shots"][0]["camera"]["primary_move"]["speed"] = "slow"
        self.assert_scene_error(locked_motion, "CAM002_LOCKED_SPEED_MISMATCH")

    def test_audio_temporal_relationship_and_semantic_function_remain_separate(self) -> None:
        temporal = valid_scene()
        temporal["audio_events"][0]["temporal_relationship"] = "sfx"
        self.assert_scene_error(temporal, "AUDIO001_TEMPORAL_RELATIONSHIP_INVALID")

        wrong_phase = valid_scene()
        wrong_phase["audio_events"][0]["temporal_relationship"] = "on_trigger"
        self.assert_scene_error(wrong_phase, "AUDIO001_TEMPORAL_EVENT_MISMATCH")

        semantic = valid_scene()
        semantic["audio_events"][0]["semantic_function"] = "on_trigger"
        self.assert_scene_error(semantic, "AUDIO001_SEMANTIC_FUNCTION_INVALID")

        cross_shot = valid_scene()
        cross_shot["audio_events"][0]["linked_event_id"] = "missing"
        self.assert_scene_error(cross_shot, "AUDIO_EVENT_LINK_INVALID")

    def test_endpoint_must_have_an_observable_acceptance_test(self) -> None:
        scene = valid_scene()
        scene["acceptance_tests"][0]["event_ids"].remove("endpoint")
        self.assert_scene_error(scene, "EVT004_ENDPOINT_NOT_ACCEPTANCE_LINKED")

    def test_strict_json_parser_rejects_malformed_ambiguous_and_unsafe_input_without_echo(self) -> None:
        hostile = [
            (b'{"sentinel":1,"sentinel":2}', "JSON_DUPLICATE_KEY"),
            (b"\xef\xbb\xbf{}", "JSON_BOM_FORBIDDEN"),
            (b'{"x":"\xff"}', "JSON_UTF8_REQUIRED"),
            (b'{"x":NaN}', "JSON_NONFINITE_NUMBER"),
            (b'{"x":' + b"9" * 129 + b"}", "JSON_NUMBER_OUT_OF_RANGE"),
            (b'{"x":"\\ud800"}', "UNICODE_SURROGATE_FORBIDDEN"),
            (b'{"x":"a\\u202eb"}', "UNICODE_FORMAT_CONTROL_FORBIDDEN"),
            (b'{"x":' + b"[" * 60 + b"0" + b"]" * 60 + b"}", "JSON_TOO_DEEP"),
        ]
        for raw, code in hostile:
            with self.subTest(code=code), self.assertRaises(bindings.BindingError) as caught:
                bindings.parse_json_bytes(raw)
            self.assertEqual(caught.exception.code, code)
            self.assertNotIn("sentinel", str(caught.exception))

        control = valid_scene()
        control["entities"][0]["label"] = "secret\u0085sentinel"
        self.assert_scene_error(control, "TEXT_CONTROL_FORBIDDEN")
        invalid_zwj = valid_scene()
        invalid_zwj["entities"][0]["label"] = "secret a\u200db sentinel"
        self.assert_scene_error(invalid_zwj, "UNICODE_FORMAT_CONTROL_FORBIDDEN")

        process = subprocess.run(
            [sys.executable, str(SCRIPT)],
            input=b'{"do-not-echo-me":1,"do-not-echo-me":2}',
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            cwd=ROOT,
            check=False,
        )
        self.assertEqual(process.returncode, 1)
        self.assertEqual(process.stdout, b"")
        self.assertIn(b"JSON_DUPLICATE_KEY", process.stderr)
        self.assertNotIn(b"do-not-echo-me", process.stderr)

    def test_schema_and_runtime_text_boundaries_stay_in_lockstep(self) -> None:
        schema = json.loads((ROOT / "schemas" / "scene-ir.schema.json").read_text(encoding="utf-8"))
        self.assertEqual(schema["$defs"]["bounded_text"]["maxLength"], 1_000)
        self.assertEqual(
            schema["$defs"]["entity"]["properties"]["stable_features"]["items"]["maxLength"],
            200,
        )
        self.assertEqual(
            schema["$defs"]["material"]["properties"]["response_properties"]["items"]["maxLength"],
            200,
        )
        self.assertEqual(schema["properties"]["acceptance_tests"]["maxItems"], 128)

        at_limits = valid_scene()
        at_limits["entities"][0]["label"] = "x" * 1_000
        at_limits["entities"][0]["stable_features"][0] = "y" * 200
        at_limits["materials"][0]["response_properties"][0] = "z" * 200
        self.assertIs(scene_check.validate_scene_ir(at_limits), at_limits)

        over_general = valid_scene()
        over_general["entities"][0]["label"] = "x" * 1_001
        self.assert_scene_error(over_general, "TEXT_INVALID")
        over_item = valid_scene()
        over_item["entities"][0]["stable_features"][0] = "y" * 201
        self.assert_scene_error(over_item, "TEXT_INVALID")
        locator = valid_scene()
        locator["shots"][0]["events"][0]["visible_state_change"] = "See https://secret.invalid/media."
        self.assert_scene_error(locator, "TEXT_LOCATOR_FORBIDDEN")

        acceptance_boundary = valid_scene()
        template = acceptance_boundary["acceptance_tests"][0]
        acceptance_boundary["acceptance_tests"] = [
            {**copy.deepcopy(template), "acceptance_id": f"acceptance_{index}"}
            for index in range(128)
        ]
        acceptance_boundary["post_fallbacks"][0]["trigger_acceptance_ids"] = [
            "acceptance_0"
        ]
        self.assertIs(scene_check.validate_scene_ir(acceptance_boundary), acceptance_boundary)
        acceptance_boundary["acceptance_tests"].append(
            {**copy.deepcopy(template), "acceptance_id": "acceptance_128"}
        )
        self.assert_scene_error(acceptance_boundary, "ARRAY_BOUNDS_INVALID")

    def test_cli_output_and_hash_are_canonical_across_ten_repeated_passes(self) -> None:
        raw = json.dumps(valid_scene(), ensure_ascii=False, indent=2).encode("utf-8")
        outputs = []
        for _ in range(10):
            process = subprocess.run(
                [sys.executable, str(SCRIPT)],
                input=raw,
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
                cwd=ROOT,
                check=False,
            )
            self.assertEqual(process.returncode, 0, process.stderr.decode("utf-8"))
            self.assertEqual(process.stderr, b"")
            outputs.append(process.stdout)
        self.assertTrue(all(output == outputs[0] for output in outputs))
        report = json.loads(outputs[0])
        self.assertEqual(report["status"], "valid")
        self.assertEqual(
            report["scene_ir_sha256"],
            bindings.sha256_bytes(bindings.canonical_json(valid_scene())),
        )

    def test_ten_thousand_seeded_safe_text_mutations_validate(self) -> None:
        rng = random.Random(706)
        alphabet = [*" abcdefghijklmnopqrstuvwxyz0123456789", "人", "物", "光", "é", "🚀"]
        scene = valid_scene(material_contact=False)
        for index in range(10_000):
            suffix = "".join(rng.choice(alphabet) for _ in range(rng.randint(1, 24))).strip() or "x"
            scene["entities"][0]["label"] = f"Performer {index} {suffix}"
            scene["shots"][0]["events"][3]["visible_state_change"] = f"Visible response {index}: {suffix}."
            self.assertIs(scene_check.validate_scene_ir(scene), scene)


if __name__ == "__main__":
    unittest.main()
