# How to create a new release for Zou

We release Zou versions through Github Actions on Pypi. Every time a new version is ready, we
follow this process:

1. Rebase on the main branch.
2. Up the version number located the `zou/__version__` file.
3. Push changes to `main` branch.
4. Tag the commit and push the changes to Github.
5. Github Actions will build the package from the sources and publish the package on Pypi

You can run a script to perform these commands at once, he is located in scripts/release.sh.

# Deployment

Please see the Zou documentation for the update instructions.
