.. figure:: https://zou.cg-wire.com/kitsu.png
   :alt: Kitsu Logo

Zou, the Kitsu API is the memory of your animation production
-------------------------------------------------------------

The Kitsu API allows to store and manage the data of your animation/VFX
production. Through it, you can link all the tools of your pipeline and make
sure they are all synchronized.

A dedicated Python client, `Gazu <https://gazu.cg-wire.com>`_, allows users to
integrate Zou into the tools. 

|CI badge| |Downloads badge| |Discord badge|

Features
~~~~~~~~

Zou can:

-  Store production data, such as projects, shots, assets, tasks, and file metadata.
-  Track the progress of your artists
-  Store preview files and version them
-  Provide folder and file paths for any task
-  Import and Export data to CSV files
-  Publish an event stream of changes

Installation and Documentation
~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~

Installation of Zou requires the setup of third-party tools such as a database
instance, so it is recommended to follow the documentation:

`https://zou.cg-wire.com/ <https://zou.cg-wire.com>`__

Specification:
- `https://api-docs.kitsu.cloud/ <https://api-docs.kitsu.cloud>`__

Contributing
------------

Contributions are welcomed so long as the `C4
contract <https://rfc.zeromq.org/spec:42/C4>`__ is respected.

Zou is based on Python and the `Flask <http://flask.pocoo.org/>`__
framework.

You can use the pre-commit hook for Black (a Python code formatter) before
committing:

.. code:: bash

    pip install pre-commit
    pre-commit install

Instructions for setting up a development environment are available in
`the documentation <https://zou.cg-wire.com/development/>`__


Contributors
------------

* @aboellinger (Xilam/Spa)
* @BigRoy (Colorbleed)
* @EvanBldy (CGWire) - *maintainer*
* @ex5 (Blender Studio)
* @flablog (Les Fées Spéciales)
* @frankrousseau (CGWire) - *maintainer*
* @kaamaurice (Tchak)
* @g-Lul (TNZPV)
* @pilou (Freelancer)
* @LedruRollin (Cube-Xilam)
* @mathbou (Zag)
* @manuelrais (TNZPV)
* @NehmatH (CGWire)
* @pcharmoille (Unit Image)
* @Tilix4 (Normaal)

About authors
~~~~~~~~~~~~~

Kitsu is written by CGWire, a company based in France. We help with animation and
VFX studios to collaborate better through efficient tooling. We already work
with more than 70 studios around the world.

Visit `cg-wire.com <https://cg-wire.com>`__ for more information.

|CGWire Logo|

.. |CI badge| image:: https://github.com/cgwire/zou/actions/workflows/ci.yml/badge.svg
   :target: https://github.com/cgwire/zou/actions/workflows/ci.yml
.. |Gitter badge| image:: https://badges.gitter.im/cgwire/Lobby.png
   :target: https://gitter.im/cgwire/Lobby
.. |CGWire Logo| image:: https://zou.cg-wire.com/cgwire.png
   :target: https://cgwire.com
.. |Downloads badge| image:: https://static.pepy.tech/personalized-badge/zou?period=total&units=international_system&left_color=grey&right_color=orange&left_text=Downloads
   :target: https://pepy.tech/project/zou
.. |Discord badge| image:: https://badgen.net/badge/icon/discord?icon=discord&label
   :target: https://discord.com/invite/VbCxtKN
