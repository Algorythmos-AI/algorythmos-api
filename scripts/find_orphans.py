#!/usr/bin/env python3
"""
Find orphaned Python modules (no inbound imports).
"""
import os
import re
from pathlib import Path

# Repo root
ROOT = Path('/Users/skalaliya/Desktop/api-algorythmos')

# Directories to scan for modules
MODULE_DIRS = [
    ROOT / 'document_processing',
    ROOT / 'pdf_usage_extractor',
    ROOT / 'app',
    ROOT / 'core',
    ROOT / 'api',
]

# Files to scan for imports
IMPORT_SCAN_DIRS = [
    ROOT / 'document_processing',
    ROOT / 'pdf_usage_extractor', 
    ROOT / 'app',
    ROOT / 'core',
    ROOT / 'api',
    ROOT / 'tests',
]

# Patterns to exclude from orphan detection
EXCLUDE_PATTERNS = [
    '__init__.py',
    '__pycache__',
    'conftest.py',
    'test_*.py',
]

def is_excluded(path: Path) -> bool:
    """Check if file should be excluded."""
    for pattern in EXCLUDE_PATTERNS:
        if pattern in str(path):
            return True
    return False

def get_all_modules() -> set:
    """Get all Python module files."""
    modules = set()
    for dir_path in MODULE_DIRS:
        if not dir_path.exists():
            continue
        for py_file in dir_path.rglob('*.py'):
            if not is_excluded(py_file):
                rel_path = py_file.relative_to(ROOT)
                modules.add(str(rel_path))
    return modules

def scan_imports() -> dict:
    """Scan all Python files for import statements."""
    imports = {}  # module -> list of files that import it
    
    import_pattern = re.compile(r'^\s*(?:from|import)\s+([a-zA-Z0-9_.]+)', re.MULTILINE)
    
    for dir_path in IMPORT_SCAN_DIRS:
        if not dir_path.exists():
            continue
        for py_file in dir_path.rglob('*.py'):
            try:
                content = py_file.read_text()
                matches = import_pattern.findall(content)
                
                for match in matches:
                    # Convert import path to potential file paths
                    # e.g., 'document_processing.models' -> 'document_processing/models.py'
                    parts = match.split('.')
                    
                    # Try various combinations
                    for i in range(len(parts), 0, -1):
                        potential_path = '/'.join(parts[:i]) + '.py'
                        if potential_path in imports:
                            imports[potential_path].append(str(py_file.relative_to(ROOT)))
                        else:
                            imports[potential_path] = [str(py_file.relative_to(ROOT))]
                            
            except Exception as e:
                print(f"Warning: Could not scan {py_file}: {e}")
                
    return imports

def find_orphans() -> list:
    """Find modules with no inbound imports."""
    all_modules = get_all_modules()
    imports = scan_imports()
    
    orphans = []
    for module in sorted(all_modules):
        if module not in imports:
            orphans.append(module)
    
    return orphans

if __name__ == '__main__':
    print("# ORPHAN MODULE ANALYSIS")
    print()
    
    orphans = find_orphans()
    
    if orphans:
        print(f"Found {len(orphans)} potentially orphaned modules:")
        print()
        for orphan in orphans:
            print(f"  - {orphan}")
        print()
        print("⚠️  Action needed: Review and remove or relocate orphans")
    else:
        print("✅ No orphaned modules found")
        print()
    
    print("# SUMMARY")
    print(f"Total orphaned modules: {len(orphans)}")
    
    if not orphans:
        print("\n✅ All modules are referenced")
