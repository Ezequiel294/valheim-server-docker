## Purpose

Provides on-demand operations against a running instance — forcing a backup, restarting the game process without recreating the container, and reporting run state — so routine administration does not require remembering container-internal commands.

## ADDED Requirements

### Requirement: Backups can be taken on demand

The system SHALL let a user trigger a world backup immediately rather than waiting for the scheduled one, and SHALL report where the backup was written.

#### Scenario: Forcing a backup before a risky change

- **WHEN** a user requests a backup of a running instance
- **THEN** the container's backup routine runs immediately and the system reports the backup directory

#### Scenario: Backup requested for a stopped instance

- **WHEN** a user requests a backup of an instance that is not running
- **THEN** the system reports that the instance is not running and does not claim a backup was taken

### Requirement: The game process can be restarted without recreating the container

The system SHALL let a user restart the game server process inside a running container, leaving the container itself in place. This SHALL be distinct from stopping and starting the instance, which recreates the container and re-runs the update check.

#### Scenario: Applying a configuration change that only needs a server restart

- **WHEN** a user restarts a running instance's server process
- **THEN** the game server stops and starts again within the same container, and the container is not recreated

#### Scenario: Restart requested for a stopped instance

- **WHEN** a user restarts an instance that is not running
- **THEN** the system reports that the instance is not running and suggests starting it instead

### Requirement: Run state is reportable

The system SHALL report whether an instance's server process is running. Where the instance is configured such that richer information is available, the system SHALL additionally report live details such as connected player count and server version.

#### Scenario: Status of a running instance

- **WHEN** a user requests status for a running instance
- **THEN** the system reports that the server process is running

#### Scenario: Status when live details are unavailable

- **WHEN** a user requests status for an instance whose configuration does not expose live query data
- **THEN** the system reports process state and explains that richer details require the relevant settings, rather than reporting an error or fabricating values

#### Scenario: Status of a stopped instance

- **WHEN** a user requests status for an instance that is not running
- **THEN** the system reports that it is not running

### Requirement: Operations do not expose container internals

Operations SHALL be expressed in terms of the instance and the outcome, not in terms of the container's internal process supervisor. The system SHALL NOT provide a raw passthrough to that supervisor.

#### Scenario: Command surface stays at the instance level

- **WHEN** a user lists the available commands
- **THEN** every operation names what it does to the server, and no command forwards arbitrary arguments to the container's process supervisor
