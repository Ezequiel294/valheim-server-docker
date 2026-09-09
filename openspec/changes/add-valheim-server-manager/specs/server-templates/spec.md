## Purpose

Provides a single richly-commented Valheim server blueprint that documents the container's full configuration surface, and the means to scaffold an editable working copy of it as a named instance.

## ADDED Requirements

### Requirement: Annotated template documents the full configuration surface

The repository SHALL provide exactly one template blueprint that documents every configuration group the container image exposes: server identity and networking, access control, update and restart scheduling, backups, observability, event hooks, log filters, permissions, and Valheim's own gameplay arguments. Options not required for a working server SHALL be present but commented out, so the file reads as a reference without needing edits to run.

#### Scenario: Reader discovers an option without leaving the file

- **WHEN** a user opens the template looking for how to schedule backups
- **THEN** the file contains a commented backup section naming the relevant variables and their defaults, with enough explanation to set them without consulting upstream documentation

#### Scenario: Template runs unmodified except for identity

- **WHEN** a user uncomments nothing and only edits the server name, world name, and password
- **THEN** the resulting file is a valid, runnable server configuration

### Requirement: Template is not directly runnable and identifies itself as a blueprint

The template SHALL carry instructions marking it as a blueprint rather than a running configuration, and those instructions SHALL NOT appear in any instance scaffolded from it.

#### Scenario: Scaffolded instance does not describe itself as a template

- **WHEN** a user scaffolds an instance from the template
- **THEN** the generated file contains no text instructing the reader to scaffold an instance, and no reference to itself as a template

### Requirement: Scaffolding produces a named working copy

The system SHALL scaffold an instance from the template under a user-supplied name, substituting that name everywhere the template refers to the instance, and SHALL refuse to overwrite an instance that already exists.

#### Scenario: Scaffolding a new instance

- **WHEN** a user scaffolds an instance named `friends`
- **THEN** a compose file is created for `friends` with the container name, config path, and server name reflecting `friends`, and the original template is left unmodified

#### Scenario: Scaffolding over an existing instance

- **WHEN** a user scaffolds an instance whose name is already in use
- **THEN** the system refuses, reports that the instance already exists, and leaves the existing file untouched

### Requirement: Template pins the maintained image and explains version pinning

The template SHALL reference the actively maintained container image, and SHALL explain in comments how to pin a specific version tag instead of tracking the newest build.

#### Scenario: Generated instances reference the maintained image

- **WHEN** any instance is created, by scaffolding or by the wizard
- **THEN** its image reference is the maintained registry image, not the stale mirror that predates the Valheim 1.0 world format

#### Scenario: User wants a reproducible deployment

- **WHEN** a user reads the template's image section
- **THEN** it shows the syntax for pinning a version tag and names the tags available

### Requirement: Modding is documented but not automated

The template SHALL document the container's mod frameworks and their configuration bridge as commented-out sections, including that the two frameworks are mutually exclusive. The system SHALL NOT install, update, or otherwise manage mod plugins.

#### Scenario: Reader learns modding exists and how to enable it

- **WHEN** a user reads the template's modding section
- **THEN** it names both mod frameworks, states that at most one may be enabled, shows where plugin files must be placed, and explains the environment-variable-to-config-file bridge including its character escaping rules

#### Scenario: Tooling makes no attempt to manage plugins

- **WHEN** a user runs any command the manager provides
- **THEN** no plugin file is downloaded, installed, moved, or deleted
