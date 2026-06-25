import argparse
import csv
import json
from pathlib import Path
from statistics import mean, median


def load_events(log_path):
    events = []
    with Path(log_path).open("r", encoding="utf-8") as log_file:
        for line in log_file:
            line = line.strip()
            if not line:
                continue
            events.append(json.loads(line))
    return events


def percentile(values, ratio):
    if not values:
        return None
    ordered = sorted(values)
    index = int(round((len(ordered) - 1) * ratio))
    return ordered[index]


def summarize_numeric(values):
    if not values:
        return None
    return {
        "count": len(values),
        "min": min(values),
        "mean": mean(values),
        "median": median(values),
        "p95": percentile(values, 0.95),
        "max": max(values),
    }


def load_annotations(annotation_path):
    annotations = {}
    with Path(annotation_path).open("r", encoding="utf-8") as annotation_file:
        reader = csv.DictReader(annotation_file)
        for row in reader:
            frame_id = int(row["frame_id"])
            outcome = row["outcome"].strip().lower()
            if outcome not in {"tp", "fp", "fn", "tn"}:
                raise ValueError(
                    "annotation outcome must be one of tp, fp, fn, tn"
                )
            annotations[frame_id] = outcome
    return annotations


def compute_precision(frame_events, annotations):
    outcomes = []
    for event in frame_events:
        frame_id = event["frame_id"]
        if frame_id in annotations:
            outcomes.append(annotations[frame_id])

    tp = sum(outcome == "tp" for outcome in outcomes)
    fp = sum(outcome == "fp" for outcome in outcomes)
    fn = sum(outcome == "fn" for outcome in outcomes)
    tn = sum(outcome == "tn" for outcome in outcomes)

    precision = None if tp + fp == 0 else (tp / (tp + fp)) * 100.0
    recall = None if tp + fn == 0 else (tp / (tp + fn)) * 100.0
    accuracy = None if tp + tn + fp + fn == 0 else (
        (tp + tn) / (tp + tn + fp + fn)
    ) * 100.0

    return {
        "annotated_frames": len(outcomes),
        "tp": tp,
        "fp": fp,
        "fn": fn,
        "tn": tn,
        "precision_percent": precision,
        "recall_percent": recall,
        "accuracy_percent": accuracy,
    }


def main():
    parser = argparse.ArgumentParser(
        description="Analyze Spectra YOLO metrics from structured JSONL logs."
    )
    parser.add_argument(
        "log_path",
        nargs="?",
        default="yolo/metrics_log.jsonl",
        help="Path to the structured metrics JSONL log",
    )
    parser.add_argument(
        "--annotations",
        help="Optional CSV with columns frame_id,outcome where outcome is tp/fp/fn/tn",
    )
    args = parser.parse_args()

    events = load_events(args.log_path)
    frame_events = [event for event in events if event["event"] == "frame_decision"]
    command_events = [event for event in events if event["event"] == "command_sent"]
    obstacle_events = [
        event
        for event in events
        if event["event"] == "obstacle_state" and event.get("blocked") is True
    ]

    tracking_errors = [
        abs(event["center_error_x"])
        for event in frame_events
        if event.get("center_error_x") is not None and event.get("target_visible")
    ]
    command_latencies = [
        event["command_latency_ms"]
        for event in command_events
        if event.get("command_latency_ms") is not None
    ]
    stopping_errors = [
        abs(event["stop_threshold_cm"] - event["distance_cm"])
        for event in obstacle_events
        if event.get("distance_cm") is not None
    ]

    print("Structured log summary")
    print(f"- events: {len(events)}")
    print(f"- frame decisions: {len(frame_events)}")
    print(f"- command sends: {len(command_events)}")
    print(f"- obstacle stops: {len(obstacle_events)}")

    tracking_summary = summarize_numeric(tracking_errors)
    if tracking_summary is not None:
        print("\nTracking error |x_object - x_center| (px)")
        print(
            "- count={count} min={min:.2f} mean={mean:.2f} median={median:.2f} "
            "p95={p95:.2f} max={max:.2f}".format(**tracking_summary)
        )

    latency_summary = summarize_numeric(command_latencies)
    if latency_summary is not None:
        print("\nCommand latency t_command_sent - t_detection (ms)")
        print(
            "- count={count} min={min:.3f} mean={mean:.3f} median={median:.3f} "
            "p95={p95:.3f} max={max:.3f}".format(**latency_summary)
        )

    stopping_summary = summarize_numeric(stopping_errors)
    if stopping_summary is not None:
        print("\nStopping error |d_stop_threshold - d_actual| (cm)")
        print(
            "- count={count} min={min:.2f} mean={mean:.2f} median={median:.2f} "
            "p95={p95:.2f} max={max:.2f}".format(**stopping_summary)
        )

    if args.annotations:
        precision_summary = compute_precision(
            frame_events,
            load_annotations(args.annotations),
        )
        print("\nDetection metrics from annotations")
        print(
            "- annotated_frames={annotated_frames} tp={tp} fp={fp} fn={fn} tn={tn}"
            .format(**precision_summary)
        )
        precision_percent = precision_summary["precision_percent"]
        recall_percent = precision_summary["recall_percent"]
        accuracy_percent = precision_summary["accuracy_percent"]
        if precision_percent is not None:
            print(f"- precision={precision_percent:.2f}%")
        if recall_percent is not None:
            print(f"- recall={recall_percent:.2f}%")
        if accuracy_percent is not None:
            print(f"- accuracy={accuracy_percent:.2f}%")
    else:
        print("\nDetection precision")
        print(
            "- not computable from runtime logs alone; supply --annotations "
            "with frame_id,outcome ground truth labels"
        )


if __name__ == "__main__":
    main()
