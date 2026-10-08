#!/usr/bin/env python3
"""Validate a directory and author indexes without trusting their publisher claims."""
import hashlib
import json
import pathlib
import re
import urllib.parse
import urllib.request
import zipfile
from io import BytesIO

ID = re.compile(r"^[a-z][a-z0-9]*(\.[a-z][a-z0-9_-]*)+$")
VERSION = re.compile(r"^(0|[1-9]\d*)\.(0|[1-9]\d*)\.(0|[1-9]\d*)(?:-[0-9A-Za-z.-]+)?(?:\+[0-9A-Za-z.-]+)?$")
REPOSITORY = re.compile(r"^[A-Za-z0-9_.-]+/[A-Za-z0-9_.-]+$")


def require(condition, message):
    if not condition:
        raise ValueError(message)


def repository_name(value):
    require(isinstance(value, str) and REPOSITORY.fullmatch(value), "repository must be owner/repo")
    require(all(part not in ('.', '..') for part in value.split('/')), "invalid repository")
    return value


def https_url(value, hostname, prefix):
    require(isinstance(value, str), "URL must be a string")
    parsed = urllib.parse.urlsplit(value)
    require(parsed.scheme == 'https' and parsed.netloc == hostname and
            not parsed.query and not parsed.fragment and parsed.path.startswith(prefix),
            f"URL must be HTTPS on {hostname}{prefix}")
    require('%' not in parsed.path and '\\' not in parsed.path and
            all(part not in ('.', '..') for part in parsed.path.split('/')), "unsafe URL path")
    return parsed


def validate_catalog(catalog):
    require(isinstance(catalog, dict) and catalog.get('catalogFormat') == 1, "unsupported catalog format")
    require(isinstance(catalog.get('modules'), list), "modules must be an array")
    seen = set()
    for entry in catalog['modules']:
        require(isinstance(entry, dict), "directory entry must be an object")
        module_id = entry.get('id')
        require(isinstance(module_id, str) and ID.fullmatch(module_id), "invalid module ID")
        require(module_id not in seen, f"duplicate module ID: {module_id}")
        seen.add(module_id)
        for field in ('name', 'description', 'author'):
            require(isinstance(entry.get(field), str) and entry[field].strip(), f"missing {field}: {module_id}")
        repository = repository_name(entry.get('repository'))
        url = https_url(entry.get('indexUrl'), 'raw.githubusercontent.com', f'/{repository}/')
        require(len(url.path.split('/')) >= 5 and url.path.endswith('.json'), "index URL must include a ref and JSON path")
    return catalog


def validate_index(index, entry):
    require(isinstance(index, dict) and index.get('indexFormat') == 1, "unsupported index format")
    require(index.get('moduleId') == entry['id'], "index module identity mismatch")
    require(index.get('repository') == entry['repository'], "index publisher repository mismatch")
    require(isinstance(index.get('versions'), list) and index['versions'], "empty version index")
    versions = set()
    for release in index['versions']:
        require(isinstance(release, dict), "version entry must be an object")
        version = release.get('version')
        require(isinstance(version, str) and VERSION.fullmatch(version), "invalid release version")
        require(version not in versions, f"duplicate release version: {version}")
        versions.add(version)
        manifest = release.get('manifest')
        require(isinstance(manifest, dict) and manifest.get('id') == entry['id'] and
                manifest.get('version') == version, "release manifest identity mismatch")
        require(isinstance(manifest.get('hostApi'), str) and isinstance(manifest.get('dataVersion'), int)
                and not isinstance(manifest['dataVersion'], bool) and manifest['dataVersion'] >= 1,
                "invalid host compatibility or data version")
        require(isinstance(manifest.get('permissions'), list) and
                all(isinstance(p, str) and p for p in manifest['permissions']), "invalid permissions")
        require(isinstance(manifest.get('dependencies'), list), "invalid dependencies")
        for dependency in manifest['dependencies']:
            if isinstance(dependency, str):
                require(ID.fullmatch(dependency), "invalid module dependency")
            else:
                require(isinstance(dependency, dict) and isinstance(dependency.get('moduleId'), str)
                        and ID.fullmatch(dependency['moduleId']) and isinstance(dependency.get('version'), str)
                        and dependency['version'].strip(), "invalid module dependency")
        require(isinstance(release.get('services'), list), "missing service declarations")
        services = set()
        for service in release['services']:
            require(isinstance(service, dict) and isinstance(service.get('id'), str)
                    and service['id'] and type(service.get('major')) is int and service['major'] > 0
                    and service.get('kind') in ('query', 'command'), "invalid service declaration")
            key = (service['id'], service['major'])
            require(key not in services, "duplicate service declaration")
            services.add(key)
        parsed = https_url(release.get('url'), 'github.com', f'/{entry["repository"]}/releases/download/')
        require(len(parsed.path.split('/')) == 7 and parsed.path.endswith('.xmodule'), "release URL must pin a tag and asset")
        require(type(release.get('size')) is int and 0 < release['size'] <= 16 * 1024 * 1024, "invalid package size")
        require(isinstance(release.get('sha256'), str) and re.fullmatch(r'[0-9a-f]{64}', release['sha256']), "invalid SHA-256")
        require(release.get('signature') is None or isinstance(release['signature'], dict), "invalid signature metadata")
    return index


def validate_package(data, release):
    require(len(data) == release['size'], "download size mismatch")
    require(hashlib.sha256(data).hexdigest() == release['sha256'], "download digest mismatch")
    with zipfile.ZipFile(BytesIO(data)) as archive:
        names = archive.namelist()
        require(len(names) <= 256 and len(names) == len(set(names)), "duplicate or excessive ZIP entries")
        require(sum(item.file_size for item in archive.infolist()) <= 16 * 1024 * 1024,
                "expanded package too large")
        for item in archive.infolist():
            require(item.file_size <= 2 * 1024 * 1024 and item.filename and
                    re.fullmatch(r'[a-zA-Z0-9_@.-]+(/[a-zA-Z0-9_@.-]+)*', item.filename) and
                    all(p not in ('.', '..') for p in item.filename.split('/')) and
                    not item.is_dir() and item.external_attr >> 16 & 0o170000 in (0, 0o100000)
                    and not item.flag_bits & 1 and item.compress_type in (zipfile.ZIP_STORED, zipfile.ZIP_DEFLATED),
                    "unsafe package entry")
        files = {name: archive.read(name) for name in names}
    require('package.json' in files and 'module.json' in files, "package metadata missing")
    package = json.loads(files.pop('package.json'))
    require(package.get('packageFormat') == 2, "unsupported package format")
    require(isinstance(package.get('release'), dict) and package['release'].get('channel') in ('local', 'market'),
            "invalid package release source")
    require(isinstance(package.get('files'), list), "package file list missing")
    listed = set()
    for item in package['files']:
        name = item.get('path')
        require(name in files and name not in listed, "package file identity mismatch")
        listed.add(name)
        require(len(files[name]) == item.get('size') and hashlib.sha256(files[name]).hexdigest() == item.get('sha256'),
                "package internal digest mismatch")
    require(listed == files.keys(), "unlisted package files")
    definition = json.loads(files['module.json'])
    require(definition.get('formatVersion') == 3, "unsupported module format")
    require(definition.get('manifest') == release['manifest'], "package manifest identity mismatch")
    require(definition.get('services', []) == release['services'], "package service identity mismatch")
    require(package.get('signature') == release.get('signature'), "signature metadata mismatch")
    return definition


def fetch(url, limit=16 * 1024 * 1024):
    # Reject redirects: moving a publishing repository is a directory review, not a download fallback.
    class NoRedirect(urllib.request.HTTPRedirectHandler):
        def redirect_request(self, request, fp, code, message, headers, new_url):
            parsed = urllib.parse.urlsplit(new_url)
            # GitHub Release assets intentionally redirect to the dedicated asset CDN.
            require(parsed.scheme == 'https' and parsed.hostname in ('release-assets.githubusercontent.com', 'objects.githubusercontent.com'),
                    "unexpected publishing redirect")
            return super().redirect_request(request, fp, code, message, headers, new_url)
    with urllib.request.build_opener(NoRedirect).open(url, timeout=30) as response:
        data = response.read(limit + 1)
    require(len(data) <= limit, "response too large")
    return data


def validate_directory(catalog_path, index_dir=None, package_dir=None, online=False):
    catalog = validate_catalog(json.loads(pathlib.Path(catalog_path).read_text()))
    for entry in catalog['modules']:
        if index_dir:
            raw = (pathlib.Path(index_dir) / f'{entry["id"]}.json').read_bytes()
        elif online:
            raw = fetch(entry['indexUrl'])
        else:
            continue
        index = validate_index(json.loads(raw), entry)
        for release in index['versions']:
            if package_dir:
                data = (pathlib.Path(package_dir) / urllib.parse.urlsplit(release['url']).path.split('/')[-1]).read_bytes()
            elif online:
                data = fetch(release['url'])
            else:
                continue
            validate_package(data, release)
    return catalog


def main():
    import argparse
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('catalog', type=pathlib.Path)
    parser.add_argument('--index-dir', type=pathlib.Path)
    parser.add_argument('--package-dir', type=pathlib.Path)
    parser.add_argument('--online', action='store_true', help='Fetch and verify author indexes and all release assets')
    args = parser.parse_args()
    try:
        directory = validate_directory(args.catalog, args.index_dir, args.package_dir, args.online)
    except (ValueError, OSError, zipfile.BadZipFile, KeyError, TypeError) as error:
        parser.exit(1, f'Invalid directory: {error}\n')
    print(f'Validated {len(directory["modules"])} directory entries' + (' and author packages' if args.package_dir or args.online else ''))


if __name__ == '__main__':
    main()
