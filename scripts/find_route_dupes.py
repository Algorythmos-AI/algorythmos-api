#!/usr/bin/env python3
"""
Find duplicate routes in the FastAPI application.
"""
import sys
sys.path.insert(0, '/Users/skalaliya/Desktop/api-algorythmos')

try:
    from app import app
    from collections import defaultdict
    
    print("# ROUTE ANALYSIS")
    print(f"Total routes: {len(app.routes)}")
    print()
    
    # Group routes by (path, methods)
    route_map = defaultdict(list)
    
    for route in app.routes:
        if hasattr(route, 'path') and hasattr(route, 'methods'):
            path = route.path
            methods = route.methods if route.methods else {'GET'}
            
            for method in methods:
                key = (path, method)
                route_map[key].append(route)
    
    # Find duplicates
    duplicates = {k: v for k, v in route_map.items() if len(v) > 1}
    
    if duplicates:
        print("# DUPLICATE ROUTES")
        print(f"Found {len(duplicates)} duplicate (path, method) combinations:")
        print()
        for (path, method), routes in sorted(duplicates.items()):
            print(f"{method} {path}")
            for route in routes:
                endpoint = getattr(route, 'endpoint', None)
                if endpoint:
                    module = getattr(endpoint, '__module__', 'unknown')
                    name = getattr(endpoint, '__name__', 'unknown')
                    print(f"  - {module}.{name}")
            print()
    else:
        print("# NO DUPLICATE ROUTES")
        print("✅ No duplicate (path, method) combinations found")
        print()
    
    # Summary
    unique_paths = len(set(path for path, _ in route_map.keys()))
    print("# SUMMARY")
    print(f"Unique paths: {unique_paths}")
    print(f"Total (path, method) combinations: {len(route_map)}")
    print(f"Duplicate combinations: {len(duplicates)}")
    
    if duplicates:
        print("\n⚠️  Action needed: Consolidate duplicate routes")
    else:
        print("\n✅ No action needed: Routes are unique")

except Exception as e:
    print(f"Error analyzing routes: {e}", file=sys.stderr)
    import traceback
    traceback.print_exc()
    sys.exit(1)
