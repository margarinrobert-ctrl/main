import sys; sys.path.insert(0,"research")
import pandas as pd
pd.set_option("display.width",200); pd.set_option("display.max_columns",30)
from edgelab import data, splits, analysis
d = data.bars(15); B = splits.blocks(d)["discovery"]
print("=== TIME-OF-DAY MAP (discovery, 1.0xATR stop, 1:1, 30-min buckets) ===")
print(analysis.time_map(d, B, bucket=30).to_string(index=False, float_format=lambda x:f"{x:.2f}"))
print("\n=== same, 15-minute buckets ===")
print(analysis.time_map(d, B, bucket=15).to_string(index=False, float_format=lambda x:f"{x:.2f}"))
print("\n=== STOP SWEEP (discovery) ===")
print(analysis.stop_sweep(d, B).to_string(index=False, float_format=lambda x:f"{x:.3f}"))
print("\n=== TARGET SWEEP (discovery, stop 1.0xATR) ===")
print(analysis.rr_sweep(d, B).to_string(index=False, float_format=lambda x:f"{x:.3f}"))
print("\n=== HOLDING TIME (discovery) ===")
print(analysis.hold_sweep(d, B).to_string(index=False, float_format=lambda x:f"{x:.3f}"))
print("\n=== EXCURSIONS in R (discovery) ===")
print(analysis.excursions(d, B).to_string(float_format=lambda x:f"{x:.2f}"))
