#!/usr/bin/env python3
# Copyright 2026 EasyFly Project
#
# Licensed under the Apache License, Version 2.0 (the "License");
# you may not use this file except in compliance with the License.
# You may obtain a copy of the License at
#
#     http://www.apache.org/licenses/LICENSE-2.0
#
# Unless required by applicable law or agreed to in writing, software
# distributed under the License is distributed on an "AS IS" BASIS,
# WITHOUT WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied.
# See the License for the specific language governing permissions and
# limitations under the License.

"""Offline PNG replay through actual ef_tag::estimate; never start ROS or flight."""

import argparse
from collections import Counter
import hashlib
import json
import math
from pathlib import Path
import re
import shlex
import subprocess
import xml.etree.ElementTree as ET

from easyfly_precision_landing.geometry import transform
from PIL import Image
import yaml


def load_calibrations(artifact, exact=None):
    """Retain explicit provenance: SDF assumptions or externally captured K/D."""
    if exact:
        document = json.loads(Path(exact).read_text())
        samples = document.get("observation_samples", [document])
        models = [sample.get("camera_info", sample) for sample in samples]
        models = [sample for sample in models if "K" in sample or "k" in sample]
        if not models:
            raise ValueError("calibration JSON needs K/D or camera_info observation samples")
        unique = {}
        for sample in models:
            K, D = sample.get("K", sample.get("k")), sample.get("D", sample.get("d", []))
            if len(K) != 9 or len(D) not in (0, 5, 8) or not all(math.isfinite(v) for v in K + D):
                raise ValueError("finite conventional K/D required")
            if K[0] <= 0 or K[4] <= 0 or [K[i] for i in (1, 3, 6, 7, 8)] != [0, 0, 0, 0, 1]:
                raise ValueError("conventional positive K required")
            model = {
                "K": K,
                "D": D,
                "provenance": str(Path(exact).resolve()),
                "same_run_calibration_certified": False,
            }
            unique[json.dumps([K, D])] = model
        return list(unique.values())
    sensor = ET.parse(artifact / "down_iris.sdf").find(".//sensor[@name='down_color']/camera")
    width, height = int(sensor.findtext("image/width")), int(sensor.findtext("image/height"))
    focal = width / (2 * math.tan(float(sensor.findtext("horizontal_fov")) / 2))
    return [
        {
            "K": [focal, 0, cx, 0, focal, cy, 0, 0, 1],
            "D": [0.0] * 5,
            "provenance": "SDF-derived fx=fy and assumed zero distortion, NOT captured CameraInfo",
            "same_run_calibration_certified": False,
        }
        for cx, cy in ((width / 2, height / 2), ((width - 1) / 2, (height - 1) / 2))
    ]


def image_sources(path, result):
    """Match raw RGB/BGR hashes; use capture index only after a hash cross-check."""
    pixels = Image.open(path).convert("RGB").tobytes()
    hashes = {
        "rgb8": hashlib.sha256(pixels).hexdigest(),
        "bgr8": hashlib.sha256(
            bytes(
                value
                for offset in range(0, len(pixels), 3)
                for value in (pixels[offset + 2], pixels[offset + 1], pixels[offset])
            )
        ).hexdigest(),
    }
    samples = [s for s in result.get("observation_samples", []) if "image_sha256" in s]
    match = re.fullmatch(r"camera_(\d+)\.png", path.name)
    index = int(match[1]) if match else None
    if index and index <= len(samples) and samples[index - 1]["image_sha256"] in hashes.values():
        return hashes, [samples[index - 1]], "capture_index_and_exact_raw_hash"
    return (
        hashes,
        [s for s in samples if s["image_sha256"] in hashes.values()],
        "hash_matches_only_preserve_ambiguity",
    )


def state_envelope(source, flight, candidate, config):
    """Retain all nearest-stamp states; never guess receipt or choose one duplicate."""
    if not flight:
        return {"states": [], "reason": "no_flight_samples"}
    if candidate["translation"][2] <= 0:
        return {"states": [], "reason": "candidate_nonpositive_depth"}
    gap = min(abs(round(s["stamp"] * 1e9) - source) for s in flight)
    matched = [s for s in flight if abs(round(s["stamp"] * 1e9) - source) == gap]
    output = {
        "source_ns": source,
        "source_gap_s": gap * 1e-9,
        "states": matched,
        "receipt_and_actual_pair_unknown": True,
        "within_pair_gap": gap <= 100000000,
    }
    if gap > 100000000:
        return output
    geometries = []
    for state in matched:
        center, normal = transform(
            candidate["translation"],
            candidate["quaternion"],
            config["camera_translation_flu"],
            config["camera_quaternion_xyzw"],
            [state[k] for k in ("x", "y", "z")],
            [state[k] for k in ("roll", "pitch", "yaw")],
        )
        error = abs(center[2] - config["landing_plane_z_m"])
        tilt = math.acos(min(1.0, abs(normal[2])))
        geometries.append(
            {
                "center": center,
                "normal": normal,
                "plane_error_m": error,
                "tilt_rad": tilt,
                "height_rejected": error > config["plane_height_tolerance_m"],
                "tilt_rejected": tilt > config["plane_tilt_limit_rad"],
            }
        )
    output["geometry_hypotheses"] = geometries
    return output


def main():
    """Compile only a new helper, read inputs, and save exclusive offline evidence."""
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--artifact", required=True)
    parser.add_argument("--output", required=True)
    parser.add_argument("--calibration-json")
    args = parser.parse_args()
    artifact = Path(args.artifact).resolve(strict=True)
    output = Path(args.output).resolve()
    output.mkdir(exist_ok=False)
    workspace = Path(__file__).resolve().parents[5]
    header = (
        workspace / "src/perception/p2_detection/easyfly_apriltag_detection/include/tag_core.hpp"
    )
    helper = Path(__file__).with_suffix(".cpp")
    binary = output / "replay_tag_frames"
    flags = shlex.split(
        subprocess.check_output(["pkg-config", "--cflags", "--libs", "opencv4"], text=True)
    )
    header_sha = hashlib.sha256(header.read_bytes()).hexdigest()
    subprocess.run(
        ["c++", "-std=c++17", "-O2", "-I", str(header.parent), str(helper), "-o", str(binary)]
        + flags,
        check=True,
    )
    if hashlib.sha256(header.read_bytes()).hexdigest() != header_sha:
        raise RuntimeError("production header changed during helper compilation")
    result = json.loads((artifact / "result.json").read_text())
    configuration = yaml.safe_load((artifact / "config.yaml").read_text())
    geometry = configuration["landing_transform"]["ros__parameters"]
    detector = configuration["apriltag_detection"]["ros__parameters"]
    calibration = load_calibrations(artifact, args.calibration_json)
    report = {
        "artifact": str(artifact),
        "header_sha256": header_sha,
        "helper_sha256": hashlib.sha256(helper.read_bytes()).hexdigest(),
        "calibrations": calibration,
        "limitations": [
            "Current source replay, not certified identical old binary",
            "No exact CameraInfo in original run",
            "State samples subsampled and duplicate ROS stamps preserved; "
            "no first receipt reconstructed",
        ],
        "frames": [],
    }
    reasons = Counter()
    geometry_reasons = Counter()
    for image in sorted(artifact.glob("camera_*.png")):
        hashes, samples, association = image_sources(image, result)
        frame = {
            "image": image.name,
            "raw_hashes": hashes,
            "source_association": association,
            "source_matches": samples,
            "replays": [],
        }
        for index, model in enumerate(calibration):
            model_path = output / f"calibration_{index}.json"
            if not model_path.exists():
                model_path.write_text(json.dumps({"K": model["K"], "D": model["D"]}))
            for mode in ("none", "production"):
                command = [
                    str(binary),
                    str(image),
                    str(model_path),
                    str(detector["tag_size_m"]),
                    str(detector.get("max_reprojection_error_px", 2.0)),
                    str(detector.get("ambiguity_margin_px", 0.2)),
                    mode,
                ]
                replay = json.loads(subprocess.check_output(command, text=True))
                replay.update({"calibration_index": index, "detector_mode": mode})
                for tag in replay["tags"]:
                    reasons[f"{mode}/K{index}/{tag['reason']}"] += 1
                    for candidate in tag["candidates"]:
                        candidate["state_alignments"] = [
                            state_envelope(
                                s["source_ns"],
                                result.get("flight_samples", []),
                                candidate,
                                geometry,
                            )
                            for s in samples
                        ]
                    if tag["valid"]:
                        selected = {
                            "translation": tag["selected_translation"],
                            "quaternion": tag["selected_quaternion"],
                        }
                        tag["selected_state_alignments"] = [
                            state_envelope(
                                s["source_ns"],
                                result.get("flight_samples", []),
                                selected,
                                geometry,
                            )
                            for s in samples
                        ]
                        for alignment in tag["selected_state_alignments"]:
                            hypotheses = alignment.get("geometry_hypotheses", [])
                            if not hypotheses:
                                geometry_reasons[f"{mode}/K{index}/no_certifiable_state_pair"] += 1
                            else:
                                for hypothesis in hypotheses:
                                    rejection = (
                                        "height_and_tilt"
                                        if hypothesis["height_rejected"]
                                        and hypothesis["tilt_rejected"]
                                        else "height"
                                        if hypothesis["height_rejected"]
                                        else "tilt"
                                        if hypothesis["tilt_rejected"]
                                        else "accepted_geometry"
                                    )
                                    geometry_reasons[f"{mode}/K{index}/{rejection}"] += 1
                frame["replays"].append(replay)
        report["frames"].append(frame)
    report["summary"] = dict(reasons)
    report["geometry_hypothesis_summary"] = dict(geometry_reasons)
    latest = artifact / "latest_down_camera.png"
    if latest.is_file():
        hashes, samples, association = image_sources(latest, result)
        report["latest_saved_png"] = {
            "image": latest.name,
            "raw_hashes": hashes,
            "source_matches": samples,
            "source_association": association,
            "same_pixels_as_replayed": [
                frame["image"] for frame in report["frames"] if frame["raw_hashes"] == hashes
            ],
            "not_counted_twice_in_capture_summary": True,
        }
    (output / "replay.json").write_text(json.dumps(report, indent=2, allow_nan=False))
    print(
        json.dumps(
            {"frames": len(report["frames"]), "summary": report["summary"], "output": str(output)}
        )
    )


if __name__ == "__main__":
    main()
