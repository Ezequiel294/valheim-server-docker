## Purpose

Installs an existing Valheim world into an instance, handling both the Valheim 1.0 directory save format and the older single-file format, and guarding against the irreversible conversion that occurs when a 1.0 server first opens an older world.

## ADDED Requirements

### Requirement: Both world save formats are recognised

Valheim 1.0 stores a world as a directory of files, while older versions store it as a paired save and metadata file. The system SHALL accept either form, identify which it was given, and report that identification to the user.

#### Scenario: Importing a Valheim 1.0 world

- **WHEN** a user imports a path that is a 1.0 world directory
- **THEN** the system identifies it as a 1.0 world and installs it

#### Scenario: Importing a pre-1.0 world

- **WHEN** a user imports a path that is a pre-1.0 save and metadata file pair
- **THEN** the system identifies it as a pre-1.0 world and installs it

#### Scenario: Importing something that is not a world

- **WHEN** a user imports a path that matches neither format
- **THEN** the system refuses, explains what it expected, and installs nothing

### Requirement: One-way conversion is warned about before it can happen

A Valheim 1.0 server rewrites an older world into the new format on first open, after which older servers can no longer read it. When importing a pre-1.0 world the system SHALL warn that this conversion is irreversible and SHALL offer to retain an untouched copy of the original before installing.

#### Scenario: Importing a pre-1.0 world

- **WHEN** a user imports a pre-1.0 world
- **THEN** the system warns that a 1.0 server will convert it irreversibly and offers to keep a safety copy

#### Scenario: Accepting the safety copy

- **WHEN** a user accepts the offered safety copy
- **THEN** an untouched copy of the original world is retained and its location is reported

#### Scenario: Importing an already-converted world

- **WHEN** a user imports a world already in the 1.0 format
- **THEN** no conversion warning is given, because no conversion will occur

### Requirement: Import does not destroy existing worlds

The system SHALL NOT overwrite a world already installed in the target instance without the user's explicit agreement, and SHALL leave the source world unmodified in all cases.

#### Scenario: Importing over an existing world of the same name

- **WHEN** a user imports a world whose name matches one already installed in the target instance
- **THEN** the system reports the collision and does not overwrite unless the user explicitly confirms

#### Scenario: Source is left intact

- **WHEN** any import completes
- **THEN** the world at the source path is unchanged

### Requirement: The instance is pointed at the imported world

After a successful import the system SHALL ensure the target instance is configured to load the imported world, using the name the server expects for the detected format, and SHALL report the name it set.

#### Scenario: Instance loads the imported world on next start

- **WHEN** a user imports a world into an instance and then starts that instance
- **THEN** the server loads the imported world rather than creating a new one

#### Scenario: Reporting the configured world name

- **WHEN** an import completes
- **THEN** the system reports the world name it configured for the instance

### Requirement: Import requires an existing target instance

The system SHALL verify the target instance exists before importing, and SHALL NOT create one implicitly.

#### Scenario: Importing into a nonexistent instance

- **WHEN** a user imports into an instance name that has not been created
- **THEN** the system reports that no such instance exists, names the command that creates one, and installs nothing
