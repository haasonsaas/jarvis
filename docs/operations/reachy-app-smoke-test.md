# Reachy App Smoke Test

Use this runbook after app packaging changes, before publishing a new Hugging Face Space revision, and after any robot-audio or operator-UI changes.

## Local Contract Check

Run the automated contract checks first:

```bash
./scripts/reachy_app_smoke.sh --reinstall
```

That validates:
- `reachy-mini-app-assistant check .`
- `reachy_mini_apps` entry-point registration
- optional editable reinstall into the active environment

## Local Dashboard Path

If `reachy-mini-daemon` is available locally, run:

```bash
./scripts/reachy_app_smoke.sh --daemon --reinstall
```

Expected outcome:
- daemon becomes reachable at `http://127.0.0.1:8000/`
- Jarvis appears in installed apps
- app can be started and stopped from the dashboard
- settings UI opens without 500s

## Hardware Checklist

Validate these on an actual Reachy Mini before treating a release as production-ready:

1. Install Jarvis from the dashboard's Hugging Face app browser.
2. Launch the app and wait for the settings panel to report healthy runtime status.
3. Open the settings UI and verify:
   - readiness summary is populated
   - startup diagnostics are visible
   - control actions return success payloads
4. Exercise low-risk controls:
   - `Wake Word`
   - `Sleep`
   - `Wake`
   - `Motion Off`
   - `Motion On`
5. Verify embodied behavior:
   - head and antenna idle behavior starts
   - motion toggles apply immediately
   - stop action returns the app to an idle/stopped state
6. Verify audio path:
   - microphone input is accepted
   - first response audio plays
   - barge-in interrupts playback cleanly
7. Verify failure path:
   - disconnect or disable one optional subsystem if possible
   - confirm the UI surfaces the degraded capability instead of hanging

## Publish Gate

Do not request official app-store inclusion until:
- contract checks pass
- dashboard smoke path passes
- at least one real hardware smoke run completes cleanly
