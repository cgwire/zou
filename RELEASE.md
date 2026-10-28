# How to create a new release for Zou

We release Zou versions through Github Actions on Pypi. Every time a new version is ready, we
follow this process:

1. Rebase on the main branch.
2. Bump the `__version__` variable in `zou/__init__.py`.
3. Push changes to `main` branch.
4. Tag the commit and push the changes to Github.
5. Github Actions will build the package from the sources and publish the package on Pypi

You can run `scripts/release.sh` to perform these commands at once. It bumps the patch version
by default (1.0.97 → 1.0.98); pass `minor` (→ 1.1.0) or `major` (→ 2.0.0) to bump another part:

```bash
scripts/release.sh minor
```

# Deployment

Please see the Zou documentation for the update instructions.
