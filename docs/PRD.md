# Product Requirements

## Problem

Linux users with Logitech MX mice can use the hardware, but they do not get Logitech's proprietary shortcut and Actions Ring workflow. The missing piece is a Linux-native tool that maps mouse buttons to useful actions with minimal setup.

## Target user

A Linux laptop or desktop user with a Logitech MX mouse who wants one-press productivity shortcuts such as screenshots, app launch, window management, or context-aware actions.

## Goals

- Bind MX mouse buttons to user-defined actions.
- Support command execution and keyboard shortcut emission.
- Make screenshots a first-class built-in workflow.
- Provide an optional radial overlay (Phase 4 — shipped).

## Non-goals

- Reverse engineer Logitech firmware.
- Reproduce Logitech's proprietary software exactly.
- Support every Linux desktop environment equally in the first version.

## MVP

The MVP should:

- load TOML configuration
- define named actions
- bind a Linux input trigger to an action
- execute screenshot or shell command actions
- provide clear logs and error messages

## Success criteria

- a user can press one MX button and capture a screenshot
- configuration changes do not require code edits
- the system is modular enough to add overlay support later
- pressing and holding a configured button opens a ring; releasing on a segment fires its action.

