# Models

## Base classes

All models inherit from `db.Model`, `BaseMixin`, and `SerializerMixin`.

**BaseMixin** (`zou/app/models/base.py`):
- `id`: UUID primary key (auto-generated)
- `created_at`, `updated_at`: UTC timestamps (auto-maintained)
- `create(**data)`, `get(id)`, `get_by(**filters)`, `get_all_by(**filters)`
- `update(data)`, `save()`, `delete()`
- `serialize(relations=False)`, `present()` (custom serialization override)

**SerializerMixin** (`zou/app/models/serializer.py`):
- Converts model instances to dicts
- Optional relation inclusion (`relations=True` loads FK targets)
- Handles UUIDs, datetimes, JSONB, and choice fields

## Core models and relationships

```
Person ──────────────┐
  ├─ studio_id → Studio            (optional)
  ├─ departments ←→ Department     (many-to-many via DepartmentLink)
  ├─ tasks ←→ Task                 (many-to-many via TaskPersonLink)
  └─ notifications → Notification

Project ─────────────┐
  ├─ project_status_id → ProjectStatus
  ├─ persons ←→ Person             (many-to-many via ProjectPersonLink)
  ├─ task_types ←→ TaskType        (many-to-many)
  ├─ task_statuses ←→ TaskStatus   (many-to-many)
  └─ asset_types ←→ EntityType     (many-to-many)

Entity ──────────────┐  (assets, shots, sequences, episodes, scenes, edits, concepts)
  ├─ project_id → Project
  ├─ entity_type_id → EntityType
  ├─ parent_id → Entity            (self-referential hierarchy)
  └─ entities_out ←→ Entity        (many-to-many via EntityLink)

Task ────────────────┐
  ├─ project_id → Project
  ├─ entity_id → Entity
  ├─ task_type_id → TaskType
  ├─ task_status_id → TaskStatus
  ├─ assigner_id → Person
  └─ assignees ←→ Person           (many-to-many)

Comment ─────────────┐
  ├─ task_id → Task
  ├─ person_id → Person
  ├─ task_status_id → TaskStatus
  ├─ attachment_files → AttachmentFile (one-to-many)
  ├─ mentions ←→ Person            (many-to-many)
  └─ replies (self-referential via reply_to)

PreviewFile ─────────┐
  ├─ task_id → Task
  ├─ person_id → Person
  └─ linked to comments via CommentPreviewLink

OutputFile / WorkingFile
  ├─ entity_id → Entity
  ├─ task_id → Task
  └─ person_id → Person

TimeSpent
  ├─ task_id → Task
  ├─ person_id → Person
  └─ date (unique per person+task+date)
```

## Entity type system

The `Entity` model is polymorphic. The `entity_type_id` determines the kind:

| Kind | EntityType name | Typical parent |
|------|----------------|----------------|
| Asset | Props, Characters, Environment, ... | None |
| Shot | Shot | Sequence |
| Sequence | Sequence | Episode |
| Episode | Episode | None |
| Scene | Scene | Sequence |
| Edit | Edit | Episode or None |
| Concept | Concept | None |

Assets, shots, etc. are all rows in the `entity` table distinguished by `entity_type_id`. Helper services (`shots_service`, `assets_service`) provide typed access.

## Naming conventions

- Model class: `PascalCase` (e.g., `TaskStatus`)
- Table name: auto-derived `snake_case` (e.g., `task_status`)
- Route: kebab-case (e.g., `data/task-statuses`)
- FK column: `<related_table>_id` (e.g., `project_id`)
- Many-to-many table: `<table1>_<table2>_link` (e.g., `task_person_link`)
