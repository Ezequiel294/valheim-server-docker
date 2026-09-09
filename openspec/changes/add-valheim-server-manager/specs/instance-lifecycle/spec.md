## Purpose

Covers discovering, starting, stopping, and observing named Valheim server instances on a single host, including the volume layout that lets many instances share one server download and the shutdown handling that protects world saves.

## ADDED Requirements

### Requirement: Instances are discoverable with their run state

The system SHALL list the available template and every scaffolded instance, reporting for each instance whether its container is currently running.

#### Scenario: Listing with a mix of states

- **WHEN** a user lists instances while one of three is running
- **THEN** all three are listed, the running one is marked running, and the other two are marked stopped

#### Scenario: Listing before any instance exists

- **WHEN** a user lists instances in a fresh checkout
- **THEN** the system reports that none exist and names the command that creates one

#### Scenario: Docker unavailable

- **WHEN** a user lists instances while Docker is not running
- **THEN** the system still lists the known instances rather than failing, treating run state as unknown or stopped

### Requirement: Only one server runs at a time

Because all instances bind the same host UDP ports and share one server directory, the system SHALL ensure at most one instance runs at a time. Starting an instance SHALL first stop any other running instance.

#### Scenario: Starting while another instance runs

- **WHEN** a user starts instance `hardcore` while `friends` is running
- **THEN** the system reports that it is stopping `friends` first, stops it, and then starts `hardcore`

#### Scenario: Starting the already-running instance

- **WHEN** a user starts an instance that is already running
- **THEN** the system does not stop it as a precondition of starting it

### Requirement: Instance state is split between shared and per-instance storage

The system SHALL store each instance's world saves, backups, and access-control lists in a per-instance location, and SHALL store the downloaded game server in a single location shared by all instances so it is fetched once rather than per instance.

#### Scenario: Second instance reuses the existing download

- **WHEN** a user creates and starts a second instance after a first has already downloaded the server
- **THEN** the second instance uses the existing download rather than fetching it again

#### Scenario: Instance worlds stay isolated

- **WHEN** two instances exist
- **THEN** neither can read or overwrite the other's world saves, backups, or access-control lists

#### Scenario: Instance name would collide with shared storage

- **WHEN** a user attempts to create an instance whose name would collide with the shared server directory
- **THEN** the system refuses the name and explains why

### Requirement: Stopping preserves the world

Valheim writes the world to disk only on a periodic timer and at shutdown, so an abrupt stop discards recent play. Every generated instance SHALL grant the container a shutdown window long enough for the server to complete its final save, and stopping an instance SHALL respect that window rather than killing the container immediately.

#### Scenario: Generated instance declares a shutdown window

- **WHEN** any instance is created, by scaffolding or by the wizard
- **THEN** its configuration grants a shutdown grace period of at least two minutes

#### Scenario: Stopping a running server

- **WHEN** a user stops a running instance
- **THEN** the server is signalled to shut down and given its grace period to save before the container is removed

### Requirement: Server output is observable

The system SHALL let a user follow a running instance's log output, and SHALL return cleanly when the user interrupts following.

#### Scenario: Following logs

- **WHEN** a user follows the logs of a running instance
- **THEN** server output is streamed until interrupted

#### Scenario: Interrupting log following

- **WHEN** a user interrupts log following
- **THEN** the system exits without an error traceback and leaves the server running

### Requirement: Commands reject unknown instances

Every command that operates on a named instance SHALL verify the instance exists before acting, and SHALL report how to create one when it does not.

#### Scenario: Operating on a nonexistent instance

- **WHEN** a user runs any instance command with a name that has not been created
- **THEN** the system reports that no such instance exists and names the command that creates one
