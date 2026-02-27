#!/usr/bin/env bash
set -euo pipefail

uv run pytest -q \
  tests/test_robot_controller.py \
  tests/test_tools_robot.py \
  tests/test_presence.py \
  tests/test_integration.py \
  tests/test_intended_query.py \
  tests/test_turn_taking.py \
  tests/test_main_lifecycle.py::test_operator_control_handler_validates_and_applies_runtime_controls \
  tests/test_main_lifecycle.py::test_runtime_state_persists_and_restores_runtime_controls \
  tests/test_main_lifecycle.py::test_with_voice_profile_guidance_applies_non_default_verbosity \
  tests/test_main_lifecycle.py::test_with_voice_profile_guidance_applies_tone_preference
