# API

The Zou API is REST-based. If you are looking for a Python client, see [Gazu](https://github.com/cgwire/gazu).

## Authentication

Before you can use any of the endpoints outline below, you will have to get a JWT to authorize your requests.

You can get a authorization token using a (form-encoded) POST request to `/auth/login`. With
`curl` this would look something like `curl -X POST <server_address>/auth/login -d "email=<youremail>&password=<yourpassword>`.

The response is a JSON object, specifically you'll need to provide the `access_token` for your future requests. 
 
Here is a complete authentication process as an example (again using `curl`):

    $ curl -X POST <server_address>/api/auth/login -d "email=<youremail>&password=<yourpassword>
    {"login": true", "access_token": "eyJ0e...", ...}
    
    $ jwt=eyJ0e...  # Store the access token for easier use
    
    $ curl -H "Authorization: Bearer $jwt" <server_address>/api/data/projects
    [{...},
     {...}]

## Available data

Data you can store and retrieve are from the following type :

* persons
* projects
* project\_status
* tasks 
* task\_status
* task\_types
* departments
* time\ spents
* episodes
* sequences
* shots
* assets
* asset\_types
* file\_status
* working\_files
* output\_files
* preview\_files
* output\_types
* softwares


*Warning: below documentation is a bit outdated and incomplete.*

## HTTP routes

### Main routes

* GET `/data/projects`: Get all projects
* GET `/data/project-status`: Get all project status
* GET `/data/persons`: Get all projects
* GET `/data/episodes`: Get all episodes
* GET `/data/sequences`: Get all sequences
* GET `/data/shots`: Get all shots
* GET `/data/asset-types`: Get all asset types
* GET `/data/shots`: Get all assets
* GET `/data/departments`: Get all departements
* GET `/data/tasks`: Get all projects
* GET `/data/task-types`: Get all task types
* GET `/data/task-status`: Get all task status
* GET `/data/file-status`: Get all file status
* GET `/data/working-files`: Get all working files
* GET `/data/output-files`: Get all output files
* GET `/data/comments`: Get all comments
* GET `/data/entity-types`: Get all entity types (asset or shot)
* GET `/data/entities`: Get all entities (asset or shot)

### Main operations

All these routes support CRUD operations, filtering and pagination. We'll take 
projects as example but it works for every route listed above.

#### Create

POST `/data/projects` will  create a new project instance if you give required 
data in the request body. 

#### Retrieve

GET `/data/projects/:project_id` will return project with given ID.

#### Delete

DELETE `/data/projects/:project_id` If nothing is linked to the given project,
it will remove it from the database.

#### Paginate

GET `projects?page=2` will return the seconde page of projects listed in the
database. Each page has a size of 100 entries.

#### Filter

GET `projects?name=Agent327` will return all projects of which name is equal to
Agent327. Filters can only be applied to project fields. Joins are not
supported.

### Project related routes

* GET `/data/projects/:project_id/episodes`: Get all episodes of given
  project.
* GET `/data/projects/:project_id/sequences`: Get all sequences of
  given project.
* GET `/data/projects/:project_id/shots`: Get all shots related of given
  project.
* GET `/data/episodes/:episode_id/sequences`: Get all sequences of given
  episode.
* GET `/data/sequences/:sequence_id/shots`: Get all sequences of given shot.

* GET `/data/shots/:shot_id/assets`: Get all assets that appears on given shot.
* GET `/data/assets-types`: Get all asset types.
* GET `/data/projects/:project_id/assets`: Get all assets related to given
  project.
* GET `/data/projects/:project_id/asset_types/:asset_type_id/assets`: Get all
  assets related to given project for given asset type.


### Task routes 

* GET `/data/shots/:shot_id/tasks`: Get all tasks related to given shot.
* GET `/data/assets/:asset_id/tasks`: Get all tasks related to given asset.
* PUT `/data/tasks/:task_id/start`: Start a task, change its real start date to
  now.
* PUT `/data/tasks/:task_id/assign`: Assign a task to someone.
    * *person_id*: The project id that is going to be changed.


### File routes

* POST `/project/set-tree`: Set given file tree for given project.
    * *project_id*: The project id that is going to be changed.
    * *tree_name*: The name of the file tree to use from the file tree folder.
* POST `/project/tree/folder`: Build a folder path for given task
    * *mode*: "working" or "output" or any context set in the file tree
      descriptor.
    * *task_id*: Task ID for which folder path is required.
    * *sep* (optional): separator used to build path ('/' or '\\')
* POST `/project/tree/file`: 
    * *mode*: "working" or "output" or any context set in the file tree
      descriptor.
    * *task_id*: Task ID for which folder path is required.
    * *sep* (optional): separator used to build path ('/' or '\\')
    * *version* (optional): file version to add to the name.
    * *comment* (optional): a comment to add at the end of the file name.
* POST `/project/files/working-files/publish`: Create an output file entry 
  linked to a working file revision. Returns related file path.
    * *task_id*: Task ID for which folder path is required.
    * *sep* (optional): separator used to build path ('/' or '\\')
    * *working_file_revision*: The working file revision which is the source
      of the output file.
    * *comment* (optional): comment to save and to add at the end of the file
      name.


### Thumbnails

* POST `/pictures/thumbnails/persons/<person_id>`: Set a thumbnail on given person.
    * Expect thumbnail file in his body
* POST `/pictures/thumbnails/projects/<project_id>`: Set a thumbnail on given project.
    * Expect thumbnail file in his body
* GET `/pictures/thumbnails/persons/<person_id>.png`: Get thumbnail bound to given shot.
* GET `/pictures/thumbnails/projects/<project_id>.png`: Get thumbnail bound to given project.


### Shotgun import

* POST `/data/import/shotgun/projects`: Turn raw data from Shotgun projects into Zou data.
    * Expect shotgun data in the body.
* POST `/data/import/shotgun/persons`: Turn raw data from Shotgun human users into Zou data.
    * Expect shotgun data in the body.
* POST `/data/import/shotgun/shots`: Turn raw data from Shotgun shots into Zou data.
    * Expect shotgun data in the body.
* POST `/data/import/shotgun/sequences`: Turn raw data from Shotgun sequences into Zou data.
    * Expect shotgun data in the body.
* POST `/data/import/shotgun/assets`: Turn raw data from Shotgun assets into Zou data.
    * Expect shotgun data in the body.
* POST `/data/import/shotgun/steps`: Turn raw data from Shotgun steps into Zou data.
    * Expect shotgun data in the body.
* POST `/data/import/shotgun/status`: Turn raw data from Shotgun status into Zou data.
    * Expect shotgun data in the body.
* POST `/data/import/shotgun/tasks`: Turn raw data from Shotgun tasks into Zou data.
    * Expect shotgun data in the body.
* POST `/data/import/shotgun/versions`: Turn raw data from Shotgun versions into Zou data.
    * Expect shotgun data in the body.
* POST `/data/import/shotgun/notes`: Turn raw data from Shotgun notes into Zou data.
    * Expect shotgun data in the body.
* POST `/data/import/shotgun/errors`: Allow to save error information when data
  cannot be imported.
* POST `/data/import/shotgun/errors/:error_id`: Allow to retrieve details about
  a given Shotgun import error. 


### CSV Import

* POST `/data/import/csv/persons`: Export persons info from a CSV file. 
    * Expect csv file in the body
* POST `/data/import/csv/projects`: Export projects info from a CSV file. 
    * Expect csv file in the body
* POST `/data/import/csv/shots`: Export shots info from a CSV file. 
    * Expect csv file in the body
* POST `/data/import/csv/asset`: Export assets info from a CSV file. 
    * Expect csv file in the body
* POST `/data/import/csv/task-types`: Export task types info from a CSV file. 
    * Expect csv file in the body
* POST `/data/import/csv/tasks.csv`: Export tasks info from a CSV file. 
    * Expect csv file in the body


### CSV Export

* GET `/export/csv/persons.csv`: Export persons info into a CSV file.
* GET `/export/csv/projects.csv`: Export projects info into a CSV file.
* GET `/export/csv/shots.csv`: Export shots info into a CSV file.
* GET `/export/csv/assets.csv`: Export asset info into a CSV files.
* GET `/export/csv/task-types.csv`: Export task type info into a CSV file.
* GET `/export/csv/tasks.csv`: Export task info into a CSV file. 

