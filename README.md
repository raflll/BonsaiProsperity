# BonsaiProsperity

## Backtesting

You can use the community backtester. Install and run it like this:

```bash
pip install -U prosperity4bt
prosperity4bt trader.py 0
```

That will simulate round 0 (the tutorial round) using the same price/trade data from those CSVs and show your PnL.

To run a round with local data (e.g. Round 1), from the round's directory:

```bash
cd ROUND1
prosperity4bt trader.py 1 --data ./data
```

You can also add `--print` to see your `print()` output, or `--out results.log` to save the full log.
