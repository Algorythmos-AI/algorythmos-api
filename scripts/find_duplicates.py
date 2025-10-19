#!/usr/bin/env python3
"""
Find duplicate files, junk files, and empty files in the repository.
"""
import hashlib
import os
import sys

EXCLUDE_DIRS = {'.git', '.venv', '__pycache__', '.pytest_cache', 'dist', 'build', '.mypy_cache', 'node_modules'}
JUNK_PATTERNS = ('.DS_Store', '.swp', '.tmp', '.log', '.ipynb_checkpoints')

def is_junk(path):
    """Check if a file is junk that should be removed."""
    n = os.path.basename(path).lower()
    return any(pat in n for pat in JUNK_PATTERNS) or n.endswith('.pyc')

def iter_files(root='.'):
    """Iterate over all files in the repository, categorizing them."""
    for d, sub, files in os.walk(root):
        # Skip excluded directories
        if any(x in d.split(os.sep) for x in EXCLUDE_DIRS):
            continue
        
        for f in files:
            p = os.path.join(d, f)
            
            # Check if junk
            if is_junk(p):
                yield ('JUNK', p)
                continue
            
            # Check if empty
            try:
                if os.path.getsize(p) == 0:
                    yield ('EMPTY', p)
                    continue
            except OSError:
                continue
            
            yield ('FILE', p)

def sha256(path, chunk=1024*1024):
    """Calculate SHA256 hash of a file."""
    h = hashlib.sha256()
    try:
        with open(path, 'rb') as fd:
            while True:
                b = fd.read(chunk)
                if not b:
                    break
                h.update(b)
    except Exception as e:
        print(f"Error hashing {path}: {e}", file=sys.stderr)
        return None
    return h.hexdigest()

def main():
    """Find duplicates, junk, and empty files."""
    duplicates = {}
    junk = []
    empty = []
    
    for kind, path in iter_files('.'):
        if kind == 'JUNK':
            junk.append(path)
            continue
        if kind == 'EMPTY':
            empty.append(path)
            continue
        
        try:
            h = sha256(path)
            if h:
                duplicates.setdefault(h, []).append(path)
        except Exception:
            continue
    
    # Find actual duplicates (more than one file with same hash)
    dups = [paths for paths in duplicates.values() if len(paths) > 1]
    
    print('# DUPLICATES')
    print(f'Found {len(dups)} groups of duplicate files:')
    for group in sorted(dups):
        print(' - ' + ' | '.join(sorted(group)))
    
    print('\n# JUNK')
    print(f'Found {len(junk)} junk files:')
    for p in sorted(junk):
        print(' - ' + p)
    
    print('\n# EMPTY')
    print(f'Found {len(empty)} empty files:')
    for p in sorted(empty):
        print(' - ' + p)
    
    # Summary
    print('\n# SUMMARY')
    print(f'Total duplicate groups: {len(dups)}')
    print(f'Total junk files: {len(junk)}')
    print(f'Total empty files: {len(empty)}')
    print(f'Action needed: {len(dups) + len(junk) + len(empty)} files')

if __name__ == '__main__':
    main()
