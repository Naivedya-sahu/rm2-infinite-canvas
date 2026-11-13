"""Reject unreviewed native editor resources before building the rM2 patch."""
import hashlib
from pathlib import Path

PREFIX = 'qml/device/view/documentview/'
PINNED = {
    PREFIX + 'DocumentView.qml': '867b30a725a4ae97e3459f07a60cd72bcafb21db9a0b374f02d75c5cd8d83269',
    PREFIX + 'DeviceSceneView.qml': '78df7fe68f0be6e0795cde67bdb5ce5c5f355c9100f0c14d6e8157c688271a0c',
    PREFIX + 'SceneViewGestures.qml': 'ab11773343d512d7f1e4259411c91ed2aff5c222c787cccd2e8d076b4e33563f',
}


def check(resources):
    errors = []
    for relative, expected in PINNED.items():
        path = Path(resources) / relative
        if not path.is_file():
            errors.append(f'Missing reviewed resource: {relative}')
        elif hashlib.sha256(path.read_bytes()).hexdigest() != expected:
            errors.append(f'Unreviewed resource content: {relative}')
    return errors


if __name__ == '__main__':
    import argparse
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('resources', type=Path)
    args = parser.parse_args()
    errors = check(args.resources)
    print('\n'.join(errors) if errors else 'All three native editor resource hashes match reviewed OS 3.28.0.172')
    raise SystemExit(bool(errors))
