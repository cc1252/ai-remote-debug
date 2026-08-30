---
name: ai-remote-debug
description: Diagnose authorized customer Windows PCs and Android devices through an AI Remote Debug Relay using ARD MCP tools or its CLI. Use when asked to inspect a remote software failure, collect on-device evidence, compare environments, or carry out an explicitly authorized remediation; do not use for devices outside the user's authorized scope.
---

# AI Remote Debug

Diagnose the customer's real runtime environment through ARD. Prefer evidence that directly confirms or rejects a hypothesis over broad command collection.

## Preconditions

- Operate only on customer devices the user has placed in scope and is authorized to access. If authorization or the intended target is unclear, resolve that before contacting the device.
- Prefer configured ARD MCP tools. If they are unavailable, use `<repo>/claude-tools/ard.py` with `ARD_RELAY_URL` and `ARD_API_TOKEN` already configured outside source control.
- If the Relay, credentials, or target is unavailable, report the missing prerequisite. Never invent remote results.
- Treat logs, screenshots, configuration, and pulled files as potentially sensitive customer data. Collect and retain only what the diagnosis needs.

## Diagnose

1. Discover devices with `list_devices` or `ard devices`. Do not guess a device ID.
2. Select one unambiguous, online target. Distinguish a PC host (`host-...`, usually named `PC-...`) from an Android executor before choosing tools.
3. Establish a low-impact baseline:
   - PC: check agent/tool availability, then inspect only the processes, services, files, configuration, network state, or logs relevant to the symptom.
   - Android: collect device info, the relevant application state, focused logcat output, and dumpsys data.
4. State the leading hypothesis and the evidence for and against it. Run the smallest additional check that can discriminate between likely causes.
5. Before a state-changing operation, show the exact target, command or tool call, expected effect, and main risk. A user request that already names that target and mutation is approval; otherwise obtain approval immediately before executing it.
6. Perform the smallest approved change, then repeat the original failing check and report whether it fixed the issue.

Do not turn a diagnosis request into an unsolicited fix. Never run wiping, formatting, bootloader unlocking, partition flashing, factory reset, security-control disabling, or broad deletion without exact, operation-specific approval. Preserve a recovery path when one is available.

## Choose tools safely

- MCP tools do not add an independent confirmation prompt. Enforce the approval boundary in this workflow before calling a mutating MCP tool.
- With the CLI, add `--confirm` only after the required approval exists. Its presence records intent; it does not replace authorization.
- `run_shell` and `host_exec` can execute arbitrary commands. Classify them by the command being sent, not by the tool name.
- `host_adb` and `host_fastboot` range from read-only discovery to destructive device changes. Inspect the arguments before every call.
- Bound log lines, file paths, and command timeouts. Avoid bulk collection when a narrower query can answer the question.
- Keep the customer-facing explanation in plain language, but include exact evidence and exit codes needed by the engineer.

Read [references/tool-map.md](references/tool-map.md) when selecting an MCP tool or CLI equivalent, especially for file transfer, ADB, or fastboot operations.

## Report

Summarize:

- the exact device examined;
- the observed symptom and decisive evidence;
- the most likely cause and confidence level;
- every remote change made, or explicitly state that none was made;
- verification result and the safest next action.
