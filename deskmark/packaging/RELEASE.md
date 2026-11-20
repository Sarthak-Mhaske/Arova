# Release checklist

Do these in order. Every step is checkable; none of them is "looks fine".

## 1. Version

One version, four places — they must agree:

```bash
grep -rn "0\.3\.0" \
  deskmark/__init__.py pyproject.toml packaging/aur/PKGBUILD \
  packaging/aur/.SRCINFO CHANGELOG.md
```

A test asserts `__version__` equals `pyproject.toml`; nothing asserts the AUR
files, so check those by eye.

## 2. Green before anything else

```bash
python -m pytest -q
python -m compileall -q deskmark
python -m build && python -m twine check dist/*
```

## 3. The wheel, not the source tree

Install the built artifact somewhere disposable and drive it:

```bash
python -m venv /tmp/rel && /tmp/rel/bin/pip install dist/*.whl
export DESKMARK_HOME=/tmp/rel-home
/tmp/rel/bin/deskmark --version
/tmp/rel/bin/deskmark doctor
/tmp/rel/bin/deskmark save release-smoke && /tmp/rel/bin/deskmark resume
```

If `hooks/shell_hook.sh` is missing from the wheel, this is where you find out.

## 4. Changelog

`CHANGELOG.md` gets a dated section with Added / Changed / Fixed. If the release
changes behaviour, the matching sentence in `README.md` and `docs/spec.md` was
updated in the same commit.

## 5. Tag and publish

```bash
git tag -a v0.3.0 -m "deskmark 0.3.0"
git push origin main --tags
```

`.github/workflows/release.yml` then builds, checks the metadata, publishes to
PyPI over trusted publishing (no token in the repo), and attaches the wheel and
sdist to a GitHub release. The job fails rather than publishing if the tag and
the package version disagree.

## 6. AUR

```bash
cd packaging/aur
updpkgsums            # if the source tarball is not SKIP
makepkg --printsrcinfo > .SRCINFO
makepkg -f            # build the package locally first
```

Then push the updated `PKGBUILD` and `.SRCINFO` to the AUR git remote. The AUR
file is committed in this repo on purpose, so the package a user builds is the
one in review here.

## 7. After

- Check `pipx install deskmark` in a clean container.
- Read the release page as a stranger would: does the first paragraph say what
  this is and who it is for?
