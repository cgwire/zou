# File trees descriptors

To generate file path, Zou relies on JSON-based configuration files.

Each file contains several sections, each one corresponds to a context (working
file, output file, preview, etc.)


## Contexts

Working and output are expected in all files.

```json
{
  "working": {...},
  "output": {...}
}
```


## Context details

Then each section is composed of 4 fields:

* Mounting point
* Root folder
* Folder path template
* File path template

```json
"working": {
  "mountpoint": "/working_files",
  "root": "productions",
  "folder_path": {...},
  "file_name": {...}
}
```

## Folder path

Folder path section requires three fields:

* Path for tasks related to assets.
* Path for tasks related to shots.
* Path for tasks related to sequences.
* Style (uppercase or lowercase)

```json
"folder_path": {
  "shot": "<Project>/shots/<Sequence>/<Shot>/<TaskType>",
  "asset": "<Project>/assets/<AssetType>/<Asset>/<TaskType>",
  "sequence": "<Project>/sequences/<Sequence>>/<TaskType>",
  "style": "lowercase"
}
```

Tags (words between <>) are replaced by the name of the object attached to the
task. 


## File name

File name templates are written the same way than folder templates.

```json
"file_name": {
    "shot": "<Project>_<Sequence>_<Shot>_<TaskType>",
    "asset": "<Project>_<AssetType>_<Asset>_<TaskType>",
    "sequence": "<Project>_<Sequence>_<TaskType>",
    "style": "lowercase"
}
```
