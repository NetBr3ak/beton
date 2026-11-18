"""Load the packaged Python modules for the npm and Cargo launchers."""

import sys
import types

if sys.version_info < (3, 11):
    raise SystemExit("beton: Python 3.11 or later is required")

package = types.ModuleType("beton_checks")
package.__path__ = []
sys.modules[package.__name__] = package
discovery = types.ModuleType("beton_checks.discovery")
sys.modules[discovery.__name__] = discovery
exec(sys.argv.pop(1), discovery.__dict__)
exec(sys.argv.pop(1), {"__name__": "__main__"})
