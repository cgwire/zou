=====================================================================================================================================
New release information (1.0.86) - Friday (today), September, 25th night around 8:00 PM (GMT)

Hello @everyone,

Tonight, we will proceed with the release of a new version of Zou. It will be shipped with the following changes:

New features
Picture previews are now built in the background. The upload answers
immediately with the preview file in the "processing" status, and the
preview turns "ready" once its variants are stored. Add `?no_job=true`
to the upload to keep the previous synchronous behaviour.

A variant requested while the preview is being built answers 202 to a
client that accepts JSON, and 404 to a browser, as before. Gazu 1.3.1
or later understands the 202 and retries on its own; an older Gazu keeps
seeing 404.

If your instance has a job queue enabled, its rq workers must run on the
API host, or share `TMP_DIR` with it: the picture job now receives a
local path, exactly like the movie job already did. Previously this only
affected movie uploads; it now affects every picture upload too.

A preview file left in the "processing" status by an older import or a
past failure is no longer served: it now answers the same 202/404 as a
genuinely processing preview. Use the "mark broken" action of the
preview list to fix one manually.

=====================================================================================================================================
New release information - Tuesday (today), March, 10th night around 8:00 PM (GMT)

Hello @everyone,

Tonight, we will proceed with the release of a new version of Zou (1.0.16). It will be shipped with the following changes:

Fixes
Security improvements for authentication, 2FA, and admin access control.
Fix person presence computed using the wrong user's data.
Fix sequence subscription notifications sent to all users instead of the target person.
Fix playlist notifications always sent regardless of settings.
Fix annotation updates not persisted due to shared mutable references.
Fix comment reply attachment deletion.
Fix the last comment per task, returning the first instead of the last.
Fix cookie-based token refresh not returning a response.
Fix preview sync swapping picture and file download methods.
Performance improvements on comment serialization and N+1 queries.
Add email translations for admin actions across all locales.
Significantly expanded test coverage across routes, models, services, and utilities.

=====================================================================================================================================
New release information (1.0.17) - Friday (today), March, 6th night around 8:00 PM (GMT)

Hello @everyone,

Tonight, we will proceed with the release of a new version of Kitsu. It will be shipped with the following changes:

Fixes
Fix page initialization when switching to the studio newsfeed.
Fix person filter for the studio newsfeed.
Fix real-time updates for the studio newsfeed.
Fix the condition for displaying 3D model animation buttons in the preview player.
Fix UI glitch with titles of grouped lists when scrolling horizontally.
Fix UI glitch on person's timesheets when scrolling.
Make the combobox status responsive.
Keep the search filter when refreshing the My Tasks page.
Keep the search filter when refreshing the Person page.
Refactor fullscreen mixin to use modern Fullscreen API and remove legacy vendor prefixes.
Improve Kitsu translations: add missing i18n keys, fix date translations, add translations to the Calendar page, ...
Update several translations.

=====================================================================================================================================
New release information (1.0.15) - Wednesday (today), February, 25th night around 8:00 PM (GMT)

Hello @everyone,

Tonight, we will proceed with the release of a new version of Kitsu. It will be shipped with the following changes:

New features
Enforce 2FA setup when required by organization configuration.
Add a flag for users who have enabled 2FA in the user management list.

Fixes
Automatically confirm file selections in import modals to minimize clicks.
Fix metadata filtering using the IN operator in the task list.
Hide the frames column in the shot list for 2D paper productions.
Clear selected tasks on department change.
Disable links to entity pages for client users.
Hide certain data for client users.
Simplify unregistering a FIDO key (2FA).
Fix the Disable 2FA button to include FIDO authentication on the People page.
Fix task selection logic when department filtering is enabled.
Improve API performance (load metadata, tasks batch, todo list...).
Fix deletions (delete output files linked to entities or projects).
Allow attachments larger than 2GB.
Add translations for emails.
Update some Kitsu translations.
Remove the Kitsu Summit badge.
Add a link to the Kitsu Developer Documentation.

=====================================================================================================================================
New release information (1.0.11) - Tuesday (today), February, 3rd night around 8:00 PM (GMT)

Hello @everyone,

Tonight, we will proceed with the release of a new version of Kitsu. It will be shipped with the following changes:

New features
Allow adding frontend plugins.
Allow filtering of client notifications by department in playlists.
Support all entities on the production schedule.
Implement cascading deletion of Schedule Items when a Task Type is deleted.
Allow to enforce 2FA on the frontend.
Allow not to save the source file.
Add a flexible data field to preview file models.

Fixes
Fix annotation display on the Edit page.
Fix the set or unset day off in the timesheets tab of the My Tasks page.
Fix an invalid month issue when changing the year with Day level enabled on the Timesheets page.
Harmonize the department and studio comboboxes.
Fit PDF files to the preview container.
Fix metadata filtering for checklist type.
Fix task loading on the task type page in the Episodes section.
Fix CSV export of quotas.
Refactor the sound button to restore volume when unmuting.
Fix file parsing with multiline fields when importing CSV files.
Fix end date computation of tasks (first review date).

=====================================================================================================================================
New release information (1.0.6) - Wednesday (today), December, 17th night around 8:00 PM (GMT)

Hello @everyone,

Tonight, we will proceed with the release of a new version of Kitsu. It will be shipped with the following changes:

New features
Switch to server-side pagination for the log list of the studio logs.
Add server-side pagination for the preview files list of the studio logs.

Fixes
Reset pan zoom on reset canvas position on a playlist.
Fix the unwanted PDF loading in the background.
Fix the task start date and due date updates on the editable task lists.
Fix the pan zoom toggle action on the playlists.

Next: frontend support for plugins.


=====================================================================================================================================
New release information (1.0.3) - Tuesday (today), December, 9th night around 8:00 PM (GMT)

Hello @everyone,

Tonight, we will proceed with the release of a new version of Kitsu. It will be shipped with the following changes:

New features
Allow a supervisor to modify only their playlists.
Improve the Add Thumbnails form by listing invalid files.
Add pagination to the studio logs.

Fixes
Fix the layout of the shot page info.
Fix version selection in temp playlist modal.
Fix available actions when a concept is selected.
Add missing translations.

Next: frontend support for plugins.
