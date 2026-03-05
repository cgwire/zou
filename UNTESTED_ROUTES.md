# Untested Blueprint Routes

## Chats — 100% covered
## Events — 100% covered
## Search — 100% covered

## User — DONE
| Route | Method | Status |
|---|---|---|
| `/data/user/assets/<id>/task-types` | GET | ✅ Done |
| `/actions/user/chats/<id>/join` | DELETE | ✅ Done |

## Shots — DONE
| Route | Method | Status |
|---|---|---|
| `/data/shots/<id>/preview-files` | GET | ✅ Done |
| `/data/shots/<id>/versions` | GET | ✅ Done |
| `/data/episodes/<id>/shot-tasks` | GET | ✅ Done |
| `/data/episodes/<id>/asset-tasks` | GET | ✅ Done |
| `/data/sequences/<id>/shot-tasks` | GET | ✅ Done |
| `/data/projects/<id>/quotas/<task_type_id>` | GET | ✅ Done |
| `/data/projects/<id>/quotas/persons/<person_id>` | GET | ✅ Done |
| `/actions/projects/<id>/task-types/<id>/set-shot-nb-frames` | POST | ✅ Done |

## Tasks — DONE
| Route | Method | Status |
|---|---|---|
| `/data/tasks/open-tasks/stats` | GET | ✅ Done |
| `/data/projects/<id>/subscriptions` | GET | ✅ Done |
| `/data/persons/task-dates` | GET | ✅ Done |
| `/actions/projects/<id>/task-types/<id>/delete-tasks` | DELETE | ✅ Done |
| `/actions/projects/<id>/delete-tasks` | POST | ✅ Done |
| `/actions/persons/<id>/assign` | PUT | ✅ Done |
| `/actions/tasks/clear-assignation` | PUT | ✅ Done |
| `/actions/projects/<id>/task-types/<id>/edits/create-tasks` | POST | ✅ Done |
| `/actions/projects/<id>/task-types/<id>/concepts/create-tasks` | POST | ✅ Done |
| `/actions/tasks/<id>/set-main-preview` | PUT | ✅ Done |
| `/actions/tasks/<id>/comments/<id>/preview-files/<id>` | DELETE | ✅ Done |

## Files — DONE (except file upload/download)
| Route | Method | Status |
|---|---|---|
| `/data/files/<id>` | GET | ✅ Done |
| `/data/tasks/<id>/working-files` | GET | ✅ Done |
| `/data/asset-instances/<id>/entities/<id>/output-types` | GET | ✅ Done |
| `/data/asset-instances/<id>/entities/<id>/output-types/<id>/output-files` | GET | Skipped (complex FK setup) |
| `/data/entities/guess_from_path` | POST | ✅ Done |
| `/data/working-files/<id>/file` | GET, POST | Skipped (binary file I/O) |
| `/actions/projects/<id>/set-file-tree` | POST | ✅ Done |

## News — DONE
| Route | Method | Status |
|---|---|---|
| `/data/projects/news` | GET | ✅ Done |

## Edits — DONE
| Route | Method | Status |
|---|---|---|
| `/data/edits` | GET | ✅ Done |
| `/data/edits/<id>/preview-files` | GET | ✅ Done |
| `/data/edits/<id>/versions` | GET | ✅ Done |
| `/data/episodes/<id>/edits` | GET | ✅ Done |
| `/data/episodes/<id>/edit-tasks` | GET | ✅ Done |

## Assets — DONE
| Route | Method | Status |
|---|---|---|
| `/data/assets/<id>/assets` | GET | ✅ Done |
| `/data/assets/<id>/cast-in` | GET | ✅ Done |
| `/data/assets/<id>/casting` | GET, PUT | ✅ Done |
| `/data/assets/<id>/shot-asset-instances` | GET | ✅ Done |
| `/data/assets/<id>/scene-asset-instances` | GET | ✅ Done |
| `/data/assets/<id>/asset-asset-instances` | GET, POST | ✅ Done |
| `/actions/assets/share` | POST | ✅ Done |
| `/actions/projects/<id>/assets/share` | POST | ✅ Done |
| `/actions/projects/<id>/asset-types/<id>/assets/share` | POST | ✅ Done |
| `/data/projects/<id>/assets/shared-used` | GET | ✅ Done |
| `/data/projects/<id>/episodes/<id>/assets/shared-used` | GET | ✅ Done |

## Projects — DONE
| Route | Method | Status |
|---|---|---|
| `/data/projects/<id>/settings/asset-types` | GET, POST | ✅ Done |
| `/data/projects/<id>/settings/asset-types/<id>` | DELETE | ✅ Done |
| `/data/projects/<id>/settings/task-types` | GET, POST | ✅ Done |
| `/data/projects/<id>/settings/task-types/<id>` | DELETE | ✅ Done |
| `/data/projects/<id>/settings/task-status` | GET, POST | ✅ Done |
| `/data/projects/<id>/settings/task-status/<id>` | DELETE | ✅ Done |
| `/data/projects/<id>/settings/status-automations` | GET, POST | ✅ Done |
| `/data/projects/<id>/settings/status-automations/<id>` | DELETE | ✅ Done |
| `/data/projects/<id>/settings/preview-background-files` | GET, POST | ✅ Done |
| `/data/projects/<id>/settings/preview-background-files/<id>` | DELETE | ✅ Done |
| `/data/projects/<id>/time-spents` | GET | ✅ Done |
| `/data/projects/<id>/milestones` | GET | ✅ Done |
| `/data/projects/<id>/budgets` | GET, POST | ✅ Done |
| `/data/projects/<id>/budgets/<id>` | GET, PUT, DELETE | ✅ Done |
| `/data/projects/<id>/budgets/<id>/entries` | GET, POST | ✅ Done |
| `/data/projects/<id>/budgets/<id>/entries/<id>` | GET, PUT, DELETE | ✅ Done |
| `/data/projects/<id>/budgets/time-spents` | GET | ✅ Done |
| `/data/production-schedule-versions/<id>/task-links` | GET, POST | ✅ Done |
| `/actions/production-schedule-versions/<id>/set-task-links-from-production` | POST | Skipped (complex schedule setup) |
| `/actions/production-schedule-versions/<id>/set-task-links-from-production-schedule-version` | POST | Skipped (complex schedule setup) |
| `/actions/production-schedule-versions/<id>/apply-to-production` | POST | Skipped (complex schedule setup) |
| `/data/projects/<id>/task-types/<id>/time-spents` | GET | ✅ Done |
| `/data/projects/<id>/day-offs` | GET | ✅ Done |

## Auth — Skipped (requires real bcrypt, TOTP, FIDO hardware, SAML IdP)
| Route | Method | Status |
|---|---|---|
| `/auth/totp` | GET, POST, DELETE | Skipped |
| `/auth/email-otp` | GET, PUT, POST, DELETE | Skipped |
| `/auth/recovery-codes` | GET, PUT, POST, DELETE | Skipped |
| `/auth/fido` | GET, PUT, POST, DELETE | Skipped |
| `/auth/saml/sso` | POST | Skipped |
| `/auth/saml/login` | GET | Skipped |

## Breakdown — DONE
| Route | Method | Status |
|---|---|---|
| `/data/projects/<id>/asset-types/<id>/casting` | GET | ✅ Done |
| `/data/projects/<id>/episodes/casting` | GET | ✅ Done |
| `/data/projects/<id>/sequences/<id>/casting` | GET | ✅ Done |
| `/data/projects/<id>/episodes/<id>/sequences/all/casting` | GET | ✅ Done |
| `/data/projects/<id>/sequences/all/casting` | GET | ✅ Done |
| `/data/projects/<id>/entity-links/<id>` | DELETE | ✅ Done |
| `/data/scenes/<id>/asset-instances` | GET, POST | ✅ Done |
| `/data/scenes/<id>/camera-instances` | GET | ✅ Done |
| `/data/shots/<id>/asset-instances` | GET, POST | ✅ Done |
| `/data/shots/<id>/asset-instances/<id>` | DELETE | ✅ Done |

## Persons — DONE (except invite)
| Route | Method | Status |
|---|---|---|
| `/data/persons/<id>/time-spents` | GET | ✅ Done |
| `/data/persons/<id>/day-offs/<date>` | GET | ✅ Done |
| `/data/persons/<id>/time-spents/year/<year>` | GET | ✅ Done |
| `/data/persons/<id>/time-spents/month/<year>/<month>` | GET | ✅ Done |
| `/data/persons/<id>/time-spents/week/<year>/<week>` | GET | ✅ Done |
| `/data/persons/<id>/time-spents/day/<year>/<month>/<day>` | GET | ✅ Done |
| `/data/persons/<id>/quota-shots/month/<year>/<month>` | GET | ✅ Done |
| `/data/persons/<id>/quota-shots/week/<year>/<week>` | GET | ✅ Done |
| `/data/persons/<id>/quota-shots/day/<year>/<month>/<day>` | GET | ✅ Done |
| `/data/persons/time-spents/year-table/` | GET | ✅ Done |
| `/data/persons/time-spents/month-table/<year>` | GET | ✅ Done |
| `/data/persons/time-spents/week-table/<year>` | GET | ✅ Done |
| `/data/persons/time-spents/day-table/<year>/<month>` | GET | ✅ Done |
| `/data/persons/day-offs/<year>/<month>` | GET | ✅ Done |
| `/data/persons/<id>/day-offs/week/<year>/<week>` | GET | ✅ Done |
| `/data/persons/<id>/day-offs/month/<year>/<month>` | GET | ✅ Done |
| `/data/persons/<id>/day-offs/year/<year>` | GET | ✅ Done |
| `/data/persons/<id>/day-offs` | GET | ✅ Done |
| `/actions/persons/<id>/invite` | POST | Skipped (sends email) |
| `/actions/persons/<id>/change-password` | POST | ✅ Done |
| `/actions/persons/<id>/disable-two-factor-authentication` | DELETE | ✅ Done |
| `/actions/persons/<id>/clear-avatar` | DELETE | ✅ Done |

## Concepts — DONE
| Route | Method | Status |
|---|---|---|
| `/data/concepts` | GET | ✅ Done |
| `/data/concepts/with-tasks` | GET | ✅ Done |
| `/data/concepts/<id>` | GET, DELETE | ✅ Done |
| `/data/concepts/<id>/task-types` | GET | ✅ Done |
| `/data/concepts/<id>/tasks` | GET | ✅ Done |
| `/data/concepts/<id>/preview-files` | GET | ✅ Done |
| `/data/projects/<id>/concepts` | GET, POST | ✅ Done |

## Departments — DONE
| Route | Method | Status |
|---|---|---|
| `/data/departments/software-licenses` | GET | ✅ Done |
| `/data/departments/<id>/software-licenses` | POST | ✅ Done |
| `/data/departments/<id>/software-licenses/<id>` | GET, DELETE | ✅ Done |
| `/data/departments/hardware-items` | GET | ✅ Done |
| `/data/departments/<id>/hardware-items` | POST | ✅ Done |
| `/data/departments/<id>/hardware-items/<id>` | GET, DELETE | ✅ Done |

## Entities — DONE
| Route | Method | Status |
|---|---|---|
| `/data/entities/<id>/news` | GET | ✅ Done |
| `/data/entities/<id>/preview-files` | GET | ✅ Done |
| `/data/entities/<id>/time-spents` | GET | ✅ Done |
| `/data/entities/<id>/entities-linked/with-tasks` | GET | ✅ Done |

## Comments — DONE (except file upload/download)
| Route | Method | Status |
|---|---|---|
| `/data/tasks/<id>/comments/<id>/ack` | POST | ✅ Done |
| `/data/tasks/<id>/comments/<id>/reply` | POST | ✅ Done |
| `/data/tasks/<id>/comments/<id>/attachments/<id>` | DELETE | Skipped (needs file upload) |
| `/data/tasks/<id>/comments/<id>/reply/<id>` | DELETE | ✅ Done |
| `/data/attachment-files/<id>/file/<name>` | GET | Skipped (binary file I/O) |
| `/actions/tasks/<id>/comments/<id>/add-attachment` | POST | Skipped (needs file upload) |
| `/data/projects/<id>/attachment-files` | GET | ✅ Done |
| `/data/tasks/<id>/attachment-files` | GET | ✅ Done |
| `/actions/tasks/<id>/comment` | POST | ✅ Done |
| `/actions/projects/<id>/tasks/comment-many` | POST | ✅ Done |

## Previews — Skipped (requires file storage, image processing, ffmpeg)
| Route | Method | Status |
|---|---|---|
| `/pictures/preview-files/<id>` | POST | Skipped |
| `/actions/tasks/<id>/batch-comment` | POST | Skipped |
| `/actions/tasks/batch-comment` | POST | Skipped |
| `/movies/originals/preview-files/<id>.mp4` | GET | Skipped |
| `/movies/originals/preview-files/<id>/download` | GET | Skipped |
| `/movies/low/preview-files/<id>.mp4` | GET | Skipped |
| `/pictures/thumbnails/preview-files/<id>.png` | GET | Skipped |
| `/pictures/thumbnails/attachment-files/<id>.png` | GET | Skipped |
| `/pictures/thumbnails-square/preview-files/<id>.png` | GET | Skipped |
| `/pictures/originals/preview-files/<id>.png` | GET | Skipped |
| `/pictures/originals/preview-files/<id>.<extension>` | GET | Skipped |
| `/pictures/originals/preview-files/<id>/download` | GET | Skipped |
| `/pictures/previews/preview-files/<id>.png` | GET | Skipped |
| `/movies/tiles/preview-files/<id>.png` | GET | Skipped |
| `/pictures/thumbnails/organisations/<id>.png` | GET | Skipped |
| `/pictures/thumbnails/organisations/<id>` | POST | Skipped |
| `/pictures/thumbnails/persons/<id>.png` | GET | Skipped |
| `/pictures/thumbnails/persons/<id>` | POST | Skipped |
| `/pictures/thumbnails/projects/<id>.png` | GET | Skipped |
| `/pictures/thumbnails/projects/<id>` | POST | Skipped |
| `/pictures/preview-background-files/<id>` | POST | Skipped |
| `/pictures/thumbnails/preview-background-files/<id>.png` | GET | Skipped |
| `/pictures/preview-background-files/<id>.<extension>` | GET | Skipped |
| `/actions/preview-files/<id>/set-main-preview` | PUT | Skipped |
| `/actions/preview-files/<id>/update-annotations` | PUT | Skipped |
| `/actions/preview-files/<id>/update-position` | PUT | Skipped |
| `/actions/preview-files/<id>/extract-frame` | GET | Skipped |
| `/actions/preview-files/<id>/extract-tile` | GET | Skipped |

## Playlists — DONE (except build/download)
| Route | Method | Status |
|---|---|---|
| `/data/projects/<id>/playlists/all` | GET | ✅ Done |
| `/data/projects/<id>/episodes/<id>/playlists` | GET | ✅ Done |
| `/data/projects/<id>/playlists/<id>` | GET | ✅ Done |
| `/data/playlists/entities/<id>/preview-files` | GET | ✅ Done |
| `/data/playlists/<id>/jobs/<id>` | GET, DELETE | Skipped (needs build job) |
| `/data/projects/<id>/build-jobs` | GET | ✅ Done |
| `/data/playlists/<id>/build/mp4` | GET | Skipped (needs ffmpeg) |
| `/data/playlists/<id>/jobs/<id>/build/mp4` | GET | Skipped (needs build job + file) |
| `/data/projects/<id>/playlists/temp` | POST | ✅ Done |
| `/actions/playlists/<id>/add-entity` | POST | ✅ Done |
| `/data/playlists/<id>/notify-clients` | POST | Skipped (sends notifications) |
