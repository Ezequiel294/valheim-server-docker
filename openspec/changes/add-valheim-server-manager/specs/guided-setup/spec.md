## Purpose

Provides a guided question-and-answer flow that turns plain-language answers into a clean, minimal instance configuration, exposing the container's large option surface without forcing the user through all of it.

## ADDED Requirements

### Requirement: Setup asks essentials first

The wizard SHALL open with a short round covering only what is needed for a working server: the instance name, the name shown in the server browser, the world name, the password, whether the server is publicly listed, and whether crossplay is enabled. A user who answers only this round SHALL end with a complete, runnable configuration.

#### Scenario: Accepting defaults through the essentials round

- **WHEN** a user answers only the essentials and declines all further configuration
- **THEN** a valid runnable instance is written, containing the essentials and nothing the user did not choose

### Requirement: Advanced configuration is opt-in and gated per topic

Beyond the essentials the wizard SHALL offer advanced configuration, and within it SHALL gate each topic group behind its own question so a declined group is skipped entirely. Topic groups SHALL cover at minimum: gameplay world modifiers, access control, backups, scheduling, notifications, monitoring, and log filtering.

#### Scenario: Taking one advanced topic and declining the rest

- **WHEN** a user opts into advanced configuration, accepts the backups topic, and declines every other topic
- **THEN** the wizard asks only backup questions and the generated file contains no scheduling, notification, monitoring, or log-filter settings

#### Scenario: Declining advanced configuration entirely

- **WHEN** a user declines advanced configuration
- **THEN** no topic questions are asked and the generated file contains only essentials

### Requirement: Generated configuration contains only what was chosen

The wizard SHALL write only the settings the user actively selected. A setting left at its container default SHALL be omitted rather than written out explicitly.

#### Scenario: Untouched settings are absent

- **WHEN** a user leaves a setting at its default
- **THEN** that setting does not appear in the generated file

### Requirement: Every question can explain itself

The wizard SHALL accept a help request at any prompt, printing an explanation of what the setting does and its consequences, then re-asking without advancing.

#### Scenario: Requesting help mid-prompt

- **WHEN** a user requests help at a prompt
- **THEN** an explanation is printed and the same prompt is asked again

### Requirement: Invalid answers are rejected before they reach the server

The wizard SHALL validate answers whose invalid values would cause the server to fail or misbehave, re-prompting rather than writing an unusable file. At minimum it SHALL enforce that the instance name is usable as a directory and container name, and that a non-empty password meets the server's minimum length.

#### Scenario: Password below the server's minimum length

- **WHEN** a user enters a non-empty password shorter than the server's minimum
- **THEN** the wizard explains the minimum and re-prompts, and the short password is never written

#### Scenario: Instance name containing unusable characters

- **WHEN** a user enters an instance name containing characters not valid in a directory or container name
- **THEN** the wizard explains the allowed characters and re-prompts

#### Scenario: Instance name already taken

- **WHEN** a user enters an instance name that already exists
- **THEN** the wizard reports the collision and re-prompts rather than overwriting

### Requirement: Gameplay settings are emitted as correctly ordered server arguments

Valheim's gameplay settings are command-line arguments rather than environment variables, and a preset appearing after an individual modifier silently discards that modifier. The wizard SHALL emit the arguments it builds in an order where earlier selections cannot be discarded by later ones.

#### Scenario: Preset combined with an individual modifier

- **WHEN** a user selects a difficulty preset and also overrides an individual modifier
- **THEN** the generated arguments place the preset before the modifier, so the override survives

#### Scenario: No gameplay settings chosen

- **WHEN** a user declines the gameplay topic
- **THEN** no gameplay argument setting is written and the world uses its own defaults

### Requirement: Setup is confirmed before anything is written

The wizard SHALL present a summary of the chosen settings and the destination path, and SHALL write nothing unless the user confirms. Abandoning the wizard SHALL leave no partial instance behind.

#### Scenario: Declining at the summary

- **WHEN** a user reviews the summary and declines
- **THEN** no file or directory is created and the system reports that nothing was created

#### Scenario: Interrupting mid-wizard

- **WHEN** a user interrupts the wizard before reaching the summary
- **THEN** the system exits cleanly, reports that nothing was created, and leaves no partial instance

### Requirement: Setup reports what to do next

On success the wizard SHALL report where the instance was written and what command starts it, and SHALL surface any follow-up the user's answers made necessary.

#### Scenario: Reporting after a successful write

- **WHEN** the wizard finishes writing an instance
- **THEN** it prints the file path and the command that starts the instance
