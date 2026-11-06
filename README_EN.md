[简体中文](README.md) | [English](README_EN.md)

# astrbot-plugin-jmdownloader-docker

**Linux cloud server / dual-Docker-container compatibility fork of the AstrBot jmdownloader plugin**

This repository is based on [CLRedfield's `astrbot-plugin-jmdownloader`](https://github.com/CLRedfield/astrbot-plugin-jmdownloader). It focuses on file-path accessibility and filesystem-permission issues that can occur when AstrBot and NapCat run in separate Docker containers on a Linux server.

> **Project notice**
>
> This is an unofficial, independently maintained compatibility fork for Linux cloud deployments, not an official release of the upstream project.
>
> The original functionality and most of the source code belong to the upstream author. This fork primarily documents changes related to Docker file sharing and Linux filesystem permissions.

## 1. Background

In a typical local Windows setup, AstrBot and NapCat can often access files through the same host filesystem.

On a Linux cloud server, however, AstrBot and NapCat may run in separate Docker containers. Each container has its own filesystem unless directories are explicitly shared.

This can lead to issues such as:

- AstrBot successfully creates a file, but NapCat cannot read it.
- The OneBot file API returns `retcode=1200`.
- Logs report `Failed to recognize URL` (`识别URL失败`).
- `EACCES: permission denied` persists even after a shared Docker directory has been configured.

This fork addresses compatibility issues associated with that deployment setup.

## 2. Main Changes

### 2.1 Shared-directory compatibility for Docker

The original implementation uses Python's default temporary directory:

```python
TEMP_ROOT = Path(tempfile.gettempdir()) / "astrbot_jmdownloader"
```

Inside a Linux container, this generally resolves to a location under `/tmp`.

Because two separate containers do not automatically share their `/tmp` directories, a file path that works for AstrBot may be inaccessible to NapCat.

The modified temporary-file root is:

```text
/AstrBot/data/pdf_uploads/
```

This path must be accessible from both the AstrBot and NapCat containers.

### 2.2 Linux filesystem-permission compatibility

Python's `tempfile.mkdtemp()` normally creates temporary directories with `0700` permissions.

If AstrBot and NapCat run under different Linux user identities, NapCat may be unable to read files even when the directory is mounted into both containers.

This fork includes compatibility changes to temporary-directory access permissions.

**Security note:** Do not use `chmod -R 777` on the entire AstrBot data directory. Grant only the permissions necessary for the relevant files and directories.

### 2.3 Temporary File Management

This modified version retains the original project’s mechanisms for task isolation and temporary file management, including:

- Creating a dedicated temporary directory for each task.
- Automatically generating the necessary folders.
- Scheduling an asynchronous cleanup after a task concludes, with a delay of approximately 10 minutes before the temporary directory is deleted.
- Maintaining a cleanup mechanism for expired tasks, which removes eligible old directories during plugin initialization or when a new task begins.

**Note:** The delayed cleanup task relies on the AstrBot process remaining active. If the process restarts before the cleanup is executed, the asynchronous task will be cancelled, and any remaining temporary files will instead be handled by the subsequent cleanup process for expired tasks.

## 3. Intended Environment

This fork primarily targets the following setup:

| Component | Environment |
|---|---|
| Operating system | Linux / Ubuntu |
| Container runtime | Docker |
| AstrBot | Separate Docker container |
| NapCat | Separate Docker container |
| Communication | OneBot v11 / WebSocket |
| Shared storage | Docker bind mount |

**Tested setup:** Ubuntu cloud server, AstrBot v4.29.4, with AstrBot and NapCat running in separate Docker containers.

Other deployment configurations have not been thoroughly tested.

## 4. Docker Shared-directory Overview

In a dual-container deployment, both containers need access to the same underlying host directory.

Example layout:

```text
Host shared directory
          │
    ┌─────┴─────┐
    │           │
 AstrBot      NapCat
    │           │
/AstrBot/data /AstrBot/data
```

Using the same mount path inside both containers can simplify cross-container file access.

Before deploying, verify that:

- The shared directory exists on the host.
- The directory is mounted into both containers.
- File ownership and permissions allow the required access.
- Files are not deleted before the receiving process has read them.

## 5. Common Errors

### `retcode=1200`: Failed to recognize URL

Possible causes:

- A file is stored in a directory visible to only one container.
- The receiving container cannot access the supplied path.
- The file API cannot interpret the supplied path format.

### `EACCES: permission denied`

Possible causes:

- Insufficient permissions on a temporary directory.
- Different user or group IDs (UID/GID) between containers.
- Missing directory traversal permissions on a parent directory.
- Insufficient read permissions on the target file.

### File not found

Possible causes:

- Temporary files were already removed by cleanup logic.
- Docker mount paths do not match.
- File generation failed or the file was saved elsewhere.

## 6. Security and Privacy

Before making a repository public, check that it does not contain:

- QQ login credentials
- Cookies or session data
- API keys or access tokens
- SSH private keys
- Download caches or personal files
- Logs containing sensitive information

Avoid committing secrets even to private repositories.

## 7. Credits and Upstream Project

This fork is based on:

**Upstream project:** [CLRedfield/astrbot-plugin-jmdownloader](https://github.com/CLRedfield/astrbot-plugin-jmdownloader)

Thanks to the original author for the core implementation. This fork focuses on file paths, shared directories, and access permissions in Linux Docker deployments.

This is an unofficial fork and is not affiliated with the upstream maintainer.

## 8. Disclaimer

This repository is intended for research and technical discussion of software deployment compatibility.

Users are responsible for complying with applicable laws, platform terms, and copyright requirements. This repository does not host or provide third-party content.

## 9. License

This fork is distributed under the upstream project's [MIT License](LICENSE), with the original copyright notice preserved. The changes made by this fork are described in this README.
