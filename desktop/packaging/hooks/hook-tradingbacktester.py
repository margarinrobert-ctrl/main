"""PyInstaller hook: pull in the whole package.

Indicators register themselves as a side effect of importing
``tradingbacktester.indicators.library``, and strategy files name indicators by
string, so static analysis cannot see the dependency.  Collecting every
submodule is cheap here -- the package is pure Python and a few hundred KB.
"""

from PyInstaller.utils.hooks import collect_data_files, collect_submodules

hiddenimports = collect_submodules("tradingbacktester")
datas = collect_data_files("tradingbacktester")
