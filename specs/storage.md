# File Storage

## Architecture

File storage is abstracted via `zou/app/stores/file_store.py`, backed by Flask-FS. Three storage buckets exist:

| Bucket | Contents |
|--------|----------|
| `pictures` | Thumbnails, avatars, preview images |
| `movies` | Video previews |
| `files` | Work files, output files, attachments |

## Backends

Configured via `FS_BACKEND` env var:

| Backend | Value | Description |
|---------|-------|-------------|
| Local filesystem | `local` | Default. Files stored under `FS_ROOT` |
| Amazon S3 | `s3` | S3 or S3-compatible (MinIO) |
| OpenStack Swift | `swift` | OVH, Rackspace object storage |

## Path mapping

Local storage uses a custom path structure to avoid directory listing performance issues:

```
Input:  "prefix-abcdef12-3456-7890-abcd-ef1234567890.png"
Output: /root/prefix/abc/def/abcdef12-3456-7890-abcd-ef1234567890.png
```

Files are grouped by prefix, then split into subdirectories using the first 3 and next 3 characters of the filename.

## API

```python
from zou.app.stores import file_store

# Write
file_store.add_picture("thumbnails", file_id, local_path)
file_store.add_movie("previews", file_id, local_path)
file_store.add_file("attachments", file_id, local_path)

# Read
data = file_store.read_picture("thumbnails", file_id)   # bytes
stream = file_store.open_picture("thumbnails", file_id)  # generator

# Check / delete
file_store.exists_picture("thumbnails", file_id)
file_store.remove_picture("thumbnails", file_id)

# Copy between prefixes
file_store.copy_picture("thumbnails", old_id, "backup", new_id)
```

## Configuration

```bash
FS_BACKEND=local
FS_ROOT=/opt/zou/previews

# S3
FS_S3_REGION=us-east-1
FS_S3_ENDPOINT=https://s3.amazonaws.com
FS_S3_ACCESS_KEY=...
FS_S3_SECRET_KEY=...

# Swift
FS_SWIFT_AUTHURL=https://identity.api.rackspacecloud.com/v2.0
FS_SWIFT_USER=...
FS_SWIFT_KEY=...
```
