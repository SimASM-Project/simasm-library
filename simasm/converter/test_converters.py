"""
Test script for JSON to SimASM converters.

Tests both Event Graph and ACD converters with the MM5 queue example.
"""

import json
from pathlib import Path

# Add parent directory to path for imports
import sys
sys.path.insert(0, str(Path(__file__).parent.parent.parent))

from simasm.converter.event_graph.schema import PureEventGraphSpec
from simasm.converter.event_graph.converter import PureEventGraphConverter, convert_pure_event_graph
from simasm.converter.acd.schema import ACDSpec, create_mm5_acd_spec
from simasm.converter.acd.converter import ACDConverter, convert_acd


def test_event_graph_pure_json():
    """Test Pure Event Graph converter from JSON file."""
    print("=" * 70)
    print("TEST: Event Graph from Pure JSON")
    print("=" * 70)

    # Load JSON
    json_path = Path(__file__).parent / "examples" / "mm5_event_graph_pure.json"
    if not json_path.exists():
        print(f"JSON file not found: {json_path}")
        return False

    with open(json_path) as f:
        data = json.load(f)

    # Parse to spec
    spec = PureEventGraphSpec(**data)

    # Validate
    errors = spec.validate_graph()
    if errors:
        print("Validation errors:")
        for e in errors:
            print(f"  - {e}")
        return False

    # Convert
    code = convert_pure_event_graph(spec)

    # Save output
    output_path = Path(__file__).parent / "examples" / "mm5_eg_pure_generated.simasm"
    with open(output_path, "w") as f:
        f.write(code)

    print(f"\nGenerated code saved to: {output_path}")
    print(f"Total lines: {len(code.split(chr(10)))}")

    # Print first 200 lines
    print("\nGenerated SimASM code (first 200 lines):")
    print("-" * 70)
    lines = code.split("\n")
    for line in lines[:200]:
        print(line)
    if len(lines) > 200:
        print(f"... ({len(lines) - 200} more lines)")

    return True


def test_acd_from_factory():
    """Test ACD converter using factory function."""
    print("\n" + "=" * 70)
    print("TEST: ACD from Factory")
    print("=" * 70)

    # Create spec from factory
    spec = create_mm5_acd_spec()

    # Validate
    errors = spec.validate_model()
    if errors:
        print("Validation errors:")
        for e in errors:
            print(f"  - {e}")
        return False

    # Convert
    code = convert_acd(spec)

    print("\nGenerated SimASM code (first 100 lines):")
    print("-" * 70)
    lines = code.split("\n")
    for line in lines[:100]:
        print(line)
    if len(lines) > 100:
        print(f"... ({len(lines) - 100} more lines)")

    return True


def test_acd_from_json():
    """Test ACD converter from JSON file."""
    print("\n" + "=" * 70)
    print("TEST: ACD from JSON")
    print("=" * 70)

    # Load JSON
    json_path = Path(__file__).parent / "examples" / "mm5_acd.json"
    if not json_path.exists():
        print(f"JSON file not found: {json_path}")
        return False

    with open(json_path) as f:
        data = json.load(f)

    # Parse to spec
    spec = ACDSpec(**data)

    # Validate
    errors = spec.validate_model()
    if errors:
        print("Validation errors:")
        for e in errors:
            print(f"  - {e}")

    # Convert
    code = convert_acd(spec)

    # Save output
    output_path = Path(__file__).parent / "examples" / "mm5_acd_generated.simasm"
    with open(output_path, "w") as f:
        f.write(code)

    print(f"\nGenerated code saved to: {output_path}")
    print(f"Total lines: {len(code.split(chr(10)))}")

    return True


def main():
    """Run all tests."""
    print("SimASM Converter Tests")
    print("=" * 70)

    results = []

    # Test Event Graph
    results.append(("Event Graph (Pure JSON)", test_event_graph_pure_json()))

    # Test ACD
    results.append(("ACD (Factory)", test_acd_from_factory()))
    results.append(("ACD (JSON)", test_acd_from_json()))

    # Summary
    print("\n" + "=" * 70)
    print("TEST SUMMARY")
    print("=" * 70)

    for name, passed in results:
        status = "PASS" if passed else "FAIL"
        print(f"  {name}: {status}")

    all_passed = all(r[1] for r in results)
    print(f"\nOverall: {'ALL TESTS PASSED' if all_passed else 'SOME TESTS FAILED'}")

    return 0 if all_passed else 1


if __name__ == "__main__":
    exit(main())
